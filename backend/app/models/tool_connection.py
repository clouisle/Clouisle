"""Tool connection and delegation grant models.

Connections separate tool *definitions* from the *identity and secrets* used to
reach an external service. A connection is always bound to exactly one team
(site connections are global and have no team), never carries secrets in plain
text, and never becomes a substitute for tool access control or execution
approval.

Secret material lives in :attr:`ToolConnection.encrypted_config` (Fernet token
of the declared credential fields). Only ``secret_fields`` — names, never
values — is safe to expose to clients.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from tortoise import fields, models

if TYPE_CHECKING:
    from .tool import Tool
    from .user import Team, User


class ToolConnectionScope(str, Enum):
    """Who the external account belongs to."""

    USER = "user"  # Personal account; owner_user_id is mandatory
    TEAM = "team"  # Shared team service account
    SITE = "site"  # Site-managed account; cannot be overridden by tool editors


class ToolConnectionStatus(str, Enum):
    """Lifecycle state of a connection."""

    ACTIVE = "active"  # Usable
    REVOKED = "revoked"  # Permanently unusable; grants are revoked with it
    REAUTH_REQUIRED = "reauth_required"  # Stored secrets no longer usable


class ConnectionEntrypointType(str, Enum):
    """Non-interactive entrypoint that may be delegated a connection."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    API_KEY = "api_key"
    SCHEDULE = "schedule"  # Cron-triggered workflow; entrypoint_id is the workflow id
    CHANNEL = "channel"
    EMBED = "embed"  # Public embed surface; entrypoint_id is the agent id


class ToolConnection(models.Model):
    """A configured external identity for a tool definition or builtin tool."""

    id = fields.UUIDField(primary_key=True, default=uuid4)

    # Team isolation. Personal and team connections are always team-scoped;
    # only site connections are global (team_id is None).
    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_connections",
        on_delete=fields.CASCADE,
        null=True,
        description="Owning team (NULL only for site scope)",
    )
    team_id: UUID | None  # type: ignore[assignment]

    # Exactly one of tool_id / builtin_tool_key identifies the service.
    tool: fields.ForeignKeyRelation["Tool"] | None = fields.ForeignKeyField(
        "models.Tool",
        related_name="connections",
        on_delete=fields.CASCADE,
        null=True,
        description="Tool definition this connection serves",
    )
    tool_id: UUID | None  # type: ignore[assignment]
    builtin_tool_key = fields.CharField(
        max_length=100,
        null=True,
        description="Stable builtin tool key when no Tool row exists",
    )

    scope = fields.CharEnumField(
        ToolConnectionScope, description="Who owns the external account"
    )
    owner_user: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="owned_tool_connections",
        on_delete=fields.CASCADE,
        null=True,
        description="Required for scope=user; administrator cannot stand in for it",
    )
    owner_user_id: UUID | None  # type: ignore[assignment]

    name = fields.CharField(max_length=100, description="Display name")
    account_label = fields.CharField(
        max_length=150,
        null=True,
        description="Non-secret external account label (e.g. e-mail or handle)",
    )

    # Secret storage: Fernet ciphertext of the declared credential field map.
    # Never select this into client DTOs, approval payloads or run events.
    encrypted_config = fields.TextField(
        default="", description="Encrypted credential fields (Fernet token)"
    )
    secret_fields: list[str] = fields.JSONField(
        default=list, description="Names of credential fields that are set"
    )  # type: ignore[assignment]
    secret_version = fields.IntField(
        default=1,
        description="Bumped whenever secrets or account identity change",
    )

    status = fields.CharEnumField(
        ToolConnectionStatus,
        default=ToolConnectionStatus.ACTIVE,
        description="Lifecycle state",
    )

    # Default selection. default_slot is NULL unless this is the default; its
    # uniqueness (team + service + owner scope) is enforced by the database.
    is_default = fields.BooleanField(default=False)
    default_slot = fields.CharField(
        max_length=255,
        null=True,
        unique=True,
        description="Active default marker; NULL when not default",
    )

    last_used_at = fields.DatetimeField(null=True)

    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_tool_connections",
        on_delete=fields.SET_NULL,
        null=True,
    )
    created_by_id: UUID | None  # type: ignore[assignment]

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_connections"
        ordering = ["-updated_at"]
        indexes = [
            ("team", "tool"),
            ("team", "builtin_tool_key"),
            ("owner_user", "is_default"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.scope}, team={self.team_id})"

    @property
    def is_usable(self) -> bool:
        return self.status == ToolConnectionStatus.ACTIVE

    @property
    def service_key(self) -> str:
        """Stable identity of the tool definition this connection serves."""
        if self.tool_id:
            return f"tool:{self.tool_id}"
        if self.builtin_tool_key:
            return f"builtin:{self.builtin_tool_key}"
        # Fail closed instead of inventing a service identity.
        raise ValueError("tool_connection_service_identity_missing")

    def validate_invariants(self) -> None:
        """Enforce scope/owner/team consistency before any write.

        Kept explicit (rather than in ``save``) so batch tooling cannot create
        ambiguous rows silently; every service write calls this first.
        """
        has_tool = self.tool_id is not None
        has_builtin = bool(self.builtin_tool_key)
        if has_tool == has_builtin:
            raise ValueError("tool_connection_service_identity_invalid")

        if self.scope == ToolConnectionScope.USER:
            if self.owner_user_id is None:
                raise ValueError("tool_connection_owner_required")
            if self.team_id is None:
                raise ValueError("tool_connection_team_required")
        elif self.scope == ToolConnectionScope.TEAM:
            if self.owner_user_id is not None:
                raise ValueError("tool_connection_owner_not_allowed")
            if self.team_id is None:
                raise ValueError("tool_connection_team_required")
        elif self.scope == ToolConnectionScope.SITE:
            if self.owner_user_id is not None:
                raise ValueError("tool_connection_owner_not_allowed")
            if self.team_id is not None:
                raise ValueError("tool_connection_team_not_allowed")
        else:  # pragma: no cover - CharEnumField guards this in practice
            raise ValueError("tool_connection_scope_invalid")

        if len(set(self.secret_fields or [])) != len(self.secret_fields or []):
            raise ValueError("tool_connection_secret_fields_duplicate")
        if self.is_default and not self.default_slot:
            raise ValueError("tool_connection_default_slot_required")
        if not self.is_default and self.default_slot:
            raise ValueError("tool_connection_default_slot_without_flag")


