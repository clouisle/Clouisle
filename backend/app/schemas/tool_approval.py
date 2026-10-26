"""Typed tool execution approval policy, binding and API DTOs.

This module is deliberately dependency-light: it must be importable both by
Pydantic response schemas (``app.schemas.tool``) and by the Tortoise models
(``app.models.tool_approval``) without importing services or ORM models.

Policy semantics
----------------
* ``default_decision`` applies to every operation without an explicit
  ``operation_overrides`` entry.
* An override is a *complete* policy for that exact operation name and
  replaces the tool-level default for it. Overrides are keyed by the original
  operation name (for MCP, the raw server-side tool name — never a model-facing
  alias or a discovery-cache id).
* A policy whose decision requires approval always has at least one gate:
  constructing one without gates adds caller confirmation. Callers and
  reviewers still need an interactive audience; the evaluator fails closed
  with ``policy_configuration_required`` when no audience can decide.
* Gate signatures are deduplicated deterministically. A duplicated audience
  keeps the stricter ``allow_self_approval=False``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.team import TeamMemberRole

MAX_OPERATION_KEY_LENGTH = 200
MAX_OPERATION_OVERRIDES = 200
MAX_GATES_PER_POLICY = 20
MAX_APPROVERS_PER_GATE = 50
MAX_POLICY_NESTING = 8
MAX_SENSITIVE_FIELDS = 200


class ApprovalDecision(str, Enum):
    """Decision a policy layer returns for one operation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class ApprovalVote(str, Enum):
    """Human decision recorded for one approval gate."""

    APPROVE = "approve"
    REJECT = "reject"


class ApprovalGateKind(str, Enum):
    """Who is able to decide one approval gate."""

    CALLER = "caller"
    USER = "user"
    TEAM_ROLE = "team_role"


class PolicySource(str, Enum):
    """Strength layer a policy comes from (highest first)."""

    SITE = "site"
    TEAM = "team"
    TOOL = "tool"
    ENTRYPOINT = "entrypoint"


class ExecutionEntrypoint(str, Enum):
    """Entrypoint that requests one tool execution."""

    CHAT = "chat"
    AGENT_RUN = "agent_run"
    WORKFLOW = "workflow"
    API_KEY = "api_key"
    SCHEDULE = "schedule"
    CHANNEL = "channel"
    EMBED = "embed"
    SUBWORKFLOW = "subworkflow"
    NESTED_AGENT = "nested_agent"
    TOOL_TEST = "tool_test"
    ADMIN_TEST = "admin_test"


class ExecutionRunKind(str, Enum):
    """Durable run a tool execution belongs to."""

    AGENT = "agent"
    WORKFLOW = "workflow"


class ToolExecutionStatus(str, Enum):
    """Lifecycle of one tool execution request.

    ``ready`` means every approval gate passed and exactly one worker may
    claim the execution. ``cancelled`` carries a terminal reason because a
    rejection, expiry, revoked grant and a stopped run must never collapse
    into an approval.
    """

    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    CANCELLED = "cancelled"


class ToolExecutionCancelReason(str, Enum):
    """Why an execution ended without a side effect."""

    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CANCELLED = "cancelled"
    BINDING_CHANGED = "binding_changed"
    RUN_STOPPED = "run_stopped"
    POLICY_DENIED = "policy_denied"


