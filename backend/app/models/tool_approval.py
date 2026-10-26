"""Tool execution and approval models.

Three records isolate one external side effect:

* :class:`ToolExecution` — the immutable binding of tool definition version,
  operation, effective principal, connection/grant version, encrypted business
  parameters, parameter digest and effective policy. Its status machine is
  ``awaiting_approval -> ready -> executing -> succeeded/failed/outcome_unknown``
  with terminal ``cancelled`` (plus an explicit cancel reason) when nobody
  approved, the request expired, a grant was revoked or the run stopped.
* :class:`ToolApprovalRequest` — one approval gate. An execution can carry
  several gates (caller confirmation, designated users, team roles); every
  gate must approve before the execution becomes ``ready``.
* :class:`ToolApprovalDecision` — append-only decision record with a unique
  idempotency key. Rows are never updated by the service.

Secrets never enter these tables: parameters are stored as a Fernet token,
previews are redacted, and the JSON ``policy_snapshot``/``masked_display``
fields contain identifiers and redacted values only.
"""

from __future__ import annotations

import string
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from tortoise import fields, models

from app.schemas.tool_approval import (
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)

if TYPE_CHECKING:
    from .tool import Tool
    from .user import Team, User

_HEX_DIGITS = set(string.hexdigits)
_CONNECTION_SCOPES = {"user", "team", "site"}
_CANCEL_REASONS = {reason.value for reason in ToolExecutionCancelReason}


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX_DIGITS for char in value)


def _non_empty(value: str | None) -> bool:
    return bool(value) and bool(value.strip())


