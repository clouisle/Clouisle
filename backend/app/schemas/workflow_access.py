"""Typed per-workflow access policy.

Shape (stored in ``Workflow.access_policy``):

```json
{
  "operations": {
    "run":  {"decision": "allow", "gates": [{"kind": "team_role", "roles": ["owner", "admin"]}]},
    "edit": {"decision": "deny"}
  }
}
```

An empty policy, or an operation missing from ``operations``, means "inherit":
callers fall back to the legacy rules (visibility + RBAC code + team role).
Inheritance is per operation so a workflow can lock down ``run`` without
restating ``view``.

Only ``allow`` and ``deny`` are accepted. ``require_approval`` is deliberately
absent: a workflow run starts a worker and a sandbox, so gating it on a human
before it starts is a different feature (a pre-run queue), not a policy value
that can be added silently later.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.team import TeamMemberRole

MAX_GATES_PER_OPERATION = 20
MAX_PRINCIPALS_PER_GATE = 200
ALLOWED_TEAM_ROLES = frozenset(
    {
        TeamMemberRole.OWNER,
        TeamMemberRole.ADMIN,
        TeamMemberRole.MEMBER,
        TeamMemberRole.VIEWER,
    }
)


class WorkflowOperation(str, Enum):
    """Operations a workflow access policy can decide."""

    VIEW = "view"
    RUN = "run"
    EDIT = "edit"
    PUBLISH = "publish"
    DELETE = "delete"


class AccessDecision(str, Enum):
    """Decision for one operation."""

    ALLOW = "allow"
    DENY = "deny"


class AccessGateKind(str, Enum):
    """Audience a gate matches."""

    TEAM_ROLE = "team_role"
    USER = "user"
    API_KEY = "api_key"


class AccessGate(BaseModel):
    """One audience a principal may match.

    Each kind carries exactly the list it matches on, so a malformed gate cannot
    accidentally match everyone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: AccessGateKind
    roles: tuple[str, ...] = ()
    user_ids: tuple[UUID, ...] = ()
    api_key_ids: tuple[UUID, ...] = ()

    @field_validator("roles", mode="after")
    @classmethod
    def _known_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unknown = sorted({role for role in value if role not in ALLOWED_TEAM_ROLES})
        if unknown:
            raise ValueError(f"unknown_team_roles:{','.join(unknown)}")
        return value

    @model_validator(mode="after")
    def _exactly_one_audience(self) -> "AccessGate":
        populated = [
            bool(self.roles),
            bool(self.user_ids),
            bool(self.api_key_ids),
        ]
        if sum(populated) != 1:
            raise ValueError("gate_audience_invalid")
        expected = {
            AccessGateKind.TEAM_ROLE: bool(self.roles),
            AccessGateKind.USER: bool(self.user_ids),
            AccessGateKind.API_KEY: bool(self.api_key_ids),
        }[self.kind]
        if not expected:
            raise ValueError("gate_audience_mismatch")
        for values in (self.roles, self.user_ids, self.api_key_ids):
            if len(values) > MAX_PRINCIPALS_PER_GATE:
                raise ValueError("gate_audience_too_large")
        return self


class WorkflowOperationPolicy(BaseModel):
    """Decision plus optional audience restriction for one operation.

    ``gates`` empty means "anyone the legacy rules already allow". When gates
    are present the principal must match one of them, so a gate list narrows an
    ``allow`` and is meaningless on ``deny``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: AccessDecision
    gates: tuple[AccessGate, ...] = ()

    @field_validator("gates", mode="after")
    @classmethod
    def _bounded_gates(cls, value: tuple[AccessGate, ...]) -> tuple[AccessGate, ...]:
        if len(value) > MAX_GATES_PER_OPERATION:
            raise ValueError("too_many_gates")
        return value

    @model_validator(mode="after")
    def _gates_require_allow(self) -> "WorkflowOperationPolicy":
        if self.gates and self.decision is not AccessDecision.ALLOW:
            raise ValueError("deny_cannot_have_gates")
        return self


class WorkflowAccessPolicy(BaseModel):
    """Complete policy for one workflow; empty means fully inherited."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operations: dict[WorkflowOperation, WorkflowOperationPolicy] = Field(
        default_factory=dict
    )

    def for_operation(
        self, operation: WorkflowOperation
    ) -> WorkflowOperationPolicy | None:
        return self.operations.get(operation)


def normalize_workflow_access_policy(value: Any) -> WorkflowAccessPolicy:
    """Validate a stored or submitted policy; raises ``ValueError`` when invalid."""
    if value in (None, {}):
        return WorkflowAccessPolicy()
    if not isinstance(value, dict):
        raise ValueError("access_policy_invalid")
    return WorkflowAccessPolicy.model_validate(value)


def policy_is_empty(policy: WorkflowAccessPolicy) -> bool:
    """True when the workflow inherits every operation from the legacy rules."""
    return not policy.operations
