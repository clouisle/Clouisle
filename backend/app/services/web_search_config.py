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
from urllib.parse import urlparse, urlunparse

from tortoise.transactions import in_transaction

from app.core.network_security import ensure_external_http_url_allowed
from app.integrations.credentials import (
    IntegrationSecretError,
    decrypt_secret,
    encrypt_secret,
)
from app.models.tool_config import ToolConfig
from app.schemas.response import BusinessError
from app.schemas.web_search import (
    BASE_URL_MAX_LENGTH,
    WEB_SEARCH_ENGINES,
    WebSearchConfigOut,
    WebSearchConfigUpdate,
)

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL_NAME = "web_search"
ENCRYPTED_PREFIX = "enc:v1:"
DEFAULT_ENGINE_FIELD = "default_engine"
LEGACY_CREDENTIALS_FIELD = "_legacy_credentials"
SEARXNG_BASE_URL_FIELD = "SEARXNG_BASE_URL"
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
    "searxng": "searxng_enabled",
    "deepseek": "deepseek_enabled",
}
ENGINE_SECRET_FIELDS: dict[str, str] = {
    "tavily": "TAVILY_API_KEY",
    "bocha": "BOCHA_API_KEY",
    "searxng": "SEARXNG_AUTH_TOKEN",
    "deepseek": "DEEPSEEK_API_KEY",
}
# SearXNG's bearer token is optional; the other providers cannot work without
# their API key.
ENGINE_REQUIRED_SECRETS: frozenset[str] = frozenset({"tavily", "bocha", "deepseek"})
# Update-field name for each provider secret.
SECRET_UPDATE_FIELDS: dict[str, str] = {
    "tavily": "tavily_api_key",
    "bocha": "bocha_api_key",
    "searxng": "searxng_auth_token",
    "deepseek": "deepseek_api_key",
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


def _stored_searxng_base_url(credentials: dict[str, Any]) -> str | None:
    value = credentials.get(SEARXNG_BASE_URL_FIELD)
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_searxng_base_url(value: str) -> str:
    """Validate the shape of a configured SearXNG root URL.

    The root may include a reverse-proxy subpath (``https://host/searxng``)
    but must not point at the search endpoint itself, and may not carry
    userinfo, query parameters, or a fragment. Only scheme/host validation
    happens here; DNS/private-target policy is enforced by
    :func:`validate_searxng_base_url`.
    """
    raw = (value or "").strip()
    if not raw or "\\" in raw or any(char.isspace() for char in raw):
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw):
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")
    try:
        parsed = urlparse(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or port is not None
        and not (1 <= port <= 65535)
    ):
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")
    if (
        "@" in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
    ):
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")

    path = parsed.path.rstrip("/")
    if path.lower().endswith("/search"):
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")

    normalized = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
    if len(normalized) > BASE_URL_MAX_LENGTH:
        raise BusinessError(msg_key="web_search_searxng_base_url_invalid")
    return normalized


async def validate_searxng_base_url(value: str) -> str:
    """Normalize and SSRF-check a SearXNG root URL for save and every request."""
    normalized = normalize_searxng_base_url(value)
    await ensure_external_http_url_allowed(normalized)
    return normalized


def build_searxng_search_url(base_url: str) -> str:
    """Append the SearXNG JSON search endpoint while keeping reverse-proxy paths."""
    return f"{base_url.rstrip('/')}/search"


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
        searxng_enabled=_as_flag(credentials.get(ENGINE_ENABLED_FIELDS["searxng"])),
        deepseek_enabled=_as_flag(credentials.get(ENGINE_ENABLED_FIELDS["deepseek"])),
        tavily_api_key_configured=_stored_secret(credentials, "tavily") is not None,
        bocha_api_key_configured=_stored_secret(credentials, "bocha") is not None,
        deepseek_api_key_configured=_stored_secret(credentials, "deepseek") is not None,
        searxng_base_url=_stored_searxng_base_url(credentials) or "",
        searxng_auth_token_configured=(
            _stored_secret(credentials, "searxng") is not None
        ),
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
        if (
            engine in ENGINE_REQUIRED_SECRETS
            and _stored_secret(credentials, engine) is None
        ):
            raise BusinessError(
                msg_key="web_search_engine_not_configured", engine=engine
            )

    if _as_flag(credentials.get(ENGINE_ENABLED_FIELDS["searxng"])):
        base_url = _stored_searxng_base_url(credentials)
        if base_url is None:
            raise BusinessError(msg_key="web_search_searxng_base_url_required")
        if _stored_secret(credentials, "searxng") and not base_url.lower().startswith(
            "https://"
        ):
            raise BusinessError(msg_key="web_search_searxng_https_required")

    default_engine = _stored_default_engine(credentials)
    if default_engine is None:
        raise BusinessError(msg_key="web_search_default_engine_invalid")
    if enabled_engines and default_engine not in enabled_engines:
        raise BusinessError(msg_key="web_search_default_engine_disabled")