class ApprovalRequestStatus(str, Enum):
    """Lifecycle of one approval gate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalGate(BaseModel):
    """One immutable approval requirement.

    ``user_ids`` and ``roles`` are frozen onto the approval request when the
    execution is created so a later policy edit cannot silently change who was
    asked. Authorization is re-evaluated against current membership at
    decision time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ApprovalGateKind
    user_ids: tuple[UUID, ...] = ()
    roles: tuple[str, ...] = ()
    allow_self_approval: bool = False

    @field_validator("user_ids", mode="after")
    @classmethod
    def _normalize_user_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        deduped: list[UUID] = []
        seen: set[UUID] = set()
        for user_id in value:
            if user_id in seen:
                continue
            seen.add(user_id)
            deduped.append(user_id)
        if len(deduped) > MAX_APPROVERS_PER_GATE:
            raise ValueError("approval_gate_too_many_approvers")
        return tuple(deduped)

    @field_validator("roles", mode="after")
    @classmethod
    def _normalize_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {
            TeamMemberRole.OWNER,
            TeamMemberRole.ADMIN,
            TeamMemberRole.MEMBER,
            TeamMemberRole.VIEWER,
        }
        deduped: list[str] = []
        for role in value:
            normalized = role.strip().lower()
            if normalized not in allowed:
                raise ValueError("approval_gate_role_invalid")
            if normalized not in deduped:
                deduped.append(normalized)
        return tuple(deduped)

    @model_validator(mode="after")
    def _check_shape(self) -> "ApprovalGate":
        if self.kind == ApprovalGateKind.CALLER:
            if self.user_ids or self.roles:
                raise ValueError("approval_gate_caller_has_audience")
            if self.allow_self_approval:
                raise ValueError("approval_gate_caller_self_approval_invalid")
        elif self.kind == ApprovalGateKind.USER:
            if not self.user_ids:
                raise ValueError("approval_gate_users_required")
            if self.roles:
                raise ValueError("approval_gate_users_with_roles")
            if self.allow_self_approval:
                raise ValueError("approval_gate_user_self_approval_invalid")
        elif self.kind == ApprovalGateKind.TEAM_ROLE:
            if not self.roles:
                raise ValueError("approval_gate_roles_required")
            if self.user_ids:
                raise ValueError("approval_gate_roles_with_users")
        else:  # pragma: no cover - enum exhaustiveness
            raise ValueError("approval_gate_kind_invalid")
        return self


class ToolApprovalPolicy(BaseModel):
    """Complete approval policy for one tool (or one operation override)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_decision: ApprovalDecision = ApprovalDecision.REQUIRE_APPROVAL
    gates: tuple[ApprovalGate, ...] = ()
    operation_overrides: dict[str, "ToolApprovalPolicy"] = Field(default_factory=dict)

    @field_validator("gates", mode="after")
    @classmethod
    def _dedupe_gates(cls, value: tuple[ApprovalGate, ...]) -> tuple[ApprovalGate, ...]:
        merged: list[ApprovalGate] = []
        indexes: dict[tuple[str, tuple[str, ...]], int] = {}
        for gate in value:
            signature = gate_signature(gate)
            existing_index = indexes.get(signature)
            if existing_index is None:
                indexes[signature] = len(merged)
                merged.append(gate)
                continue
            existing = merged[existing_index]
            if existing.allow_self_approval and not gate.allow_self_approval:
                merged[existing_index] = ApprovalGate(
                    kind=existing.kind,
                    user_ids=existing.user_ids,
                    roles=existing.roles,
                    allow_self_approval=False,
                )
        if len(merged) > MAX_GATES_PER_POLICY:
            raise ValueError("approval_policy_too_many_gates")
        return tuple(merged)

    @field_validator("operation_overrides", mode="after")
    @classmethod
    def _normalize_operation_overrides(
        cls, value: dict[str, "ToolApprovalPolicy"]
    ) -> dict[str, "ToolApprovalPolicy"]:
        if len(value) > MAX_OPERATION_OVERRIDES:
            raise ValueError("approval_policy_too_many_operations")
        normalized: dict[str, "ToolApprovalPolicy"] = {}
        for raw_operation, policy in value.items():
            operation = raw_operation.strip()
            if not operation:
                raise ValueError("approval_policy_operation_empty")
            if operation == "*":
                raise ValueError("approval_policy_operation_wildcard_unsupported")
            if len(operation) > MAX_OPERATION_KEY_LENGTH:
                raise ValueError("approval_policy_operation_too_long")
            if any(ord(char) < 32 for char in operation):
                raise ValueError("approval_policy_operation_control_character")
            if operation in normalized:
                raise ValueError("approval_policy_operation_duplicate")
            normalized[operation] = policy
        return normalized

    @model_validator(mode="after")
    def _check_consistency(self) -> "ToolApprovalPolicy":
        if self.default_decision == ApprovalDecision.REQUIRE_APPROVAL:
            if not self.gates:
                object.__setattr__(
                    self,
                    "gates",
                    (ApprovalGate(kind=ApprovalGateKind.CALLER),),
                )
        elif self.gates:
            raise ValueError("approval_gates_require_approval")
        _assert_policy_tree(self, depth=0)
        return self

    def for_operation(self, operation: str) -> "ToolApprovalPolicy":
        """Return the exact-operation policy, following nested overrides."""
        policy = self
        seen: set[str] = set()
        depth = 0
        while True:
            override = policy.operation_overrides.get(operation)
            if override is None:
                return policy
            depth += 1
            if depth > MAX_POLICY_NESTING:
                raise ValueError("approval_policy_nesting_too_deep")
            if id(override) in seen:  # pragma: no cover - frozen models cannot cycle
                raise ValueError("approval_policy_cycle")
            seen.add(id(override))
            policy = override


def gate_signature(gate: ApprovalGate) -> tuple[str, tuple[str, ...]]:
    """Deterministic identity of a gate's audience (self-approval excluded)."""
    if gate.kind == ApprovalGateKind.CALLER:
        return (gate.kind.value, ())
    if gate.kind == ApprovalGateKind.USER:
        return (
            gate.kind.value,
            tuple(sorted(str(user_id) for user_id in gate.user_ids)),
        )
    return (gate.kind.value, tuple(sorted(gate.roles)))


