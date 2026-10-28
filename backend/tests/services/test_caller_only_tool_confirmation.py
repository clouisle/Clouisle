"""Caller-only tool confirmation cutover at the backend boundary.

Legacy ``user``/``team_role`` audiences must stay readable for audit but can
never be written, resumed, or treated as satisfied. These tests exercise the
real persistence boundary instead of forwarding-style mocks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ToolApprovalRequest,
    ToolExecution,
    ToolExecutionStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ExternalApprovalAudienceError,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    assert_caller_only_approval_policy,
    default_tool_approval_policy,
    external_approval_gate_kinds,
)
from app.services.tool_approvals import build_parameter_snapshot, decide_approval
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    execute_stored_tool,
    require_caller_only_policy,
)

_LEGACY_POLICY = {
    "default_decision": "require_approval",
    "gates": [
        {"kind": "user", "user_ids": [str(uuid4())]},
        {"kind": "team_role", "roles": ["admin"]},
    ],
}

_LEGACY_SNAPSHOT = {
    "evaluation": {
        "decision": "require_approval",
        "gates": [{"kind": "team_role", "roles": ["admin"]}],
    },
    "layers": [
        {
            "source": "tool",
            "label": "tool",
            "policy": {
                "default_decision": "require_approval",
                "gates": [{"kind": "user", "user_ids": [str(uuid4())]}],
            },
        }
    ],
}


def test_legacy_policy_still_parses_for_history_reads():
    policy = ToolApprovalPolicy.model_validate(_LEGACY_POLICY)
    assert {gate.kind for gate in policy.gates} == {
        ApprovalGateKind.USER,
        ApprovalGateKind.TEAM_ROLE,
    }
    # Historical gate rows keep their kind for the approval-request projection.
    assert ApprovalGateKind("team_role") is ApprovalGateKind.TEAM_ROLE
    assert set(external_approval_gate_kinds(policy)) == {
        ApprovalGateKind.USER,
        ApprovalGateKind.TEAM_ROLE,
    }


def test_external_gate_detection_walks_nested_overrides_and_snapshots():
    nested = {
        "default_decision": "allow",
        "operation_overrides": {
            "tool:delete": {
                "default_decision": "require_approval",
                "gates": [{"kind": "team_role", "roles": ["owner"]}],
            }
        },
    }
    assert external_approval_gate_kinds(nested) == (ApprovalGateKind.TEAM_ROLE,)
    assert set(external_approval_gate_kinds(_LEGACY_SNAPSHOT)) == {
        ApprovalGateKind.TEAM_ROLE,
        ApprovalGateKind.USER,
    }


def test_caller_only_policies_pass_and_external_bodies_are_rejected():
    assert_caller_only_approval_policy(None)
    assert_caller_only_approval_policy({})
    assert_caller_only_approval_policy(default_tool_approval_policy())
    assert_caller_only_approval_policy(
        ToolApprovalPolicy(
            default_decision=ApprovalDecision.ALLOW,
            operation_overrides={
                "tool:read": ToolApprovalPolicy(
                    default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                    gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
                )
            },
        )
    )

    with pytest.raises(ExternalApprovalAudienceError) as exc_info:
        assert_caller_only_approval_policy(_LEGACY_POLICY)
    assert exc_info.value.code == "approval_gate_external_audience_unsupported"
    assert ApprovalGateKind.USER in exc_info.value.gate_kinds

    with pytest.raises(BusinessError) as business_error:
        require_caller_only_policy(_LEGACY_POLICY)
    assert business_error.value.code == (
        ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
    )
    assert business_error.value.status_code == 422
    assert business_error.value.msg_key == (
        "tool_approval_policy_external_audience_unsupported"
    )


async def _grant_team_read(user: User) -> None:
    permission = await Permission.filter(code="team:read").first()
    if permission is None:
        permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"Tool user {uuid4().hex[:6]}")
    await role.permissions.add(permission)
    await user.roles.add(role)


async def _team_and_user(name: str) -> tuple[User, Team]:
    user = await User.create(
        username=name, email=f"{name}@test.invalid", hashed_password="x"
    )
    await _grant_team_read(user)
    team = await Team.create(name=name)
    await TeamMember.create(team=team, user=user, role="owner")
    return user, team


def _tool_context(
    user: User,
    team: Team,
    *,
    entrypoint: ExecutionEntrypoint,
    interactive: bool,
    require_approval: bool = False,
    entrypoint_id: str | None = None,
) -> ToolCallContext:
    return ToolCallContext(
        actor=user,
        team_id=team.id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id,
        interactive=interactive,
        require_approval=require_approval,
    )


@pytest.mark.parametrize(
    "entrypoint",
    [
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.CHANNEL,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.NESTED_AGENT,
    ],
)
@pytest.mark.asyncio
async def test_every_noninteractive_entrypoint_fails_closed_on_legacy_policy(
    entrypoint,
):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user(f"legacy_{entrypoint.value}")
        tool = await Tool.create(
            name="legacy_tool",
            display_name="Legacy",
            description="",
            team=team,
            created_by=user,
            type="custom",
            identity_policy="none",
            approval_policy=_LEGACY_POLICY,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        context = _tool_context(
            user,
            team,
            entrypoint=entrypoint,
            interactive=False,
            entrypoint_id=str(uuid4()),
        )
        with pytest.raises(BusinessError) as exc_info:
            await execute_stored_tool(tool, "run", {"x": 1}, context, invoke)
        assert exc_info.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert calls == []
        assert await ToolExecution.filter(tool_id=tool.id).count() == 0
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize(
    "entrypoint", [ExecutionEntrypoint.WORKFLOW, ExecutionEntrypoint.SUBWORKFLOW]
)
@pytest.mark.asyncio
async def test_workflow_entrypoints_ignore_legacy_audience_and_never_gate(entrypoint):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user(f"workflow_{entrypoint.value}")
        tool = await Tool.create(
            name="legacy_tool",
            display_name="Legacy",
            description="",
            team=team,
            created_by=user,
            type="custom",
            identity_policy="none",
            approval_policy=_LEGACY_POLICY,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        context = _tool_context(
            user,
            team,
            entrypoint=entrypoint,
            interactive=False,
            entrypoint_id=str(uuid4()),
        )
        result = await execute_stored_tool(tool, "run", {"x": 1}, context, invoke)

        assert result == {"ok": True}
        assert calls == [{"x": 1}]
        assert await ToolApprovalRequest.all().count() == 0
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_mcp_caller_policy_pauses_and_resumes_once():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user("mcp_caller")
        tool = await Tool.create(
            name="mcp_tool",
            display_name="MCP",
            description="",
            team=team,
            created_by=user,
            type="mcp",
            identity_policy="none",
            mcp_config={"transport": "http", "url": "https://example.invalid/mcp"},
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        context = _tool_context(
            user, team, entrypoint=ExecutionEntrypoint.CHAT, interactive=True
        )
        pending = await execute_stored_tool(
            tool, "tool:delete", {"id": 1}, context, invoke
        )
        assert isinstance(pending, PendingToolApproval)
        assert calls == []
        gate = await ToolApprovalRequest.get(execution_id=pending.execution_id)
        assert gate.gate_kind == ApprovalGateKind.CALLER
        await decide_approval(
            gate.id, user, decision="approve", idempotency_key=uuid4().hex
        )
        resumed = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            interactive=True,
            execution_id=pending.execution_id,
        )
        assert await execute_stored_tool(
            tool, "tool:delete", {"id": 1}, resumed, invoke
        ) == {"ok": True}
        assert calls == [{"id": 1}]
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_agent_caller_switch_still_requires_caller_confirmation():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user("agent_switch")
        tool = await Tool.create(
            name="plain_tool",
            display_name="Plain",
            description="",
            team=team,
            created_by=user,
            type="custom",
            identity_policy="none",
            approval_policy={"default_decision": "allow"},
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return "done"

        context = _tool_context(
            user,
            team,
            entrypoint=ExecutionEntrypoint.AGENT_RUN,
            interactive=True,
            require_approval=True,
            entrypoint_id=str(uuid4()),
        )
        pending = await execute_stored_tool(tool, "run", {"x": 1}, context, invoke)
        assert isinstance(pending, PendingToolApproval)
        assert calls == []
        gate = await ToolApprovalRequest.get(execution_id=pending.execution_id)
        assert gate.gate_kind == ApprovalGateKind.CALLER
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_api_key_agent_caller_policy_parks_for_same_key():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user("noninteractive_caller")
        tool = await Tool.create(
            name="caller_tool",
            display_name="Caller",
            description="",
            team=team,
            created_by=user,
            type="custom",
            identity_policy="none",
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return "ok"

        context = _tool_context(
            user,
            team,
            entrypoint=ExecutionEntrypoint.API_KEY,
            interactive=False,
            entrypoint_id=str(uuid4()),
        )
        pending = await execute_stored_tool(tool, "run", {"x": 1}, context, invoke)

        assert isinstance(pending, PendingToolApproval)
        assert calls == []
        assert await ToolApprovalRequest.filter(
            execution_id=pending.execution_id,
            gate_kind=ApprovalGateKind.CALLER,
        ).exists()
    finally:
        await Tortoise.close_connections()


def test_evaluate_policy_denies_legacy_audience_anywhere_in_layers():
    from app.services.tool_approvals import evaluate_policy

    nested = ToolApprovalPolicy.model_validate(
        {
            "default_decision": "allow",
            "operation_overrides": {
                "unused:operation": {
                    "default_decision": "require_approval",
                    "gates": [{"kind": "team_role", "roles": ["owner"]}],
                }
            },
        }
    )
    evaluation = evaluate_policy(
        [PolicyLayer(source=PolicySource.SITE, policy=nested)],
        "current:operation",
        entrypoint_interactive=True,
    )
    assert evaluation.decision == ApprovalDecision.DENY
    assert evaluation.gates == ()
    assert evaluation.configuration_error == (
        "approval_gate_external_audience_unsupported"
    )
    assert evaluation.is_allowed is False

    legacy_allow_gate = ToolApprovalPolicy.model_construct(
        default_decision=ApprovalDecision.ALLOW,
        gates=(ApprovalGate(kind=ApprovalGateKind.USER, user_ids=(uuid4(),)),),
        operation_overrides={},
    )
    denied = evaluate_policy(
        [
            PolicyLayer.model_construct(
                source=PolicySource.TOOL, policy=legacy_allow_gate
            )
        ],
        "current:operation",
        entrypoint_interactive=False,
    )
    assert denied.decision == ApprovalDecision.DENY
    assert denied.gates == ()
    assert denied.configuration_error == ("approval_gate_external_audience_unsupported")

    caller_only = evaluate_policy(
        [PolicyLayer(source=PolicySource.TOOL, policy=default_tool_approval_policy())],
        "current:operation",
        entrypoint_interactive=True,
    )
    assert caller_only.decision == ApprovalDecision.REQUIRE_APPROVAL
    assert caller_only.configuration_error is None


@pytest.mark.asyncio
async def test_pending_execution_with_legacy_snapshot_cannot_resume():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team = await _team_and_user("legacy_snapshot")
        tool = await Tool.create(
            name="snapshot_tool",
            display_name="Snapshot",
            description="",
            team=team,
            created_by=user,
            type="custom",
            identity_policy="none",
            approval_policy={"default_decision": "allow"},
        )
        parameters = {"x": 1}
        snapshot = build_parameter_snapshot(parameters)
        execution = await ToolExecution.create(
            actor_user=user,
            team=team,
            tool=tool,
            tool_definition_version=tool.definition_version,
            operation="run",
            entrypoint=ExecutionEntrypoint.CHAT,
            parameters_cipher=snapshot.ciphertext,
            parameters_digest=snapshot.digest,
            parameters_preview=snapshot.preview,
            policy_snapshot=_LEGACY_SNAPSHOT,
            policy_hash="0" * 64,
            binding_hash="0" * 64,
            status=ToolExecutionStatus.READY,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return "ok"

        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            interactive=True,
            execution_id=execution.id,
        )
        with pytest.raises(BusinessError) as exc_info:
            await execute_stored_tool(tool, "run", parameters, context, invoke)
        assert exc_info.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert calls == []
        refreshed = await ToolExecution.get(id=execution.id)
        assert refreshed.status == ToolExecutionStatus.READY
        assert refreshed.claim_token is None
    finally:
        await Tortoise.close_connections()
