"""Site-managed web search configuration and runtime credential resolution.

The site owns exactly one configuration: a global ``ToolConfig`` row named
``web_search`` with ``team_id`` NULL. Teams and agents may select an enabled
provider, but they can never supply credentials of their own: the runtime
always reads the site row.

Stored layout (``ToolConfig.credentials``):

- ``default_engine``: provider used by ``auto`` (never inferred from keys)
- ``tavily_enabled`` / ``bocha_enabled``: ``"true"`` / ``"false"`` strings
- ``TAVILY_API_KEY`` / ``BOCHA_API_KEY``: ``enc:v1:`` + Fernet ciphertext
- keys starting with ``_``: reserved migration/audit fields, preserved verbatim
"""

import logging
from typing import Any

from tortoise.transactions import in_transaction

from app.integrations.credentials import (
    IntegrationSecretError,
    decrypt_secret,
    encrypt_secret,
)
from app.models.tool_config import ToolConfig
from app.schemas.response import BusinessError
from app.schemas.web_search import (
    WEB_SEARCH_ENGINES,
    WebSearchConfigOut,
    WebSearchConfigUpdate,
)

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_NAME = "web_search"
ENCRYPTED_PREFIX = "enc:v1:"
DEFAULT_ENGINE_FIELD = "default_engine"
LEGACY_CREDENTIALS_FIELD = "_legacy_credentials"
SITE_CONFIG_VERSION_FIELD = "_site_config_version"
SITE_CONFIG_VERSION = "1"
# Shared with the startup migration so a save and the one-time cutover cannot
# interleave and overwrite each other's secret values.
SAVE_LOCK_KEY = 736421091

# Provider catalog. Adding a provider means adding its enabled flag and the
# credential keys the runtime should load; see ``get_web_search_runtime``.
ENGINE_ENABLED_FIELDS: dict[str, str] = {
    "tavily": "tavily_enabled",
    "bocha": "bocha_enabled",
}
ENGINE_SECRET_FIELDS: dict[str, str] = {
    "tavily": "TAVILY_API_KEY",
    "bocha": "BOCHA_API_KEY",
}
# Update-field name for each provider secret.
SECRET_UPDATE_FIELDS: dict[str, str] = {
    "tavily": "tavily_api_key",
    "bocha": "bocha_api_key",
}

_FALLBACK_ENGINE = WEB_SEARCH_ENGINES[0]