def gate_stage_key(gate: ApprovalGate) -> str:
    """Stable, human-readable key used to deduplicate persisted gates."""
    kind, audience = gate_signature(gate)
    if not audience:
        return kind
    return f"{kind}:{','.join(audience)}"


def _assert_policy_tree(
    policy: ToolApprovalPolicy, *, depth: int, budget: list[int] | None = None
) -> None:
    if depth > MAX_POLICY_NESTING:
        raise ValueError("approval_policy_nesting_too_deep")
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > 2000:
        raise ValueError("approval_policy_too_large")
    for override in policy.operation_overrides.values():
        _assert_policy_tree(override, depth=depth + 1, budget=budget)


class PolicyLayer(BaseModel):
    """One strength layer contributing to an effective policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: PolicySource
    policy: ToolApprovalPolicy
    label: str | None = Field(default=None, max_length=100)

    @field_validator("label", mode="after")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if any(ord(char) < 32 for char in stripped):
            raise ValueError("approval_policy_layer_label_invalid")
        return stripped


class PolicyEvaluation(BaseModel):
    """Deterministic effective policy produced by ``evaluate_policy``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ApprovalDecision
    gates: tuple[ApprovalGate, ...] = ()
    policy_hash: str
    sources: tuple[str, ...] = ()
    configuration_error: str | None = None

    @property
    def requires_approval(self) -> bool:
        return self.decision == ApprovalDecision.REQUIRE_APPROVAL

    @property
    def is_allowed(self) -> bool:
        return (
            self.decision == ApprovalDecision.ALLOW and self.configuration_error is None
        )


def default_tool_approval_policy() -> ToolApprovalPolicy:
    """Fail-closed policy for tools with no explicit configuration."""
    return ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
    )