def _normalized_for_comparison(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return normalize_searxng_base_url(value)
    except BusinessError:
        # An unusable stored URL cannot be equivalent to a valid new one.
        return None


def _require_token_choice_for_url_change(
    previous: dict[str, Any],
    next_base_url: str | None,
    data: WebSearchConfigUpdate,
) -> None:
    """Never replay an existing bearer token against a different origin/path.

    Changing the configured SearXNG URL while a token is already stored
    requires the administrator to explicitly replace or clear that token in
    the same request.
    """
    if data.searxng_base_url is None:
        return
    if _normalized_for_comparison(
        _stored_searxng_base_url(previous)
    ) == _normalized_for_comparison(next_base_url):
        return
    if _stored_secret(previous, "searxng") and data.searxng_auth_token is None:
        raise BusinessError(msg_key="web_search_searxng_token_confirmation_required")


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
        previous_credentials = dict(credentials)
        credentials[DEFAULT_ENGINE_FIELD] = data.default_engine
        credentials[ENGINE_ENABLED_FIELDS["tavily"]] = _flag_value(data.tavily_enabled)
        credentials[ENGINE_ENABLED_FIELDS["bocha"]] = _flag_value(data.bocha_enabled)
        credentials[ENGINE_ENABLED_FIELDS["searxng"]] = _flag_value(
            data.searxng_enabled
        )
        credentials[ENGINE_ENABLED_FIELDS["deepseek"]] = _flag_value(
            data.deepseek_enabled
        )

        if data.searxng_base_url is not None:
            if data.searxng_base_url == "":
                credentials.pop(SEARXNG_BASE_URL_FIELD, None)
            else:
                credentials[SEARXNG_BASE_URL_FIELD] = normalize_searxng_base_url(
                    data.searxng_base_url
                )

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

        _require_token_choice_for_url_change(
            previous_credentials,
            _stored_searxng_base_url(credentials),
            data,
        )

        # The startup migration uses this marker to stay a no-op; a save is an
        # administrator decision and must carry the same marker forward.
        credentials[SITE_CONFIG_VERSION_FIELD] = SITE_CONFIG_VERSION
        _validate_consistency(credentials)

        if _as_flag(credentials.get(ENGINE_ENABLED_FIELDS["searxng"])):
            # Validate on save as well as on every request.
            credentials[SEARXNG_BASE_URL_FIELD] = await validate_searxng_base_url(
                _stored_searxng_base_url(credentials) or ""
            )

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

    if resolved == "searxng":
        base_url = _stored_searxng_base_url(credentials)
        if base_url is None:
            raise BusinessError(
                msg_key="web_search_engine_not_configured", engine="searxng"
            )
        stored_token = _stored_secret(credentials, "searxng")
        if stored_token and not base_url.lower().startswith("https://"):
            raise BusinessError(msg_key="web_search_searxng_https_required")
        # SSRF policy is re-evaluated on every request, not just at save time.
        validated = await validate_searxng_base_url(base_url)
        runtime_config = {"SEARXNG_BASE_URL": validated}
        if stored_token:
            runtime_config["SEARXNG_AUTH_TOKEN"] = _decrypt_stored_secret(stored_token)
        return "searxng", runtime_config

    stored = _stored_secret(credentials, resolved)
    if stored is None:
        raise BusinessError(msg_key="web_search_engine_not_configured", engine=resolved)

    return resolved, {ENGINE_SECRET_FIELDS[resolved]: _decrypt_stored_secret(stored)}
