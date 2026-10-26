"""OAuth provider state and authorization-flow models for tool connections.

Secrets never live in these tables in clear text:

* ``ToolOAuthProvider.client_secret_encrypted`` is a Fernet token produced by
  the shared integration credential helper.
* ``ToolOAuthFlow`` stores only a SHA-256 hash of the one-time ``state`` value;
  the PKCE verifier is encrypted.
* Access/refresh tokens are written into the existing
  ``ToolConnection.encrypted_config`` container, not here.

Provider rows are keyed by tool + provider kind + authorization server. A
personal user may start a flow for their own connection but can never overwrite
a provider client secret: writes to provider credentials require tool write
access in :mod:`app.services.tool_oauth`.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from .tool import Tool
    from .tool_connection import ToolConnection
    from .user import Team, User


class ToolOAuthProviderKind(str, Enum):
    """Which tool protocol the provider configuration belongs to."""

    MCP = "mcp"
    HTTP = "http"


class ToolOAuthClientAuthMethod(str, Enum):
    """How the client authenticates at the token endpoint."""

    NONE = "none"
    CLIENT_SECRET_BASIC = "client_secret_basic"
    CLIENT_SECRET_POST = "client_secret_post"


class ToolOAuthProvider(models.Model):
    """Discovered or configured OAuth authorization server for one tool.

    One row exists per (tool, protocol, authorization server). Discovery
    metadata is non-secret and stored for auditability; the client secret is
    encrypted and never returned by an API.
    """

    id = fields.UUIDField(primary_key=True)

    tool: fields.ForeignKeyRelation["Tool"] = fields.ForeignKeyField(
        "models.Tool",
        related_name="oauth_providers",
        on_delete=fields.CASCADE,
        description="Tool definition this provider serves",
    )
    tool_id: UUID  # type: ignore[assignment]

    provider_kind = fields.CharEnumField(
        ToolOAuthProviderKind, description="mcp or http"
    )
    authorization_server = fields.CharField(
        max_length=500,
        description="Issuer / authorization-server identifier used as the unique key",
    )
    issuer = fields.CharField(max_length=500, null=True)
    resource = fields.CharField(
        max_length=1000,
        null=True,
        description="RFC 8707 resource indicator (MCP)",
    )

    authorization_endpoint = fields.CharField(max_length=2000)
    token_endpoint = fields.CharField(max_length=2000)
    registration_endpoint = fields.CharField(max_length=2000, null=True)
    userinfo_endpoint = fields.CharField(max_length=2000, null=True)
    revocation_endpoint = fields.CharField(max_length=2000, null=True)

    client_id = fields.CharField(
        max_length=500,
        description="OAuth client id (public value)",
    )
    client_secret_encrypted = fields.TextField(
        default="",
        description="Fernet ciphertext of the OAuth client secret",
    )
    token_endpoint_auth_method = fields.CharEnumField(
        ToolOAuthClientAuthMethod,
        default=ToolOAuthClientAuthMethod.NONE,
        description="Client authentication method at the token endpoint",
    )

    scopes: list[str] = fields.JSONField(default=list)  # type: ignore[assignment]
    code_challenge_methods: list[str] = fields.JSONField(default=list)  # type: ignore[assignment]
    authorization_params: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    token_params: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    metadata: dict = fields.JSONField(default=dict)  # type: ignore[assignment]

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_oauth_providers"
        unique_together = [
            ("tool", "provider_kind", "authorization_server"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.provider_kind}:{self.authorization_server}"


class ToolOAuthFlow(models.Model):
    """A short-lived, one-time authorization-code flow.

    ``state_hash`` is the only lookup key available to the callback; the raw
    state value is never persisted. ``code_verifier_encrypted`` is a Fernet
    token. ``expected_secret_version`` binds the flow to the connection state
    the user started from, so an unrelated credential edit cannot be
    overwritten by a stale callback.
    """

    id = fields.UUIDField(primary_key=True)

    state_hash = fields.CharField(
        max_length=64,
        unique=True,
        description="SHA-256 hex digest of the one-time state value",
    )

    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="tool_oauth_flows",
        on_delete=fields.CASCADE,
        description="Logged-in user who started the flow",
    )
    user_id: UUID  # type: ignore[assignment]

    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_oauth_flows",
        on_delete=fields.CASCADE,
        null=True,
        description="Owning team (NULL only for site connections)",
    )
    team_id: UUID | None  # type: ignore[assignment]

    tool: fields.ForeignKeyRelation["Tool"] = fields.ForeignKeyField(
        "models.Tool",
        related_name="oauth_flows",
        on_delete=fields.CASCADE,
    )
    tool_id: UUID  # type: ignore[assignment]

    connection: fields.ForeignKeyRelation["ToolConnection"] = fields.ForeignKeyField(
        "models.ToolConnection",
        related_name="oauth_flows",
        on_delete=fields.CASCADE,
        description="Connection the resulting tokens belong to",
    )
    connection_id: UUID  # type: ignore[assignment]

    provider: fields.ForeignKeyRelation["ToolOAuthProvider"] = fields.ForeignKeyField(
        "models.ToolOAuthProvider",
        related_name="flows",
        on_delete=fields.CASCADE,
    )
    provider_id: UUID  # type: ignore[assignment]

    provider_kind = fields.CharEnumField(ToolOAuthProviderKind)

    redirect_uri = fields.CharField(max_length=2000)
    redirect_path = fields.CharField(
        max_length=500,
        null=True,
        description="Allowlisted relative frontend return path",
    )
    scopes: list[str] = fields.JSONField(default=list)  # type: ignore[assignment]
    resource = fields.CharField(max_length=1000, null=True)

    code_verifier_encrypted = fields.TextField(
        description="Fernet ciphertext of the PKCE code_verifier"
    )

    expected_secret_version = fields.IntField(
        description="Connection.secret_version observed when the flow started"
    )
    expires_at = fields.DatetimeField()
    consumed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tool_oauth_flows"
        indexes = [
            ("connection", "expires_at"),
            ("user", "created_at"),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"oauth-flow:{self.id}"


__all__ = [
    "ToolOAuthClientAuthMethod",
    "ToolOAuthFlow",
    "ToolOAuthProvider",
    "ToolOAuthProviderKind",
]
