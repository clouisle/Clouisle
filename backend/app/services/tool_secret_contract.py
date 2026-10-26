"""Write-time contract for tool definitions: definitions declare fields, values live in connections.

Tool definitions may declare credential *fields* in ``connection_fields`` and
reference them from HTTP/MCP/database configuration as ``{{field}}``
placeholders. Actual secret values belong to encrypted ``ToolConnection`` rows
and must never be accepted by the tool create/update/duplicate/import paths.

This module is intentionally pure: it classifies payloads and enforces the rule
without touching the database, so request validation can never invoke the
startup migration. The sensitive-header and template rules mirror
``app.core.tool_secret_migration``; keep them in sync if that classification
changes.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.schemas.response import BusinessError, ResponseCode

# Headers the legacy migration treats as credential carriers.
SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
    }
)

# Field-name tokens that identify a credential. Package import/export already
# classifies these fragments as secrets; write validation uses the same idea.
SENSITIVE_FIELD_FRAGMENTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
)

_FIELD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# Structural keys whose value is a URL that describes *where* an OAuth flow
# talks, not a credential (``token_endpoint`` is not a token).
_URL_KEY_SUFFIXES = ("endpoint", "issuer", "server", "url", "uri", "host")


@dataclass(frozen=True, slots=True)
class ToolSecretViolation:
    """One reason a tool definition cannot be written as submitted."""

    path: str
    rule: str
    detail: str | None = None

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.path}:{self.rule}"


def is_template_value(value: Any) -> bool:
    """True when a value is a ``{{field}}`` reference rather than a literal."""
    return isinstance(value, str) and "{{" in value and "}}" in value


def template_field_names(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return _PLACEHOLDER_PATTERN.findall(value)


def _normalized_name(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")


def _looks_like_credential_name(name: Any) -> bool:
    """Classify a header/env/query key without flagging e.g. TOKENIZERS_PARALLELISM."""
    normalized = _normalized_name(name)
    if not normalized:
        return False
    if normalized in SENSITIVE_HEADER_NAMES or normalized in SENSITIVE_FIELD_FRAGMENTS:
        return True
    for fragment in SENSITIVE_FIELD_FRAGMENTS:
        if fragment in {"token"}:
            # Bare "token" is only sensitive as a whole word (avoids tokenizers).
            if re.search(rf"(^|_){fragment}(_|$)", normalized):
                return True
        elif fragment in normalized:
            return True
    return False


def _is_url_key(name: Any) -> bool:
    normalized = _normalized_name(name)
    return any(
        normalized.endswith(f"_{suffix}") or normalized == suffix
        for suffix in _URL_KEY_SUFFIXES
    )


def _url_has_credentials(value: Any) -> bool:
    """Detect literal userinfo/credential query params in a connection URL."""
    if not isinstance(value, str) or not value.strip() or is_template_value(value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return True  # fail closed on an unparseable URL
    if parsed.password:
        return True
    if parsed.username and _looks_like_credential_name(parsed.username):
        return True
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if item and not is_template_value(item) and _looks_like_credential_name(key):
            return True
    return False


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return (
        value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        else ()
    )


def find_tool_secret_violations(
    *,
    credentials: Mapping[str, Any] | None = None,
    http_config: Mapping[str, Any] | None = None,
    mcp_config: Mapping[str, Any] | None = None,
    database_config: Mapping[str, Any] | None = None,
    connection_fields: Sequence[Mapping[str, Any]] | None = None,
) -> list[ToolSecretViolation]:
    """Return every inline secret / undeclared field in a tool write payload."""
    violations: list[ToolSecretViolation] = []

    if credentials:
        for name in credentials:
            violations.append(
                ToolSecretViolation(
                    path=f"credentials.{name}",
                    rule="inline_credentials",
                    detail=str(name),
                )
            )

    declared = {
        str(field.get("name"))
        for field in (connection_fields or ())
        if isinstance(field, Mapping) and field.get("name")
    }

    http = _mapping(http_config)
    headers = _mapping(http.get("headers"))
    for name, value in headers.items():
        if not value or is_template_value(value):
            continue
        if _looks_like_credential_name(name):
            violations.append(
                ToolSecretViolation(
                    path=f"http_config.headers.{name}",
                    rule="inline_secret",
                    detail=str(name),
                )
            )
    for name, value in _mapping(http.get("query_params")).items():
        if not value or is_template_value(value):
            continue
        if _looks_like_credential_name(name):
            violations.append(
                ToolSecretViolation(
                    path=f"http_config.query_params.{name}",
                    rule="inline_secret",
                    detail=str(name),
                )
            )
    if _url_has_credentials(http.get("url")):
        violations.append(
            ToolSecretViolation(path="http_config.url", rule="url_credentials")
        )

    mcp = _mapping(mcp_config)
    for name, value in _mapping(mcp.get("headers")).items():
        if not value or is_template_value(value):
            continue
        if _looks_like_credential_name(name):
            violations.append(
                ToolSecretViolation(
                    path=f"mcp_config.headers.{name}",
                    rule="inline_secret",
                    detail=str(name),
                )
            )
    for name, value in _mapping(mcp.get("env")).items():
        if not value or is_template_value(value):
            continue
        # Non-secret MCP env (LOG_LEVEL, NODE_ENV, ...) stays in the definition;
        # only values under credential-looking keys must move to a connection.
        if _looks_like_credential_name(name):
            violations.append(
                ToolSecretViolation(
                    path=f"mcp_config.env.{name}",
                    rule="inline_secret",
                    detail=str(name),
                )
            )
    if _url_has_credentials(mcp.get("url")):
        violations.append(
            ToolSecretViolation(path="mcp_config.url", rule="url_credentials")
        )

    database = _mapping(database_config)
    password = database.get("password")
    if password and not is_template_value(password):
        violations.append(
            ToolSecretViolation(
                path="database_config.password", rule="inline_secret", detail="password"
            )
        )
    if _url_has_credentials(database.get("url")):
        violations.append(
            ToolSecretViolation(path="database_config.url", rule="url_credentials")
        )

    # Every placeholder used in a credential slot must be declared so the
    # connection form can collect and validate it.
    placeholder_sites: Iterable[tuple[str, Any]] = (
        (f"http_config.headers.{name}", value) for name, value in headers.items()
    )
    placeholder_sites = (
        *placeholder_sites,
        *(
            (f"http_config.query_params.{name}", value)
            for name, value in _mapping(http.get("query_params")).items()
        ),
        ("http_config.url", http.get("url")),
        *(
            (f"mcp_config.headers.{name}", value)
            for name, value in _mapping(mcp.get("headers")).items()
        ),
        *(
            (f"mcp_config.env.{name}", value)
            for name, value in _mapping(mcp.get("env")).items()
        ),
        ("mcp_config.url", mcp.get("url")),
        ("database_config.password", database.get("password")),
        ("database_config.url", database.get("url")),
    )
    for path, value in placeholder_sites:
        for field_name in template_field_names(value):
            if field_name not in declared:
                violations.append(
                    ToolSecretViolation(
                        path=path,
                        rule="undeclared_connection_field",
                        detail=field_name,
                    )
                )

    seen: set[str] = set()
    for index, field in enumerate(connection_fields or ()):
        if not isinstance(field, Mapping):
            continue
        name = str(field.get("name") or "")
        if not name:
            continue
        if not _FIELD_NAME_PATTERN.fullmatch(name):
            violations.append(
                ToolSecretViolation(
                    path=f"connection_fields[{index}].name",
                    rule="invalid_connection_field",
                    detail=name,
                )
            )
        elif name in seen:
            violations.append(
                ToolSecretViolation(
                    path=f"connection_fields[{index}].name",
                    rule="duplicate_connection_field",
                    detail=name,
                )
            )
        seen.add(name)

    return violations


def enforce_tool_secret_contract(
    *,
    credentials: Mapping[str, Any] | None = None,
    http_config: Mapping[str, Any] | None = None,
    mcp_config: Mapping[str, Any] | None = None,
    database_config: Mapping[str, Any] | None = None,
    connection_fields: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """Raise ``tool_secret_inline_not_allowed`` for any contract violation."""
    violations = find_tool_secret_violations(
        credentials=credentials,
        http_config=http_config,
        mcp_config=mcp_config,
        database_config=database_config,
        connection_fields=connection_fields,
    )
    if not violations:
        return
    fields = sorted({violation.path for violation in violations})
    raise BusinessError(
        code=ResponseCode.BAD_REQUEST,
        msg_key="tool_secret_inline_not_allowed",
        status_code=400,
        fields=", ".join(fields),
    )


# ---------------------------------------------------------------------------
# Export sanitization
# ---------------------------------------------------------------------------


def _sanitize_config_value(value: Any, key: str | None = None) -> Any:
    """Copy a config value, dropping literal secrets and keeping placeholders."""
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for child_key, child_value in value.items():
            child_name = str(child_key)
            if (
                isinstance(child_value, str)
                and not is_template_value(child_value)
                and _looks_like_credential_name(child_name)
                and not (
                    _is_url_key(child_name) and not _url_has_credentials(child_value)
                )
            ):
                continue
            cleaned[child_key] = _sanitize_config_value(child_value, child_name)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_config_value(item, key) for item in value]
    return value


def sanitize_tool_configs_for_export(
    *,
    http_config: Mapping[str, Any] | None = None,
    mcp_config: Mapping[str, Any] | None = None,
    database_config: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return secret-free copies that still carry ``{{field}}`` references."""
    http = _sanitize_config_value(dict(http_config or {}))
    mcp = _sanitize_config_value(dict(mcp_config or {}))
    database = _sanitize_config_value(dict(database_config or {}))
    if isinstance(http, dict) and _url_has_credentials(http.get("url")):
        http.pop("url", None)
    if isinstance(mcp, dict) and _url_has_credentials(mcp.get("url")):
        mcp.pop("url", None)
    if isinstance(database, dict) and _url_has_credentials(database.get("url")):
        database.pop("url", None)
    return http, mcp, database


__all__ = [
    "SENSITIVE_FIELD_FRAGMENTS",
    "SENSITIVE_HEADER_NAMES",
    "ToolSecretViolation",
    "enforce_tool_secret_contract",
    "find_tool_secret_violations",
    "is_template_value",
    "sanitize_tool_configs_for_export",
    "template_field_names",
]
