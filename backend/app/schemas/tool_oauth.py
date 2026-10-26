"""Schemas for tool OAuth provider configuration and start/status APIs.

Secrets are write-only inputs (``OAuthStartRequest.client_secret``) or are
never accepted here at all. Responses expose only non-secret metadata: no
access tokens, refresh tokens, PKCE verifiers or client secrets.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tool_oauth import (
    ToolOAuthClientAuthMethod,
    ToolOAuthProviderKind,
)

MAX_OAUTH_URL_LENGTH = 2000
MAX_OAUTH_CLIENT_ID_LENGTH = 500
MAX_OAUTH_CLIENT_SECRET_LENGTH = 8192
MAX_OAUTH_SCOPES = 50
MAX_OAUTH_SCOPE_LENGTH = 200
MAX_OAUTH_EXTRA_PARAMS = 20
MAX_OAUTH_EXTRA_PARAM_LENGTH = 500
MAX_REDIRECT_PATH_LENGTH = 500

_SCOPE_PATTERN = re.compile(r"^[\x21-\x7e]{1,200}$")
_PARAM_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")

# Parameters the adapter computes itself; provider config must never override
# them (state, PKCE, redirect URI and client identity are security-sensitive).
RESERVED_AUTHORIZATION_PARAMS = frozenset(
    {
        "response_type",
        "client_id",
        "redirect_uri",
        "scope",
        "state",
        "code_challenge",
        "code_challenge_method",
        "resource",
    }
)
RESERVED_TOKEN_PARAMS = frozenset(
    {
        "grant_type",
        "code",
        "redirect_uri",
        "client_id",
        "client_secret",
        "code_verifier",
        "refresh_token",
        "resource",
    }
)

# Only these relative frontend paths may receive the final browser redirect.
ALLOWED_REDIRECT_PATH_PREFIXES = ("/app", "/settings", "/tools")


def _validate_https_url(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_OAUTH_URL_LENGTH:
        raise ValueError(f"{field_name}_invalid")
    parsed = urlsplit(cleaned)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"{field_name}_must_be_https")
    return cleaned


def _validate_scopes(value: list[str]) -> list[str]:
    if len(value) > MAX_OAUTH_SCOPES:
        raise ValueError("oauth_scopes_too_many")
    cleaned: list[str] = []
    for scope in value:
        normalized = (scope or "").strip()
        if not _SCOPE_PATTERN.fullmatch(normalized):
            raise ValueError("oauth_scope_invalid")
        cleaned.append(normalized)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("oauth_scopes_duplicate")
    return cleaned


def _validate_extra_params(
    value: dict[str, str], *, reserved: frozenset[str]
) -> dict[str, str]:
    if len(value) > MAX_OAUTH_EXTRA_PARAMS:
        raise ValueError("oauth_extra_params_too_many")
    cleaned: dict[str, str] = {}
    for name, raw in value.items():
        if not _PARAM_NAME_PATTERN.fullmatch(name or ""):
            raise ValueError("oauth_extra_param_name_invalid")
        if name in reserved:
            raise ValueError("oauth_extra_param_reserved")
        if not isinstance(raw, str) or len(raw) > MAX_OAUTH_EXTRA_PARAM_LENGTH:
            raise ValueError("oauth_extra_param_value_invalid")
        cleaned[name] = raw
    return cleaned


def validate_redirect_path(value: str | None) -> str | None:
    """Allow only same-origin frontend paths from a fixed allowlist."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_REDIRECT_PATH_LENGTH:
        raise ValueError("oauth_redirect_path_invalid")
    if (
        not cleaned.startswith("/")
        or cleaned.startswith("//")
        or "\\" in cleaned
        or any(ord(char) < 0x20 for char in cleaned)
    ):
        raise ValueError("oauth_redirect_path_invalid")
    parsed = urlsplit(cleaned)
    if parsed.scheme or parsed.netloc:
        raise ValueError("oauth_redirect_path_invalid")
    path = parsed.path.rstrip("/") or "/"
    if not any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in ALLOWED_REDIRECT_PATH_PREFIXES
    ):
        raise ValueError("oauth_redirect_path_not_allowed")
    return cleaned