def _as_flag(value: Any) -> bool:
    """Read a stored enabled flag; anything unrecognized is disabled."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


def _flag_value(enabled: bool) -> str:
    return "true" if enabled else "false"


def _stored_credentials(config: Any) -> dict[str, Any]:
    credentials = getattr(config, "credentials", None)
    return dict(credentials) if isinstance(credentials, dict) else {}


def _stored_default_engine(credentials: dict[str, Any]) -> str | None:
    value = credentials.get(DEFAULT_ENGINE_FIELD)
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in ENGINE_ENABLED_FIELDS else None


def _stored_secret(credentials: dict[str, Any], engine: str) -> str | None:
    field = ENGINE_SECRET_FIELDS[engine]
    value = credentials.get(field)
    return value if isinstance(value, str) and value else None


def _decrypt_stored_secret(value: str) -> str:
    """Decrypt one stored provider secret without leaking it into errors."""
    if not value.startswith(ENCRYPTED_PREFIX):
        logger.warning("Stored web search credential is not encrypted")
        raise BusinessError(msg_key="web_search_credentials_unreadable")
    try:
        return decrypt_secret(value[len(ENCRYPTED_PREFIX) :])
    except IntegrationSecretError:
        logger.warning("Stored web search credential cannot be decrypted")
        raise BusinessError(msg_key="web_search_credentials_unreadable") from None


def _to_output(credentials: dict[str, Any]) -> WebSearchConfigOut:
    return WebSearchConfigOut(
        default_engine=_stored_default_engine(credentials) or _FALLBACK_ENGINE,
        tavily_enabled=_as_flag(credentials.get(ENGINE_ENABLED_FIELDS["tavily"])),
        bocha_enabled=_as_flag(credentials.get(ENGINE_ENABLED_FIELDS["bocha"])),
        tavily_api_key_configured=_stored_secret(credentials, "tavily") is not None,
        bocha_api_key_configured=_stored_secret(credentials, "bocha") is not None,
        legacy_credentials_present=bool(credentials.get(LEGACY_CREDENTIALS_FIELD)),
    )


async def _get_global_config() -> ToolConfig | None:
    return await ToolConfig.filter(tool_name=WEB_SEARCH_TOOL_NAME, team_id=None).first()


async def _load_locked_config(conn) -> ToolConfig | None:
    """Lock the singleton row for the duration of a save transaction.

    PostgreSQL uses the same advisory key as the startup migration so secret
    updates cannot be lost to a concurrent cutover or administrator save.
    """
    postgres = conn.capabilities.dialect != "sqlite"
    if postgres:
        await conn.execute_query(f"SELECT pg_advisory_xact_lock({SAVE_LOCK_KEY})")
    query = ToolConfig.filter(tool_name=WEB_SEARCH_TOOL_NAME, team_id=None).using_db(
        conn
    )
    if postgres:
        query = query.select_for_update()
    return await query.first()


def _validate_consistency(credentials: dict[str, Any]) -> None:
    """Reject a configuration the runtime could not serve.

    Enabling every provider off is an explicit administrator shutoff and is
    allowed; the runtime then fails safely with a localized error.
    """
    enabled_engines = [
        engine
        for engine in ENGINE_ENABLED_FIELDS
        if _as_flag(credentials.get(ENGINE_ENABLED_FIELDS[engine]))
    ]
    for engine in enabled_engines:
        if _stored_secret(credentials, engine) is None:
            raise BusinessError(
                msg_key="web_search_engine_not_configured", engine=engine
            )

    default_engine = _stored_default_engine(credentials)
    if default_engine is None:
        raise BusinessError(msg_key="web_search_default_engine_invalid")
    if enabled_engines and default_engine not in enabled_engines:
        raise BusinessError(msg_key="web_search_default_engine_disabled")


async def get_web_search_config() -> WebSearchConfigOut:
    """Return the public site configuration; never decrypt or expose secrets."""
    config = await _get_global_config()
    return _to_output(_stored_credentials(config))


async def save_web_search_config(
    data: WebSearchConfigUpdate,
) -> WebSearchConfigOut:
    """Persist the site configuration.

    Omitted/``None`` secrets keep the stored ciphertext, ``""`` clears the
    secret, and any other value is encrypted before storage. Fields the
    service does not own — including every reserved ``_``-prefixed key — are
    copied through untouched.
    """
    async with in_transaction() as conn:
        config = await _load_locked_config(conn)
        if config is None:
            config = await ToolConfig.create(
                tool_name=WEB_SEARCH_TOOL_NAME,
                team_id=None,
                credentials={},
                using_db=conn,
            )

        credentials = _stored_credentials(config)
        credentials[DEFAULT_ENGINE_FIELD] = data.default_engine
        credentials[ENGINE_ENABLED_FIELDS["tavily"]] = _flag_value(data.tavily_enabled)
        credentials[ENGINE_ENABLED_FIELDS["bocha"]] = _flag_value(data.bocha_enabled)

        for engine, update_field in SECRET_UPDATE_FIELDS.items():
            value = getattr(data, update_field)
            if value is None:
                continue
            if value == "":
                credentials.pop(ENGINE_SECRET_FIELDS[engine], None)
            else:
                credentials[ENGINE_SECRET_FIELDS[engine]] = (
                    f"{ENCRYPTED_PREFIX}{encrypt_secret(value)}"
                )

        # The startup migration uses this marker to stay a no-op; a save is an
        # administrator decision and must carry the same marker forward.
        credentials[SITE_CONFIG_VERSION_FIELD] = SITE_CONFIG_VERSION
        _validate_consistency(credentials)

        config.credentials = credentials
        await config.save(using_db=conn)
    return _to_output(credentials)


async def get_web_search_runtime(
    engine: str = "auto",
) -> tuple[str, dict[str, str]]:
    """Resolve the site-selected provider and only that provider's secret.

    ``auto`` always means the administrator's explicit default. It is never
    inferred from which API keys happen to exist, and there is no provider
    fallback. Raises a localized :class:`BusinessError` when the site has not
    configured a usable provider.
    """
    config = await _get_global_config()
    if config is None:
        raise BusinessError(msg_key="web_search_not_configured")

    credentials = _stored_credentials(config)
    requested = (engine or "auto").strip().lower()

    if requested == "auto":
        resolved = _stored_default_engine(credentials)
        if resolved is None:
            raise BusinessError(msg_key="web_search_default_engine_invalid")
    elif requested in ENGINE_ENABLED_FIELDS:
        resolved = requested
    else:
        raise BusinessError(
            msg_key="web_search_unsupported_engine", search_engine=engine
        )

    if not _as_flag(credentials.get(ENGINE_ENABLED_FIELDS[resolved])):
        raise BusinessError(msg_key="web_search_engine_disabled", engine=resolved)

    stored = _stored_secret(credentials, resolved)
    if stored is None:
        raise BusinessError(msg_key="web_search_engine_not_configured", engine=resolved)

    return resolved, {ENGINE_SECRET_FIELDS[resolved]: _decrypt_stored_secret(stored)}
