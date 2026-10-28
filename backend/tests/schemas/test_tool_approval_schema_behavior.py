"""Behavior tests for tool approval policy and DTO validation.

These assert the fail-closed invariants of the schema layer: gate audiences
must be shaped correctly, duplicate audiences keep the strictest rule, policy
trees stay bounded, and request bodies normalize/reject unsafe input.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.tool_approval import (
    MAX_APPROVERS_PER_GATE,
    MAX_GATES_PER_POLICY,
    MAX_OPERATION_KEY_LENGTH,
    MAX_OPERATION_OVERRIDES,
    MAX_SENSITIVE_FIELDS,
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ApprovalRequestStatus,
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    PolicyEvaluation,
    PolicyLayer,
    PolicySource,
    ToolApprovalDecisionIn,
    ToolExecutionCreateIn,
    ToolExecutionOut,
    ToolExecutionStatus,
    default_tool_approval_policy,
    gate_signature,
    gate_stage_key,
)

_TOOL_ID = uuid4()


def _policy(**overrides) -> dict:
    values = {"default_decision": "allow"}
    values.update(overrides)
    return values


def _create_payload(**overrides) -> dict:
    values = {
        "tool_id": _TOOL_ID,
        "operation": "ticket.close",
        "entrypoint": ExecutionEntrypoint.CHAT,
    }
    values.update(overrides)
    return values


def test_approval_gate_deduplicates_approvers_and_rejects_oversized_audience():
    first, second = uuid4(), uuid4()
    gate = ApprovalGate(
        kind=ApprovalGateKind.USER,
        user_ids=(first, second, first),
    )
    assert gate.user_ids == (first, second)

    with pytest.raises(ValidationError, match="approval_gate_too_many_approvers"):
        ApprovalGate(
            kind=ApprovalGateKind.USER,
            user_ids=tuple(uuid4() for _ in range(MAX_APPROVERS_PER_GATE + 1)),
        )


def test_role_gate_normalizes_roles_and_rejects_unknown_roles():
    gate = ApprovalGate(
        kind=ApprovalGateKind.TEAM_ROLE,
        roles=(" Admin ", "admin", "OWNER"),
    )
    assert gate.roles == ("admin", "owner")

    with pytest.raises(ValidationError, match="approval_gate_role_invalid"):
        ApprovalGate(kind=ApprovalGateKind.TEAM_ROLE, roles=("superuser",))


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        (
            {
                "kind": ApprovalGateKind.CALLER,
                "user_ids": (uuid4(),),
            },
            "approval_gate_caller_has_audience",
        ),
        (
            {"kind": ApprovalGateKind.CALLER, "allow_self_approval": True},
            "approval_gate_caller_self_approval_invalid",
        ),
        (
            {"kind": ApprovalGateKind.USER},
            "approval_gate_users_required",
        ),
        (
            {
                "kind": ApprovalGateKind.USER,
                "user_ids": (uuid4(),),
                "roles": ("admin",),
            },
            "approval_gate_users_with_roles",
        ),
        (
            {
                "kind": ApprovalGateKind.USER,
                "user_ids": (uuid4(),),
                "allow_self_approval": True,
            },
            "approval_gate_user_self_approval_invalid",
        ),
        (
            {"kind": ApprovalGateKind.TEAM_ROLE},
            "approval_gate_roles_required",
        ),
        (
            {
                "kind": ApprovalGateKind.TEAM_ROLE,
                "roles": ("admin",),
                "user_ids": (uuid4(),),
            },
            "approval_gate_roles_with_users",
        ),
    ],
)
def test_gate_shape_rejects_ambiguous_audiences(kwargs, reason):
    with pytest.raises(ValidationError, match=reason):
        ApprovalGate(**kwargs)


def test_policy_deduplicates_gates_and_keeps_stricter_self_approval_rule():
    from app.schemas.tool_approval import ToolApprovalPolicy

    lax = ApprovalGate(
        kind=ApprovalGateKind.TEAM_ROLE,
        roles=("admin",),
        allow_self_approval=True,
    )
    strict = ApprovalGate(kind=ApprovalGateKind.TEAM_ROLE, roles=("admin",))
    policy = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        gates=(lax, strict),
    )
    assert len(policy.gates) == 1
    assert policy.gates[0].allow_self_approval is False
    assert gate_stage_key(policy.gates[0]) == "team_role:admin"
    assert gate_signature(policy.gates[0]) == ("team_role", ("admin",))


def test_policy_rejects_too_many_distinct_gates():
    from app.schemas.tool_approval import ToolApprovalPolicy

    gates = tuple(
        ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(uuid4(),))
        for _ in range(MAX_GATES_PER_POLICY + 1)
    )
    with pytest.raises(ValidationError, match="approval_policy_too_many_gates"):
        ToolApprovalPolicy(
            default_decision=ApprovalDecision.REQUIRE_APPROVAL,
            gates=gates,
        )


def test_operation_overrides_reject_unsafe_keys():
    from app.schemas.tool_approval import ToolApprovalPolicy

    too_many = {
        f"operation-{index}": _policy() for index in range(MAX_OPERATION_OVERRIDES + 1)
    }
    with pytest.raises(ValidationError, match="approval_policy_too_many_operations"):
        ToolApprovalPolicy(operation_overrides=too_many)

    for overrides, reason in [
        ({"   ": _policy()}, "approval_policy_operation_empty"),
        ({"*": _policy()}, "approval_policy_operation_wildcard_unsupported"),
        (
            {"o" * (MAX_OPERATION_KEY_LENGTH + 1): _policy()},
            "approval_policy_operation_too_long",
        ),
        ({"bad\x01key": _policy()}, "approval_policy_operation_control_character"),
        ({"op": _policy(), " op ": _policy()}, "approval_policy_operation_duplicate"),
    ]:
        with pytest.raises(ValidationError, match=reason):
            ToolApprovalPolicy(operation_overrides=overrides)


def test_policy_requires_gates_only_when_approval_is_required():
    from app.schemas.tool_approval import ToolApprovalPolicy

    with pytest.raises(ValidationError, match="approval_gates_require_approval"):
        ToolApprovalPolicy(
            default_decision=ApprovalDecision.ALLOW,
            gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
        )

    policy = ToolApprovalPolicy(default_decision=ApprovalDecision.REQUIRE_APPROVAL)
    assert policy.gates == (ApprovalGate(kind=ApprovalGateKind.CALLER),)
    assert default_tool_approval_policy().gates == policy.gates


def test_for_operation_follows_nested_overrides_and_returns_base_otherwise():
    from app.schemas.tool_approval import ToolApprovalPolicy

    leaf = ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW)
    middle = ToolApprovalPolicy(
        default_decision=ApprovalDecision.ALLOW,
        operation_overrides={"write": leaf},
    )
    root = ToolApprovalPolicy(
        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
        operation_overrides={"write": middle},
    )
    resolved = root.for_operation("write")
    assert resolved.default_decision == ApprovalDecision.ALLOW
    assert resolved.gates == ()
    assert resolved.operation_overrides == {}
    assert middle.for_operation("write").operation_overrides == {}
    assert root.for_operation("read") is root


def test_policy_layer_label_is_optional_but_never_control_data():
    assert PolicyLayer(source=PolicySource.TEAM, policy=_policy()).label is None
    assert (
        PolicyLayer(source=PolicySource.TEAM, policy=_policy(), label="   ").label
        is None
    )
    assert (
        PolicyLayer(
            source=PolicySource.TEAM, policy=_policy(), label="  Team policy  "
        ).label
        == "Team policy"
    )
    with pytest.raises(ValidationError, match="approval_policy_layer_label_invalid"):
        PolicyLayer(
            source=PolicySource.TEAM,
            policy=_policy(),
            label="bad\x00label",
        )


def test_policy_evaluation_properties_distinguish_allow_from_config_error():
    allowed = PolicyEvaluation(
        decision=ApprovalDecision.ALLOW,
        policy_hash="a" * 64,
    )
    assert allowed.is_allowed is True
    assert allowed.requires_approval is False

    misconfigured = PolicyEvaluation(
        decision=ApprovalDecision.ALLOW,
        policy_hash="a" * 64,
        configuration_error="approval_audience_missing",
    )
    assert misconfigured.is_allowed is False

    require = PolicyEvaluation(
        decision=ApprovalDecision.REQUIRE_APPROVAL,
        policy_hash="a" * 64,
    )
    assert require.requires_approval is True


def test_execution_create_normalizes_operation_and_optional_ids():
    body = ToolExecutionCreateIn(
        **_create_payload(operation="  ticket.close  ", entrypoint_id="   ")
    )
    assert body.operation == "ticket.close"
    assert body.entrypoint_id is None

    for operation, reason in [
        ("   ", "approval_policy_operation_empty"),
        ("bad\x01operation", "approval_policy_operation_control_character"),
    ]:
        with pytest.raises(ValidationError, match=reason):
            ToolExecutionCreateIn(**_create_payload(operation=operation))


def test_execution_create_normalizes_sensitive_fields():
    body = ToolExecutionCreateIn(
        **_create_payload(sensitive_fields=(" password ", "", "password", "token"))
    )
    assert body.sensitive_fields == ("password", "token")

    with pytest.raises(ValidationError, match="sensitive_field_too_long"):
        ToolExecutionCreateIn(**_create_payload(sensitive_fields=("x" * 201,)))

    with pytest.raises(ValidationError, match="sensitive_fields_too_many"):
        ToolExecutionCreateIn(
            **_create_payload(
                sensitive_fields=tuple(
                    f"field-{index}" for index in range(MAX_SENSITIVE_FIELDS + 1)
                )
            )
        )


def test_execution_create_enforces_run_and_interactive_entrypoint_bindings():
    run_id = uuid4()
    valid = ToolExecutionCreateIn(
        **_create_payload(
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
            tool_call_id="call-1",
        )
    )
    assert valid.run_id == run_id

    with pytest.raises(ValidationError, match="execution_run_binding_invalid"):
        ToolExecutionCreateIn(**_create_payload(run_kind=ExecutionRunKind.AGENT))
    with pytest.raises(ValidationError, match="execution_run_binding_invalid"):
        ToolExecutionCreateIn(**_create_payload(run_id=run_id))
    with pytest.raises(ValidationError, match="execution_tool_call_requires_run"):
        ToolExecutionCreateIn(**_create_payload(tool_call_id="call-1"))
    with pytest.raises(ValidationError, match="execution_entrypoint_id_required"):
        ToolExecutionCreateIn(**_create_payload(entrypoint=ExecutionEntrypoint.API_KEY))

    interactive = ToolExecutionCreateIn(
        **_create_payload(
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
            entrypoint_id=None,
        )
    )
    assert interactive.entrypoint_id is None


def test_decision_payload_normalizes_key_and_reason():
    body = ToolApprovalDecisionIn(
        decision=ApprovalVote.APPROVE,
        idempotency_key="  key-1  ",
        reason="  needs \x00review  ",
    )
    assert body.idempotency_key == "key-1"
    assert body.reason == "needs review"

    assert (
        ToolApprovalDecisionIn(
            decision=ApprovalVote.REJECT,
            idempotency_key="key-2",
            reason="\x00  ",
        ).reason
        is None
    )
    assert (
        ToolApprovalDecisionIn(
            decision=ApprovalVote.REJECT,
            idempotency_key="key-3",
            reason=None,
        ).reason
        is None
    )
    with pytest.raises(ValidationError, match="idempotency_key_required"):
        ToolApprovalDecisionIn(
            decision=ApprovalVote.APPROVE,
            idempotency_key="   ",
        )


def test_execution_out_projection_never_exposes_secret_fields():
    fields = set(ToolExecutionOut.model_fields)
    assert "parameters_cipher" not in fields
    assert "claim_token" not in fields
    assert {"parameters_preview", "status", "policy_hash"} <= fields
    assert ApprovalRequestStatus.PENDING.value == "pending"
    assert ToolExecutionStatus.EXECUTING.value == "executing"
