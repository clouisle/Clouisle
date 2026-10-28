"""Invariant tests for the approval lifecycle models.

These exercise ``validate_invariants`` directly on unsaved rows: the guards
are the only fail-closed barrier before writes because Tortoise does not grow
SQL CHECK constraints for them. Every rejected combination here represents a
row the service must never persist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.tool_approval import (
    ToolApprovalDecision,
    ToolApprovalRequest,
    ToolExecution,
)
from app.schemas.tool_approval import (
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)


def _digest(char: str = "a") -> str:
    return char * 64


def _execution(**overrides) -> ToolExecution:
    values = {
        "id": uuid4(),
        "operation": "ticket.close",
        "tool_definition_version": 1,
        "parameters_cipher": "gAAAAA-ciphertext",
        "parameters_digest": _digest("a"),
        "policy_hash": _digest("b"),
        "binding_hash": _digest("c"),
        "status": ToolExecutionStatus.READY,
    }
    values.update(overrides)
    return ToolExecution(**values)


def _request(**overrides) -> ToolApprovalRequest:
    values = {
        "id": uuid4(),
        "stage_index": 0,
        "stage_key": "caller",
        "gate_kind": ApprovalGateKind.CALLER,
        "status": ApprovalRequestStatus.PENDING,
    }
    values.update(overrides)
    return ToolApprovalRequest(**values)


def _decision(**overrides) -> ToolApprovalDecision:
    values = {
        "id": uuid4(),
        "decision": ApprovalVote.APPROVE,
        "idempotency_key": "decision-key-1",
        "request_hash": _digest("d"),
        "binding_hash": _digest("e"),
    }
    values.update(overrides)
    return ToolApprovalDecision(**values)


def _resolved_at() -> datetime:
    return datetime.now(timezone.utc)


def _rejects(row, reason: str) -> None:
    with pytest.raises(ValueError, match=f"^{reason}$"):
        row.validate_invariants()


@pytest.mark.parametrize("operation", [" ticket.close", "ticket.close ", "   "])
def test_execution_rejects_untrimmed_or_blank_operation(operation):
    _rejects(_execution(operation=operation), "tool_execution_operation_invalid")


def test_execution_enforces_operation_length_and_definition_version():
    _execution(operation="x" * 200).validate_invariants()

    _rejects(_execution(operation="x" * 201), "tool_execution_operation_too_long")

    for version in (0, -1):
        _rejects(
            _execution(tool_definition_version=version),
            "tool_execution_definition_version_invalid",
        )


def test_execution_rejects_missing_parameters_cipher():
    for cipher in ("", "   "):
        _rejects(
            _execution(parameters_cipher=cipher),
            "tool_execution_parameters_missing",
        )


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("parameters_digest", "tool_execution_parameters_digest_invalid"),
        ("policy_hash", "tool_execution_policy_hash_invalid"),
        ("binding_hash", "tool_execution_binding_hash_invalid"),
    ],
)
@pytest.mark.parametrize("value", ["", "a" * 63, "a" * 65, "g" * 64])
def test_execution_rejects_non_sha256_binding_hashes(field, reason, value):
    _rejects(_execution(**{field: value}), reason)


def test_execution_accepts_uppercase_hex_digests():
    _execution(
        parameters_digest="A" * 64,
        policy_hash="B" * 64,
        binding_hash="C" * 64,
    ).validate_invariants()


@pytest.mark.parametrize(
    "fragment",
    [
        {"connection_version": 1},
        {"connection_scope": "user"},
        {"connection_owner_user_id": uuid4()},
        {"connection_account_label": "service-account"},
    ],
)
def test_execution_rejects_connection_fragments_without_connection_id(fragment):
    _rejects(
        _execution(**fragment),
        "tool_execution_connection_binding_inconsistent",
    )


def test_execution_connection_requires_positive_version_and_known_scope():
    connection_id = uuid4()

    for version in (None, 0, -1):
        _rejects(
            _execution(
                connection_id=connection_id,
                connection_version=version,
                connection_scope="team",
            ),
            "tool_execution_connection_version_invalid",
        )

    for scope in (None, "", "org", "USER"):
        _rejects(
            _execution(
                connection_id=connection_id,
                connection_version=2,
                connection_scope=scope,
            ),
            "tool_execution_connection_scope_invalid",
        )


def test_execution_user_connection_binds_effective_identity_to_owner():
    connection_id = uuid4()
    owner_id = uuid4()

    _rejects(
        _execution(
            connection_id=connection_id,
            connection_version=1,
            connection_scope="user",
        ),
        "tool_execution_connection_owner_required",
    )

    for effective_user_id in (None, uuid4()):
        _rejects(
            _execution(
                connection_id=connection_id,
                connection_version=1,
                connection_scope="user",
                connection_owner_user_id=owner_id,
                effective_user_id=effective_user_id,
            ),
            "tool_execution_effective_identity_mismatch",
        )

    _execution(
        connection_id=connection_id,
        connection_version=1,
        connection_scope="user",
        connection_owner_user_id=owner_id,
        effective_user_id=owner_id,
        connection_account_label="alice@example.test",
    ).validate_invariants()


@pytest.mark.parametrize("scope", ["team", "site"])
def test_execution_shared_connection_rejects_user_identity_and_owner(scope):
    connection_id = uuid4()

    _rejects(
        _execution(
            connection_id=connection_id,
            connection_version=1,
            connection_scope=scope,
            effective_user_id=uuid4(),
        ),
        "tool_execution_effective_identity_unexpected",
    )

    _rejects(
        _execution(
            connection_id=connection_id,
            connection_version=1,
            connection_scope=scope,
            connection_owner_user_id=uuid4(),
        ),
        "tool_execution_connection_owner_unexpected",
    )

    _execution(
        connection_id=connection_id,
        connection_version=1,
        connection_scope=scope,
    ).validate_invariants()


@pytest.mark.parametrize("reason", list(ToolExecutionCancelReason))
def test_execution_cancelled_rows_require_a_known_reason(reason):
    _execution(
        status=ToolExecutionStatus.CANCELLED,
        cancel_reason=reason,
    ).validate_invariants()


def test_execution_cancelled_rows_fail_closed_on_missing_or_unknown_reason():
    _rejects(
        _execution(status=ToolExecutionStatus.CANCELLED),
        "tool_execution_cancel_reason_required",
    )

    # A legacy/corrupted raw value must not be treated as a valid reason.
    execution = _execution(
        status=ToolExecutionStatus.CANCELLED,
        cancel_reason=ToolExecutionCancelReason.EXPIRED,
    )
    execution.cancel_reason = "not-a-reason"
    _rejects(execution, "tool_execution_cancel_reason_invalid")


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.AWAITING_APPROVAL,
        ToolExecutionStatus.READY,
        ToolExecutionStatus.EXECUTING,
        ToolExecutionStatus.SUCCEEDED,
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.OUTCOME_UNKNOWN,
    ],
)
def test_execution_non_cancelled_rows_never_carry_a_cancel_reason(status):
    _rejects(
        _execution(
            status=status,
            cancel_reason=ToolExecutionCancelReason.EXPIRED,
        ),
        "tool_execution_cancel_reason_unexpected",
    )


@pytest.mark.parametrize(
    "status",
    [ToolExecutionStatus.AWAITING_APPROVAL, ToolExecutionStatus.READY],
)
def test_execution_cannot_be_claimed_before_ready(status):
    for token in ("", "holder-token"):
        _rejects(
            _execution(status=status, claim_token=token),
            "tool_execution_claim_before_ready",
        )


@pytest.mark.parametrize(
    "status",
    [
        ToolExecutionStatus.EXECUTING,
        ToolExecutionStatus.SUCCEEDED,
        ToolExecutionStatus.FAILED,
        ToolExecutionStatus.OUTCOME_UNKNOWN,
    ],
)
def test_execution_in_flight_or_terminal_success_requires_claim_token(status):
    for token in (None, "", "   "):
        _rejects(
            _execution(status=status, claim_token=token),
            "tool_execution_claim_required",
        )

    _execution(status=status, claim_token="holder-token").validate_invariants()


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (ToolExecutionStatus.AWAITING_APPROVAL, False),
        (ToolExecutionStatus.READY, False),
        (ToolExecutionStatus.EXECUTING, False),
        (ToolExecutionStatus.SUCCEEDED, True),
        (ToolExecutionStatus.FAILED, True),
        (ToolExecutionStatus.OUTCOME_UNKNOWN, True),
        (ToolExecutionStatus.CANCELLED, True),
    ],
)
def test_execution_terminal_and_claimable_properties(status, terminal):
    execution = _execution(status=status)
    assert execution.is_terminal is terminal
    assert execution.can_claim is (status == ToolExecutionStatus.READY)


@pytest.mark.parametrize("stage_index", [-1, -100])
def test_approval_request_rejects_negative_stage_index(stage_index):
    _rejects(
        _request(stage_index=stage_index),
        "tool_approval_stage_index_invalid",
    )


def test_approval_request_enforces_stage_key_boundaries():
    _request(stage_key="k" * 200).validate_invariants()

    _rejects(_request(stage_key="k" * 201), "tool_approval_stage_key_invalid")

    for stage_key in ("", "   "):
        _rejects(_request(stage_key=stage_key), "tool_approval_stage_key_invalid")


@pytest.mark.parametrize(
    "fragment",
    [
        {"approver_user_ids": [uuid4()]},
        {"approver_roles": ["admin"]},
        {"allow_self_approval": True},
    ],
)
def test_approval_request_caller_gate_rejects_any_audience(fragment):
    _rejects(_request(**fragment), "tool_approval_caller_audience_invalid")


def test_approval_request_user_gate_requires_exactly_one_unique_audience():
    user_id = uuid4()
    _request(
        gate_kind=ApprovalGateKind.USER,
        stage_key=f"user:{user_id}",
        approver_user_ids=[user_id],
    ).validate_invariants()

    for fragment in (
        {"approver_user_ids": []},
        {"approver_user_ids": [user_id], "approver_roles": ["admin"]},
        {"approver_user_ids": [user_id], "allow_self_approval": True},
    ):
        _rejects(
            _request(gate_kind=ApprovalGateKind.USER, **fragment),
            "tool_approval_user_audience_invalid",
        )

    _rejects(
        _request(
            gate_kind=ApprovalGateKind.USER,
            approver_user_ids=[user_id, user_id],
        ),
        "tool_approval_user_audience_duplicate",
    )


def test_approval_request_role_gate_requires_unique_roles_only():
    _request(
        gate_kind=ApprovalGateKind.TEAM_ROLE,
        stage_key="team_role:admin",
        approver_roles=["admin"],
        allow_self_approval=True,
    ).validate_invariants()

    for fragment in (
        {"approver_roles": []},
        {"approver_roles": ["admin"], "approver_user_ids": [uuid4()]},
    ):
        _rejects(
            _request(gate_kind=ApprovalGateKind.TEAM_ROLE, **fragment),
            "tool_approval_role_audience_invalid",
        )

    _rejects(
        _request(
            gate_kind=ApprovalGateKind.TEAM_ROLE,
            approver_roles=["admin", "admin"],
        ),
        "tool_approval_role_audience_duplicate",
    )


def test_approval_request_pending_and_resolved_states_are_exclusive():
    _rejects(
        _request(resolved_at=_resolved_at()),
        "tool_approval_pending_has_resolution",
    )

    for status in (
        ApprovalRequestStatus.APPROVED,
        ApprovalRequestStatus.REJECTED,
        ApprovalRequestStatus.EXPIRED,
        ApprovalRequestStatus.CANCELLED,
    ):
        _rejects(
            _request(status=status),
            "tool_approval_resolution_required",
        )


def test_approval_decision_requires_append_only_identity_and_hashes():
    for key in ("", "   "):
        _rejects(
            _decision(idempotency_key=key),
            "tool_approval_idempotency_key_required",
        )

    _rejects(
        _decision(request_hash="x" * 64),
        "tool_approval_request_hash_invalid",
    )
    _rejects(
        _decision(binding_hash="x" * 64),
        "tool_approval_binding_hash_invalid",
    )


def test_approval_decision_reason_length_boundary():
    _decision(reason="r" * 2000).validate_invariants()

    _rejects(_decision(reason="r" * 2001), "tool_approval_reason_too_long")