class McpOAuthConfig(BaseModel):
    """Non-secret OAuth settings for an MCP server definition.

    Stored under ``Tool.mcp_config["oauth"]`` by the tool editor. Client secrets
    are never part of this object; they are write-only provider inputs managed
    by tool administrators.
    """

    model_config = ConfigDict(extra="forbid")

    authorization_server: str | None = Field(
        default=None,
        description="AS issuer override when protected-resource discovery is unavailable",
    )
    resource: str | None = Field(
        default=None,
        description="RFC 8707 resource indicator; defaults to the MCP server URL",
    )
    scopes: list[str] = Field(default_factory=list)
    client_id: str | None = Field(default=None, max_length=MAX_OAUTH_CLIENT_ID_LENGTH)
    use_dcr: bool = Field(
        default=True,
        description="Allow RFC 7591 dynamic client registration when no client_id is set",
    )
    token_endpoint_auth_method: ToolOAuthClientAuthMethod = (
        ToolOAuthClientAuthMethod.NONE
    )
    extra_authorization_params: dict[str, str] = Field(default_factory=dict)
    extra_token_params: dict[str, str] = Field(default_factory=dict)

    @field_validator("authorization_server", "resource")
    @classmethod
    def _validate_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_https_url(value, field_name="oauth_url")

    @field_validator("client_id")
    @classmethod
    def _strip_client_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str]) -> list[str]:
        return _validate_scopes(value)

    @field_validator("extra_authorization_params")
    @classmethod
    def _authorization_params(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_extra_params(value, reserved=RESERVED_AUTHORIZATION_PARAMS)

    @field_validator("extra_token_params")
    @classmethod
    def _token_params(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_extra_params(value, reserved=RESERVED_TOKEN_PARAMS)


class HttpOAuth2Config(BaseModel):
    """Configured OAuth 2.0 provider for an HTTP tool (``http_config["oauth2"]``).

    PKCE S256 is mandatory; there is no switch to disable it.
    """

    model_config = ConfigDict(extra="forbid")

    issuer: str | None = Field(
        default=None,
        description="Authorization server identifier; defaults to the authorization endpoint origin",
    )
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None = None
    client_id: str = Field(min_length=1, max_length=MAX_OAUTH_CLIENT_ID_LENGTH)
    scopes: list[str] = Field(default_factory=list)
    token_endpoint_auth_method: ToolOAuthClientAuthMethod = (
        ToolOAuthClientAuthMethod.NONE
    )
    extra_authorization_params: dict[str, str] = Field(default_factory=dict)
    extra_token_params: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "revocation_endpoint",
    )
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_https_url(value, field_name="oauth_url")

    @field_validator("scopes")
    @classmethod
    def _scopes(cls, value: list[str]) -> list[str]:
        return _validate_scopes(value)

    @field_validator("extra_authorization_params")
    @classmethod
    def _authorization_params(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_extra_params(value, reserved=RESERVED_AUTHORIZATION_PARAMS)

    @field_validator("extra_token_params")
    @classmethod
    def _token_params(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_extra_params(value, reserved=RESERVED_TOKEN_PARAMS)


class OAuthStartRequest(BaseModel):
    """Start an authorization-code flow for an existing connection."""

    model_config = ConfigDict(extra="forbid")

    redirect_path: str | None = Field(
        default=None,
        max_length=MAX_REDIRECT_PATH_LENGTH,
        description="Allowlisted relative frontend path to return to",
    )
    client_secret: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_OAUTH_CLIENT_SECRET_LENGTH,
        repr=False,
        description=(
            "Write-only client secret for a pre-registered confidential client. "
            "Requires tool write access; never returned or logged."
        ),
    )

    @field_validator("redirect_path")
    @classmethod
    def _redirect_path(cls, value: str | None) -> str | None:
        return validate_redirect_path(value)


class OAuthStartOut(BaseModel):
    """Authorization URL the frontend opens in a browser/popup."""

    authorization_url: str
    state: str
    expires_at: datetime
    provider_kind: ToolOAuthProviderKind
    connection_id: UUID


class OAuthConnectionStatusOut(BaseModel):
    """Secret-free OAuth state for one connection."""

    connection_id: UUID
    provider_kind: ToolOAuthProviderKind | None
    provider_configured: bool
    authorized: bool
    needs_reauth: bool
    status: str
    account_label: str | None
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    client_id: str | None = None


class OAuthDisconnectOut(BaseModel):
    """Local revocation result plus the bounded remote attempt."""

    connection_id: UUID
    local_revoked: bool
    remote_revocation: str
    needs_reauth: bool


__all__ = [
    "ALLOWED_REDIRECT_PATH_PREFIXES",
    "HttpOAuth2Config",
    "McpOAuthConfig",
    "OAuthConnectionStatusOut",
    "OAuthDisconnectOut",
    "OAuthStartOut",
    "OAuthStartRequest",
    "RESERVED_AUTHORIZATION_PARAMS",
    "RESERVED_TOKEN_PARAMS",
    "validate_redirect_path",
]
