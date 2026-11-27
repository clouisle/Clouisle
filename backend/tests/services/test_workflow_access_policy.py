"""Access-policy evaluation, including inheritance and fail-closed behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.response import BusinessError
from app.schemas.workflow_access import (
    MAX_GATES_PER_OPERATION,
    WorkflowAccessPolicy,
    WorkflowOperation,
    normalize_workflow_access_policy,
    policy_is_empty,
)
from app.services.workflow_access import (
    AccessPrincipal,
    AccessReason,
    assert_workflow_access,
    evaluate_workflow_access,
)


def _workflow(policy):
    return SimpleNamespace(id=uuid4(), access_policy=policy)


def _principal(**overrides):
    base = {
        "user_id": uuid4(),
        "team_role": "member",
        "api_key_id": None,
        "is_superuser": False,
    }
    base.update(overrides)
    return AccessPrincipal(**base)


def test_empty_policy_inherits_the_legacy_rules():
    workflow = _workflow({})
    assert policy_is_empty(normalize_workflow_access_policy({}))
    for operation in WorkflowOperation:
        assert evaluate_workflow_access(workflow, operation, _principal()) is None


def test_a_missing_operation_is_inherited_while_others_are_decided():
    workflow = _workflow({"operations": {"run": {"decision": "deny"}}})

    assert (
        evaluate_workflow_access(workflow, WorkflowOperation.VIEW, _principal()) is None
    )
    run = evaluate_workflow_access(workflow, WorkflowOperation.RUN, _principal())
    assert run is not None and run.allowed is False
    assert run.reason is AccessReason.DENIED_BY_POLICY


def test_allow_without_gates_matches_any_caller_the_legacy_rules_accept():
    workflow = _workflow({"operations": {"view": {"decision": "allow"}}})

    result = evaluate_workflow_access(workflow, WorkflowOperation.VIEW, _principal())

    assert result is not None and result.allowed is True
    assert result.reason is AccessReason.ALLOWED_BY_POLICY


def test_role_gate_limits_an_allow_to_the_listed_roles():
    workflow = _workflow(
        {
            "operations": {
                "run": {
                    "decision": "allow",
                    "gates": [{"kind": "team_role", "roles": ["owner", "admin"]}],
                }
            }
        }
    )

    admin = evaluate_workflow_access(
        workflow, WorkflowOperation.RUN, _principal(team_role="admin")
    )
    member = evaluate_workflow_access(
        workflow, WorkflowOperation.RUN, _principal(team_role="member")
    )
    outsider = evaluate_workflow_access(
        workflow, WorkflowOperation.RUN, _principal(team_role=None)
    )

    assert admin is not None and admin.allowed and admin.matched_gate == 0
    assert admin.reason is AccessReason.ALLOWED_BY_GATE
    assert member is not None and member.allowed is False
    assert member.reason is AccessReason.NOT_IN_AUDIENCE
    assert outsider is not None and outsider.allowed is False


def test_user_and_api_key_gates_match_their_own_identity():
    allowed_user, other_user, key_id = uuid4(), uuid4(), uuid4()
    workflow = _workflow(
        {
            "operations": {
                "edit": {
                    "decision": "allow",
                    "gates": [
                        {"kind": "user", "user_ids": [str(allowed_user)]},
                        {"kind": "api_key", "api_key_ids": [str(key_id)]},
                    ],
                }
            }
        }
    )

    by_user = evaluate_workflow_access(
        workflow, WorkflowOperation.EDIT, _principal(user_id=allowed_user)
    )
    by_key = evaluate_workflow_access(
        workflow, WorkflowOperation.EDIT, _principal(api_key_id=key_id)
    )
    rejected = evaluate_workflow_access(
        workflow, WorkflowOperation.EDIT, _principal(user_id=other_user)
    )

    assert by_user is not None and by_user.allowed and by_user.matched_gate == 0
    assert by_key is not None and by_key.allowed and by_key.matched_gate == 1
    assert rejected is not None and rejected.allowed is False

    # An API key identity is not a substitute for its owner's user entry.
    owner_key = evaluate_workflow_access(
        workflow,
        WorkflowOperation.EDIT,
        _principal(user_id=other_user, api_key_id=uuid4()),
    )
    assert owner_key is not None and owner_key.allowed is False


def test_superuser_is_never_locked_out():
    workflow = _workflow(
        {
            "operations": {
                "delete": {"decision": "deny"},
                "run": {
                    "decision": "allow",
                    "gates": [{"kind": "team_role", "roles": ["owner"]}],
                },
            }
        }
    )
    superuser = _principal(is_superuser=True, team_role=None)

    for operation in (WorkflowOperation.DELETE, WorkflowOperation.RUN):
        result = evaluate_workflow_access(workflow, operation, superuser)
        assert result is not None and result.allowed
        assert result.reason is AccessReason.SUPERUSER

    inherited = evaluate_workflow_access(workflow, WorkflowOperation.VIEW, superuser)
    assert inherited is not None and inherited.reason is AccessReason.SUPERUSER


def test_an_unreadable_stored_policy_denies_instead_of_inheriting():
    workflow = _workflow({"operations": {"run": {"decision": "maybe"}}})

    result = evaluate_workflow_access(workflow, WorkflowOperation.RUN, _principal())

    assert result is not None and result.allowed is False
    assert result.reason is AccessReason.INVALID_POLICY


def test_assert_workflow_access_maps_denials_to_hidden_or_explicit_errors():
    workflow = _workflow({"operations": {"run": {"decision": "deny"}}})
    principal = _principal()

    with pytest.raises(BusinessError) as hidden:
        assert_workflow_access(workflow, WorkflowOperation.RUN, principal, hidden=True)
    assert hidden.value.status_code == 404

    with pytest.raises(BusinessError) as explicit:
        assert_workflow_access(workflow, WorkflowOperation.RUN, principal)
    assert explicit.value.status_code == 403
    assert explicit.value.data == {"operation": "run", "reason": "denied_by_policy"}

    # Inherited operations never raise.
    assert assert_workflow_access(workflow, WorkflowOperation.VIEW, principal) is None


@pytest.mark.parametrize(
    "policy",
    [
        {"operations": {"run": {"decision": "allow", "extra": 1}}},
        {"operations": {"run": {"decision": "allow", "gates": [{"kind": "user"}]}}},
        {
            "operations": {
                "run": {
                    "decision": "allow",
                    "gates": [
                        {"kind": "user", "user_ids": [str(uuid4())], "roles": ["owner"]}
                    ],
                }
            }
        },
        {
            "operations": {
                "run": {
                    "decision": "deny",
                    "gates": [{"kind": "team_role", "roles": ["owner"]}],
                }
            }
        },
        {"operations": {"explode": {"decision": "allow"}}},
        {"operations": []},
        "not-a-policy",
    ],
)
def test_invalid_policies_are_rejected(policy):
    with pytest.raises(ValueError):
        normalize_workflow_access_policy(policy)


def test_gate_count_is_bounded():
    gates = [
        {"kind": "user", "user_ids": [str(uuid4())]}
        for _ in range(MAX_GATES_PER_OPERATION + 1)
    ]
    with pytest.raises(ValueError):
        normalize_workflow_access_policy(
            {"operations": {"run": {"decision": "allow", "gates": gates}}}
        )


def test_a_superuser_still_reports_inherited_operations_as_inherited():
    """A bypass must not be reported as if the policy had decided the operation."""
    from app.services.workflow_access import describe_effective_access

    workflow = _workflow({"operations": {"run": {"decision": "deny"}}})
    described = describe_effective_access(
        workflow, _principal(is_superuser=True, team_role=None)
    )

    assert described["view"]["source"] == "inherit"
    assert described["view"]["reason"] == AccessReason.SUPERUSER.value
    assert described["run"]["source"] == "policy"
    assert described["run"]["allowed"] is True


def test_round_trip_of_a_valid_policy():
    policy = normalize_workflow_access_policy(
        {"operations": {"run": {"decision": "deny"}}}
    )

    assert isinstance(policy, WorkflowAccessPolicy)
    assert policy.for_operation(WorkflowOperation.RUN) is not None
    assert policy.for_operation(WorkflowOperation.VIEW) is None
    assert policy.model_dump(mode="json") == {
        "operations": {"run": {"decision": "deny", "gates": []}}
    }
