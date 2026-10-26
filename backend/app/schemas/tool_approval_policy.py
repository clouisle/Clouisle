"""Typed DTOs for persistent site/team/entrypoint approval policy layers.

A layer is a stored :class:`~app.schemas.tool_approval.ToolApprovalPolicy`
attached to one scope:

* ``site`` — the security floor configured by site administrators; applies to
  every team and every tool.
* ``team`` — a team-enforced policy written by team owners/admins; applies to
  the team's tools and to tools shared with the team.
* ``entrypoint`` — an extra restriction attached to one concrete, stable
  entrypoint (Agent, Workflow or API Key) inside one team.

A scope may have both a generic row (``tool_id`` null) and one tool-specific
row. Both stay mandatory: the effective layer is their strictest combination
(deny > require_approval > allow, union of gates), so the tool-specific row can
tighten but never relax the generic row. Across scopes the evaluator keeps the
strictest decision and the union of approval gates, so a lower layer can only
tighten. There is no expression/script language: only decisions, gates and
operation overrides.

The definitions intentionally contain no secrets and no approver display
names; gate audiences are user ids and team roles, resolved by the approval
inbox against current membership.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    PolicySource,
    ToolApprovalPolicy,
)

MAX_SCOPE_KEY_LENGTH = 200


class ToolApprovalPolicyScope(str, Enum):
    """Where a stored policy layer applies."""

    SITE = "site"
    TEAM = "team"
    ENTRYPOINT = "entrypoint"


class ToolApprovalEntrypointKind(str, Enum):
    """Concrete entrypoint resources an entrypoint layer can bind to."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    API_KEY = "api_key"


class ToolApprovalPolicyCreateIn(BaseModel):
    """Create one policy layer. Scope fields are validated for consistency."""

    model_config = ConfigDict(extra="forbid")

    scope: ToolApprovalPolicyScope
    team_id: UUID | None = None
    entrypoint_kind: ToolApprovalEntrypointKind | None = None
    entrypoint_id: UUID | None = None
    tool_id: UUID | None = None
    policy: ToolApprovalPolicy

    @model_validator(mode="after")
    def _check_scope_fields(self) -> "ToolApprovalPolicyCreateIn":
        if self.scope == ToolApprovalPolicyScope.SITE:
            if self.team_id is not None:
                raise ValueError("tool_approval_policy_scope_invalid")
            if self.entrypoint_kind is not None or self.entrypoint_id is not None:
                raise ValueError("tool_approval_policy_scope_invalid")
            return self
        if self.scope == ToolApprovalPolicyScope.TEAM:
            if self.team_id is None:
                raise ValueError("tool_approval_policy_scope_invalid")
            if self.entrypoint_kind is not None or self.entrypoint_id is not None:
                raise ValueError("tool_approval_policy_scope_invalid")
            return self
        if (
            self.team_id is None
            or self.entrypoint_kind is None
            or self.entrypoint_id is None
        ):
            raise ValueError("tool_approval_policy_scope_invalid")
        return self


class ToolApprovalPolicyUpdateIn(BaseModel):
    """Replace one layer's policy body under optimistic concurrency control."""

    model_config = ConfigDict(extra="forbid")

    policy: ToolApprovalPolicy
    expected_version: int | None = Field(default=None, ge=1)


class ToolApprovalPolicyOut(BaseModel):
    """Secret-safe projection of one configured policy layer."""

    id: UUID
    scope: ToolApprovalPolicyScope
    team_id: UUID | None = None
    entrypoint_kind: ToolApprovalEntrypointKind | None = None
    entrypoint_id: UUID | None = None
    tool_id: UUID | None = None
    policy: ToolApprovalPolicy
    policy_hash: str
    version: int
    can_edit: bool
    configuration_error: str | None = None
    created_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ToolApprovalPolicyLayerOut(BaseModel):
    """One evaluated layer and whether the caller may change it."""

    source: PolicySource
    label: str | None = None
    version: int | None = None
    policy_hash: str | None = None
    can_edit: bool = False


class ToolApprovalPolicyEffectiveOut(BaseModel):
    """Server-composed effective policy for one tool operation."""

    operation: str
    decision: ApprovalDecision
    gates: tuple[ApprovalGate, ...] = ()
    policy_hash: str
    sources: tuple[str, ...] = ()
    configuration_error: str | None = None
    entrypoint_interactive: bool
    layers: tuple[ToolApprovalPolicyLayerOut, ...] = ()
    can_edit_team: bool = False


__all__ = [
    "MAX_SCOPE_KEY_LENGTH",
    "ToolApprovalEntrypointKind",
    "ToolApprovalPolicyCreateIn",
    "ToolApprovalPolicyEffectiveOut",
    "ToolApprovalPolicyLayerOut",
    "ToolApprovalPolicyOut",
    "ToolApprovalPolicyScope",
    "ToolApprovalPolicyUpdateIn",
]