class ConnectionGrant(models.Model):
    """Explicit owner authorization for a non-interactive entrypoint.

    A grant is bound to one entrypoint, one team (or site-wide), and a concrete
    operation allow-list. Revocation and expiry are evaluated on every resolve;
    copying an entrypoint never copies its grants.
    """

    id = fields.UUIDField(primary_key=True, default=uuid4)

    connection: fields.ForeignKeyRelation["ToolConnection"] = fields.ForeignKeyField(
        "models.ToolConnection",
        related_name="grants",
        on_delete=fields.CASCADE,
        description="Delegated connection",
    )
    connection_id: UUID  # type: ignore[assignment]

    granted_by: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="tool_connection_grants_granted",
        on_delete=fields.CASCADE,
        description="Must be the personal connection owner for scope=user",
    )
    granted_by_id: UUID  # type: ignore[assignment]

    entrypoint_type = fields.CharEnumField(
        ConnectionEntrypointType, description="Entrypoint category"
    )
    entrypoint_id = fields.CharField(
        max_length=100, description="Stable identifier of the entrypoint"
    )
    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_connection_grants",
        on_delete=fields.CASCADE,
        null=True,
        description="Team the entrypoint runs in (NULL = site-wide)",
    )
    team_id: UUID | None  # type: ignore[assignment]

    allowed_operations: list[str] = fields.JSONField(
        default=list,
        description='Explicit operation allow-list; "*" means every operation',
    )  # type: ignore[assignment]

    expires_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True)
    revoked_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="tool_connection_grants_revoked",
        on_delete=fields.SET_NULL,
        null=True,
    )
    revoked_by_id: UUID | None  # type: ignore[assignment]
    version = fields.IntField(
        default=1, description="Monotonic version for approval binding"
    )

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "connection_grants"
        ordering = ["-created_at"]
        indexes = [
            ("connection", "entrypoint_type", "entrypoint_id"),
            ("team", "entrypoint_type", "entrypoint_id"),
        ]

    def __str__(self) -> str:
        return (
            f"grant {self.id} {self.entrypoint_type}:{self.entrypoint_id} "
            f"-> connection {self.connection_id}"
        )

    def is_active(self, now: datetime | None = None) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is None:
            return True
        reference = now or datetime.now(timezone.utc)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > reference

    def allows_operation(self, operation: str | None) -> bool:
        """Fail closed when the caller cannot name the operation."""
        if not operation:
            return False
        operations = set(self.allowed_operations or [])
        return "*" in operations or operation in operations

    def validate_invariants(self) -> None:
        if not self.entrypoint_id or not self.entrypoint_id.strip():
            raise ValueError("tool_connection_grant_entrypoint_required")
        operations = [op.strip() for op in (self.allowed_operations or [])]
        if not operations or any(not op for op in operations):
            raise ValueError("tool_connection_grant_operations_required")
        if len(set(operations)) != len(operations):
            raise ValueError("tool_connection_grant_operations_duplicate")
        if len(operations) > 200:
            raise ValueError("tool_connection_grant_operations_too_many")
        if any(len(op) > 200 for op in operations):
            raise ValueError("tool_connection_grant_operations_too_long")
        if self.expires_at is not None:
            expires_at = self.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("tool_connection_grant_expired")
        if self.revoked_at is not None and self.revoked_by_id is None:
            raise ValueError("tool_connection_grant_revoker_required")


__all__: list[str] = [
    "ConnectionEntrypointType",
    "ConnectionGrant",
    "ToolConnection",
    "ToolConnectionScope",
    "ToolConnectionStatus",
]
