"""Contract boundaries for approval DTOs and gate snapshots.

Policy-shape validation lives in ``test_tool_approval_schema_behavior.py``.
This module pins the boundaries that protect server-owned identity, secret-free
projections, replay-key limits and the non-interactive entrypoint audience.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.tool_approval import ToolApprovalDecision, ToolExecution
from app.schemas.tool_approval import (
    NON_INTERACTIVE_ENTRYPOINTS,
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ApprovalVote,
    ExecutionEntrypoint,
    ToolApprovalDecisionIn,
    ToolApprovalDecisionOut,
    ToolApprovalPolicy,
    ToolExecutionCreateIn,
    ToolExecutionOut,
    ToolExecutionStatus,
    gate_signature,
    gate_stage_key,
)

_TOOL_ID = uuid4()


def _create_payload(**overrides) -> dict:
    values = {
        "tool_id": _TOOL_ID,
        "operation": "ticket.close",
        "entrypoint": ExecutionEntrypoint.CHAT,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    "field",
    ["actor_user_id", "effective_user_id", "team_id", "actor", "effective_user"],
)
def test_execution_create_rejects_client_supplied_backend_identity(field):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ToolExecutionCreateIn(**_create_payload(**{field: uuid4()}))


def test_non_interactive_entrypoints_are_exactly_the_durable_audience_set():
    assert NON_INTERACTIVE_ENTRYPOINTS == {
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.CHANNEL,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.SUBWORKFLOW,
        ExecutionEntrypoint.NESTED_AGENT,
    }

    for entrypoint in NON_INTERACTIVE_ENTRYPOINTS:
        with pytest.raises(ValidationError, match="execution_entrypoint_id_required"):
            ToolExecutionCreateIn(**_create_payload(entrypoint=entrypoint))

        identified = ToolExecutionCreateIn(
            **_create_payload(entrypoint=entrypoint, entrypoint_id="run-1")
        )
        assert identified.entrypoint_id == "run-1"


def test_gates_and_policies_are_immutable_snapshots():
    user_id = uuid4()
    gate = ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(user_id,))

    with pytest.raises(ValidationError):
        gate.user_ids = ()
    with pytest.raises(ValidationError):
        gate.allow_self_approval = True
    with pytest.raises(ValidationError):
        ApprovalGate(kind=ApprovalGateKind.CALLER, requires_review=True)

    policy = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(gate,),
    )
    with pytest.raises(ValidationError):
        policy.gates = ()
    with pytest.raises(ValidationError):
        ToolApprovalPolicy(
            default_decision=ApprovalDecision.ALLOW,
            default_action="allow",
        )


def test_gate_identity_is_order_independent_for_user_audiences():
    first, second = uuid4(), uuid4()
    forward = ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(first, second))
    reversed_ = ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(second, first))

    assert gate_signature(forward) == gate_signature(reversed_)
    assert gate_stage_key(forward) == gate_stage_key(reversed_)
    assert gate_stage_key(forward) == "user:" + ",".join(
        sorted((str(first), str(second)))
    )


def test_secret_safe_projections_drop_cipher_claim_and_binding_hashes():
    execution = ToolExecution(
        id=uuid4(),
        tool_definition_version=3,
        operation="ticket.close",
        entrypoint=ExecutionEntrypoint.CHAT,
        parameters_cipher="gAAAAA-secret-ciphertext",
        parameters_digest="a" * 64,
        parameters_preview={"token": "***REDACTED***"},
        policy_hash="b" * 64,
        binding_hash="c" * 64,
        status=ToolExecutionStatus.EXECUTING,
        claim_token="holder-only",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    execution.tool_id = _TOOL_ID
    execution.actor_user_id = uuid4()
    execution.team_id = uuid4()
    projected = ToolExecutionOut.model_validate(execution).model_dump(mode="json")

    for secret_field in (
        "parameters_cipher",
        "claim_token",
        "binding_hash",
        "policy_snapshot",
    ):
        assert secret_field not in projected
    assert projected["parameters_preview"] == {"token": "***REDACTED***"}

    decision = ToolApprovalDecision(
        id=uuid4(),
        decision=ApprovalVote.APPROVE,
        idempotency_key="client-replay-key",
        request_hash="d" * 64,
        binding_hash="e" * 64,
        created_at=datetime.now(timezone.utc),
    )
    decision.request_id = uuid4()
    decision.execution_id = uuid4()
    decision_out = ToolApprovalDecisionOut.model_validate(decision).model_dump(
        mode="json"
    )

    for internal_field in (
        "idempotency_key",
        "request_hash",
        "binding_hash",
    ):
        assert internal_field not in decision_out


def test_replay_key_and_reason_limits_match_storage_columns():
    key = "k" * 128
    accepted = ToolApprovalDecisionIn(
        decision=ApprovalVote.APPROVE,
        idempotency_key=key,
        reason="r" * 2000,
    )
    assert accepted.idempotency_key == key

    with pytest.raises(ValidationError):
        ToolApprovalDecisionIn(
            decision=ApprovalVote.APPROVE,
            idempotency_key="k" * 129,
        )
    with pytest.raises(ValidationError):
        ToolApprovalDecisionIn(
            decision=ApprovalVote.REJECT,
            idempotency_key="key-1",
            reason="r" * 2001,
        )


def test_gate_audience_identifiers_must_be_uuid_values():
    with pytest.raises(ValidationError):
        ApprovalGate(
            kind=ApprovalGateKind.USER,
            user_ids=("not-a-uuid",),
        )