class ToolExecution(models.Model):
    """One approval-bound external tool invocation."""

    id = fields.UUIDField(primary_key=True, default=uuid4)

    # Who asked, and whose external identity was resolved by the backend.
    actor_user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="initiated_tool_executions",
        on_delete=fields.CASCADE,
        description="Calling principal that initiated the execution",
    )
    actor_user_id: UUID  # type: ignore[assignment]
    effective_user: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="effective_tool_executions",
        on_delete=fields.SET_NULL,
        null=True,
        description="Connection owner whose external account is used",
    )
    effective_user_id: UUID | None  # type: ignore[assignment]
    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_executions",
        on_delete=fields.CASCADE,
        description="Team whose connection policy applies",
    )
    team_id: UUID  # type: ignore[assignment]

    # Immutable definition binding.
    tool: fields.ForeignKeyRelation["Tool"] = fields.ForeignKeyField(
        "models.Tool",
        related_name="executions",
        on_delete=fields.CASCADE,
        description="Tool definition used for this execution",
    )
    tool_id: UUID  # type: ignore[assignment]
    tool_definition_version = fields.IntField(
        description="Tool.definition_version snapshot; a bump invalidates approvals"
    )
    operation = fields.CharField(
        max_length=200,
        description="Stable operation name (raw MCP tool name, HTTP operation key)",
    )

    # Call context.
    entrypoint = fields.CharEnumField(
        ExecutionEntrypoint, description="Entrypoint kind that requested execution"
    )
    entrypoint_id = fields.CharField(
        max_length=200, null=True, description="Stable entrypoint identifier"
    )
    run_kind = fields.CharEnumField(
        ExecutionRunKind, null=True, description="Durable run kind"
    )
    run_id = fields.UUIDField(null=True, description="Durable run id")
    tool_call_id = fields.CharField(
        max_length=200, null=True, description="Model/tool-call identifier"
    )

    # Connection binding. Plain UUIDs keep the approval module independent of
    # the connection module; the service validates every field against the
    # resolver's fresh snapshot before a claim.
    connection_id = fields.UUIDField(null=True)
    connection_version = fields.IntField(null=True, description="secret_version")
    connection_scope = fields.CharField(
        max_length=20, null=True, description="user, team or site"
    )
    connection_owner_user_id = fields.UUIDField(null=True)
    connection_account_label = fields.CharField(
        max_length=150, null=True, description="Non-secret account label"
    )
    grant_id = fields.UUIDField(null=True)
    grant_version = fields.IntField(null=True)

    # Immutable request snapshot. Ciphertext only; digests bind approvals.
    parameters_cipher = fields.TextField(
        description="Fernet ciphertext of the full parameter JSON"
    )
    parameters_digest = fields.CharField(
        max_length=64, description="SHA-256 of canonical full parameters"
    )
    parameters_preview: dict = fields.JSONField(
        default=dict, description="Redacted parameter preview for reviewers"
    )  # type: ignore[assignment]
    policy_snapshot: dict = fields.JSONField(
        default=dict, description="Secret-safe effective policy and layer snapshot"
    )  # type: ignore[assignment]
    policy_hash = fields.CharField(
        max_length=64, description="SHA-256 of the evaluated policy"
    )
    binding_hash = fields.CharField(
        max_length=64,
        description="SHA-256 binding definition, identity, connection, params, policy",
    )

    # Lifecycle / single execution claim.
    status = fields.CharEnumField(
        ToolExecutionStatus,
        default=ToolExecutionStatus.AWAITING_APPROVAL,
        description="Execution status",
    )
    cancel_reason = fields.CharEnumField(
        ToolExecutionCancelReason,
        null=True,
        description="Terminal reason when status=cancelled",
    )
    claim_token = fields.CharField(
        max_length=64, null=True, description="Opaque holder token for executing"
    )
    claimed_at = fields.DatetimeField(null=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    # Non-secret result reference (ids/summary only) and failure metadata.
    result_ref: dict | None = fields.JSONField(null=True)  # type: ignore[assignment]
    error_code = fields.CharField(max_length=100, null=True)
    error_detail = fields.TextField(null=True)

    expires_at = fields.DatetimeField(
        null=True, description="Approval/execute deadline; past means terminal"
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_executions"
        ordering = ["-created_at"]
        indexes = [
            ("team", "status", "created_at"),
            ("actor_user", "created_at"),
            ("effective_user", "created_at"),
            ("tool", "operation", "created_at"),
            ("status", "expires_at"),
            ("run_kind", "run_id"),
        ]

    def __str__(self) -> str:
        return f"ToolExecution {self.id} {self.operation} ({self.status.value})"

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            ToolExecutionStatus.SUCCEEDED,
            ToolExecutionStatus.FAILED,
            ToolExecutionStatus.OUTCOME_UNKNOWN,
            ToolExecutionStatus.CANCELLED,
        }

    @property
    def can_claim(self) -> bool:
        return self.status == ToolExecutionStatus.READY

    def validate_invariants(self) -> None:
        """Fail closed on ambiguous identity/binding rows before writes.

        Enforced in the service (with database unique/index support) because
        Tortoise table generation does not emit CHECK constraints.
        """
        if not _non_empty(self.operation) or self.operation != self.operation.strip():
            raise ValueError("tool_execution_operation_invalid")
        if self.operation is None or len(self.operation) > 200:
            raise ValueError("tool_execution_operation_too_long")
        if self.tool_definition_version < 1:
            raise ValueError("tool_execution_definition_version_invalid")
        if not _non_empty(self.parameters_cipher):
            raise ValueError("tool_execution_parameters_missing")
        if not _is_sha256(self.parameters_digest):
            raise ValueError("tool_execution_parameters_digest_invalid")
        if not _is_sha256(self.policy_hash):
            raise ValueError("tool_execution_policy_hash_invalid")
        if not _is_sha256(self.binding_hash):
            raise ValueError("tool_execution_binding_hash_invalid")

        if self.connection_id is None:
            if any(
                value is not None
                for value in (
                    self.connection_version,
                    self.connection_scope,
                    self.connection_owner_user_id,
                    self.grant_id,
                    self.grant_version,
                    self.connection_account_label,
                )
            ):
                raise ValueError("tool_execution_connection_binding_inconsistent")
        else:
            if self.connection_version is None or self.connection_version < 1:
                raise ValueError("tool_execution_connection_version_invalid")
            if self.connection_scope not in _CONNECTION_SCOPES:
                raise ValueError("tool_execution_connection_scope_invalid")
            if self.connection_scope == "user":
                if self.connection_owner_user_id is None:
                    raise ValueError("tool_execution_connection_owner_required")
                if self.effective_user_id != self.connection_owner_user_id:
                    raise ValueError("tool_execution_effective_identity_mismatch")
            elif self.effective_user_id is not None:
                # Team/site accounts must never masquerade as a user identity.
                raise ValueError("tool_execution_effective_identity_unexpected")
            if self.connection_scope != "user" and self.connection_owner_user_id:
                raise ValueError("tool_execution_connection_owner_unexpected")
            if self.grant_id is None and self.grant_version is not None:
                raise ValueError("tool_execution_grant_inconsistent")
            if self.grant_id is not None and (
                self.grant_version is None or self.grant_version < 1
            ):
                raise ValueError("tool_execution_grant_version_invalid")

        if self.status == ToolExecutionStatus.CANCELLED:
            if self.cancel_reason is None:
                raise ValueError("tool_execution_cancel_reason_required")
            cancel_reason = getattr(self.cancel_reason, "value", self.cancel_reason)
            if cancel_reason not in _CANCEL_REASONS:
                raise ValueError("tool_execution_cancel_reason_invalid")
        elif self.cancel_reason is not None:
            raise ValueError("tool_execution_cancel_reason_unexpected")

        if self.status in {
            ToolExecutionStatus.AWAITING_APPROVAL,
            ToolExecutionStatus.READY,
        }:
            if self.claim_token is not None:
                raise ValueError("tool_execution_claim_before_ready")
        elif self.status in {
            ToolExecutionStatus.EXECUTING,
            ToolExecutionStatus.SUCCEEDED,
            ToolExecutionStatus.FAILED,
            ToolExecutionStatus.OUTCOME_UNKNOWN,
        }:
            if not _non_empty(self.claim_token):
                raise ValueError("tool_execution_claim_required")


class ToolApprovalRequest(models.Model):
    """One approval gate belonging to an execution."""

    id = fields.UUIDField(primary_key=True, default=uuid4)

    execution: fields.ForeignKeyRelation[ToolExecution] = fields.ForeignKeyField(
        "models.ToolExecution",
        related_name="approval_requests",
        on_delete=fields.CASCADE,
        description="Execution this gate belongs to",
    )
    execution_id: UUID  # type: ignore[assignment]

    stage_index = fields.IntField(description="Deterministic order of the gate")
    stage_key = fields.CharField(
        max_length=200,
        description="Stable audience key, unique per execution",
    )
    gate_kind = fields.CharEnumField(
        ApprovalGateKind, description="caller, user or team_role"
    )

    # Frozen audience snapshot. USER gates store the configured users; TEAM_ROLE
    # gates store the allowed roles. Current membership is re-checked when a
    # decision arrives, so a removed member cannot approve.
    approver_user_ids: list = fields.JSONField(default=list)  # type: ignore[assignment]
    approver_roles: list = fields.JSONField(default=list)  # type: ignore[assignment]
    allow_self_approval = fields.BooleanField(default=False)

    masked_display: dict = fields.JSONField(
        default=dict, description="Secret-safe object/scope/parameter display"
    )  # type: ignore[assignment]

    status = fields.CharEnumField(
        ApprovalRequestStatus,
        default=ApprovalRequestStatus.PENDING,
        description="Gate status",
    )
    expires_at = fields.DatetimeField(null=True)
    resolved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_approval_requests"
        ordering = ["stage_index"]
        unique_together = (("execution", "stage_key"),)
        indexes = [
            ("status", "expires_at"),
            ("execution", "status"),
        ]

    def __str__(self) -> str:
        return f"Approval {self.stage_key} for execution {self.execution_id}"

    def validate_invariants(self) -> None:
        if self.stage_index < 0:
            raise ValueError("tool_approval_stage_index_invalid")
        if not _non_empty(self.stage_key) or len(self.stage_key) > 200:
            raise ValueError("tool_approval_stage_key_invalid")
        user_ids = list(self.approver_user_ids or [])
        roles = list(self.approver_roles or [])
        if self.gate_kind == ApprovalGateKind.CALLER:
            if user_ids or roles or self.allow_self_approval:
                raise ValueError("tool_approval_caller_audience_invalid")
        elif self.gate_kind == ApprovalGateKind.USER:
            if not user_ids or roles or self.allow_self_approval:
                raise ValueError("tool_approval_user_audience_invalid")
            if len(set(user_ids)) != len(user_ids):
                raise ValueError("tool_approval_user_audience_duplicate")
        elif self.gate_kind == ApprovalGateKind.TEAM_ROLE:
            if not roles or user_ids:
                raise ValueError("tool_approval_role_audience_invalid")
            if len(set(roles)) != len(roles):
                raise ValueError("tool_approval_role_audience_duplicate")
        else:  # pragma: no cover - enum exhaustiveness
            raise ValueError("tool_approval_gate_kind_invalid")

        if self.status == ApprovalRequestStatus.PENDING:
            if self.resolved_at is not None:
                raise ValueError("tool_approval_pending_has_resolution")
        elif self.resolved_at is None:
            raise ValueError("tool_approval_resolution_required")


class ToolApprovalDecision(models.Model):
    """Append-only record of one human decision.

    ``idempotency_key`` is globally unique: replaying the same decision returns
    the stored row, while reusing a key for a different request/decision is a
    conflict. The service never updates an existing decision.
    """

    id = fields.UUIDField(primary_key=True, default=uuid4)

    request: fields.ForeignKeyRelation[ToolApprovalRequest] = fields.ForeignKeyField(
        "models.ToolApprovalRequest",
        related_name="decisions",
        on_delete=fields.CASCADE,
        description="Gate that was decided",
    )
    request_id: UUID  # type: ignore[assignment]
    execution: fields.ForeignKeyRelation[ToolExecution] = fields.ForeignKeyField(
        "models.ToolExecution",
        related_name="approval_decisions",
        on_delete=fields.CASCADE,
        description="Denormalized execution for audit queries",
    )
    execution_id: UUID  # type: ignore[assignment]

    decision = fields.CharEnumField(ApprovalVote, description="approve or reject")
    decided_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="tool_approval_decisions",
        on_delete=fields.SET_NULL,
        null=True,
        description="Approver; kept NULL if the user is later deleted",
    )
    decided_by_id: UUID | None  # type: ignore[assignment]
    reason = fields.TextField(null=True)

    idempotency_key = fields.CharField(
        max_length=128, unique=True, description="Client replay key"
    )
    request_hash = fields.CharField(
        max_length=64, description="SHA-256 of request+decision+reason"
    )
    binding_hash = fields.CharField(
        max_length=64, description="Execution binding snapshot at decision time"
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tool_approval_decisions"
        ordering = ["-created_at"]
        unique_together = (("request",),)
        indexes = [("execution", "created_at")]

    def __str__(self) -> str:
        return f"ApprovalDecision {self.decision.value} for request {self.request_id}"

    def validate_invariants(self) -> None:
        if not _non_empty(self.idempotency_key):
            raise ValueError("tool_approval_idempotency_key_required")
        if not _is_sha256(self.request_hash):
            raise ValueError("tool_approval_request_hash_invalid")
        if not _is_sha256(self.binding_hash):
            raise ValueError("tool_approval_binding_hash_invalid")
        if self.reason is not None and len(self.reason) > 2000:
            raise ValueError("tool_approval_reason_too_long")


__all__: list[str] = [
    "ToolApprovalDecision",
    "ToolApprovalRequest",
    "ToolExecution",
]