class ToolExecutionCreateIn(BaseModel):
    """Request body for creating one execution.

    Identity (actor, effective user, team, connection binding, grants) is
    established by the backend call context and is intentionally not accepted
    from a request body.
    """

    model_config = ConfigDict(extra="forbid")

    tool_id: UUID
    operation: str = Field(min_length=1, max_length=MAX_OPERATION_KEY_LENGTH)
    parameters: dict[str, Any] = Field(default_factory=dict)
    entrypoint: ExecutionEntrypoint
    entrypoint_id: str | None = Field(default=None, max_length=200)
    run_kind: ExecutionRunKind | None = None
    run_id: UUID | None = None
    tool_call_id: str | None = Field(default=None, max_length=200)
    connection_id: UUID | None = None
    sensitive_fields: tuple[str, ...] = ()
    expires_at: datetime | None = None

    @field_validator("operation", mode="after")
    @classmethod
    def _normalize_operation(cls, value: str) -> str:
        operation = value.strip()
        if not operation:
            raise ValueError("approval_policy_operation_empty")
        if any(ord(char) < 32 for char in operation):
            raise ValueError("approval_policy_operation_control_character")
        return operation

    @field_validator("entrypoint_id", "tool_call_id", mode="after")
    @classmethod
    def _normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("sensitive_fields", mode="after")
    @classmethod
    def _normalize_sensitive_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        deduped: list[str] = []
        for field_name in value:
            normalized = field_name.strip()
            if not normalized:
                continue
            if len(normalized) > 200:
                raise ValueError("sensitive_field_too_long")
            if normalized not in deduped:
                deduped.append(normalized)
        if len(deduped) > MAX_SENSITIVE_FIELDS:
            raise ValueError("sensitive_fields_too_many")
        return tuple(deduped)

    @model_validator(mode="after")
    def _check_run_binding(self) -> "ToolExecutionCreateIn":
        if (self.run_kind is None) != (self.run_id is None):
            raise ValueError("execution_run_binding_invalid")
        if self.tool_call_id is not None and self.run_kind is None:
            raise ValueError("execution_tool_call_requires_run")
        non_interactive = self.entrypoint in NON_INTERACTIVE_ENTRYPOINTS
        if non_interactive and not self.entrypoint_id:
            raise ValueError("execution_entrypoint_id_required")
        return self


class ToolExecutionOut(BaseModel):
    """Secret-safe execution projection.

    ``parameters_cipher``, claim tokens and connection secrets never appear in
    this DTO. ``parameters_preview`` contains values already redacted by the
    approval service.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tool_id: UUID
    tool_definition_version: int
    operation: str

    actor_user_id: UUID
    effective_user_id: UUID | None = None
    team_id: UUID

    entrypoint: ExecutionEntrypoint
    entrypoint_id: str | None = None
    run_kind: ExecutionRunKind | None = None
    run_id: UUID | None = None
    tool_call_id: str | None = None

    connection_id: UUID | None = None
    connection_version: int | None = None
    connection_scope: str | None = None
    connection_account_label: str | None = None

    parameters_preview: dict[str, Any] = Field(default_factory=dict)
    parameters_digest: str
    policy_hash: str

    status: ToolExecutionStatus
    cancel_reason: ToolExecutionCancelReason | None = None
    result_ref: dict[str, Any] | None = None
    error_code: str | None = None

    expires_at: datetime | None = None
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ToolApprovalRequestOut(BaseModel):
    """Secret-safe approval gate projection."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    execution_id: UUID
    stage_index: int
    stage_key: str
    gate_kind: ApprovalGateKind
    approver_user_ids: list[UUID] = Field(default_factory=list)
    approver_roles: list[str] = Field(default_factory=list)
    allow_self_approval: bool
    masked_display: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalRequestStatus
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class ToolApprovalDecisionIn(BaseModel):
    """Approver decision payload. Approval never edits execution parameters."""

    model_config = ConfigDict(extra="forbid")

    decision: ApprovalVote
    reason: str | None = Field(default=None, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key", mode="after")
    @classmethod
    def _normalize_key(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("idempotency_key_required")
        return stripped

    @field_validator("reason", mode="after")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.replace("\x00", "").strip()
        return stripped or None


class ToolApprovalDecisionOut(BaseModel):
    """Immutable decision record projection."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    execution_id: UUID
    decision: ApprovalVote
    decided_by_id: UUID | None = None
    reason: str | None = None
    created_at: datetime


class ToolApprovalDecisionResultOut(BaseModel):
    """Decision response including the resulting execution state."""

    decision: ToolApprovalDecisionOut
    execution_status: ToolExecutionStatus
    remaining_approvals: int


# Entry-points without a durable interactive audience. A caller-confirmation
# gate cannot be satisfied here, so the evaluator fails closed instead of
# assuming consent. Foreground chat and explicit tool tests are interactive.
NON_INTERACTIVE_ENTRYPOINTS: frozenset[ExecutionEntrypoint] = frozenset(
    {
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.CHANNEL,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.SUBWORKFLOW,
        ExecutionEntrypoint.NESTED_AGENT,
    }
)
