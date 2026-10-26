"""Persistent approval policy layers for site, team and entrypoint scopes.

Each row stores one complete
:class:`~app.schemas.tool_approval.ToolApprovalPolicy` for one scope and
optionally one tool. Rows are read at execution time by
``app.services.tool_approval_policies.load_effective_policy_layers`` and
combined with the tool's own policy by ``app.services.tool_approvals``.

``scope_key`` is the canonical uniqueness key. It exists because SQL unique
indexes do not treat ``NULL`` columns as equal, so nullable
``(team_id, entrypoint_id, tool_id)`` alone could not prevent duplicate site
rows. ``version`` is bumped on every write and is part of the evaluated layer
label, which makes a policy change invalidate pending approvals at claim time.
"""

from __future__ import annotations

import string
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from tortoise import fields, models

from app.schemas.tool_approval_policy import (
    ToolApprovalEntrypointKind,
    ToolApprovalPolicyScope,
)

if TYPE_CHECKING:
    from .tool import Tool
    from .user import Team, User

_HEX_DIGITS = set(string.hexdigits)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX_DIGITS for char in value)


class ToolApprovalPolicyDefinition(models.Model):
    """One configured approval policy layer."""

    id = fields.UUIDField(primary_key=True, default=uuid4)

    scope = fields.CharEnumField(
        ToolApprovalPolicyScope, description="site, team or entrypoint scope"
    )
    scope_key = fields.CharField(
        max_length=200,
        unique=True,
        description="Canonical scope identity including the optional tool",
    )

    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_approval_policies",
        on_delete=fields.CASCADE,
        null=True,
        description="Owning team for team/entrypoint scopes",
    )
    team_id: UUID | None  # type: ignore[assignment]

    entrypoint_kind: fields.CharEnumField[ToolApprovalEntrypointKind] | None = (
        fields.CharEnumField(
            ToolApprovalEntrypointKind,
            null=True,
            description="Concrete entrypoint resource kind",
        )
    )
    entrypoint_id = fields.UUIDField(
        null=True, description="Stable Agent/Workflow/APIKey id inside the team"
    )

    tool: fields.ForeignKeyRelation["Tool"] | None = fields.ForeignKeyField(
        "models.Tool",
        related_name="approval_policy_layers",
        on_delete=fields.CASCADE,
        null=True,
        description="Tool this row targets; null means every tool in scope",
    )
    tool_id: UUID | None  # type: ignore[assignment]

    policy: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    policy_hash = fields.CharField(
        max_length=64, description="Canonical hash of the stored policy body"
    )
    version = fields.IntField(
        default=1, description="Write version; part of the layer label"
    )

    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_tool_approval_policies",
        on_delete=fields.SET_NULL,
        null=True,
        description="User that created this layer",
    )
    created_by_id: UUID | None  # type: ignore[assignment]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_approval_policies"
        ordering = ["scope", "scope_key"]

    def __str__(self) -> str:
        return f"{self.scope.value}:{self.scope_key}"

    def clean(self) -> None:
        """Guard obvious corruption before persistence."""
        if not self.scope_key or len(self.scope_key) > 200:
            raise ValueError("tool_approval_policy_scope_invalid")
        if self.scope == ToolApprovalPolicyScope.SITE:
            if self.team_id is not None or self.entrypoint_id is not None:
                raise ValueError("tool_approval_policy_scope_invalid")
        elif self.scope == ToolApprovalPolicyScope.TEAM:
            if (
                self.team_id is None
                or self.entrypoint_kind is not None
                or self.entrypoint_id is not None
            ):
                raise ValueError("tool_approval_policy_scope_invalid")
        elif self.scope == ToolApprovalPolicyScope.ENTRYPOINT:
            if (
                self.team_id is None
                or self.entrypoint_kind is None
                or self.entrypoint_id is None
            ):
                raise ValueError("tool_approval_policy_scope_invalid")
        if not _is_sha256(self.policy_hash):
            raise ValueError("approval_policy_invalid")
        if self.version < 1:
            raise ValueError("tool_approval_policy_version_invalid")


__all__ = ["ToolApprovalPolicyDefinition"]
