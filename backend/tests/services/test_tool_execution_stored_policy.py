"""Only the tool's own policy gates Agent calls; workflows never gate.

The retired site/team/entrypoint layers are not read anymore. A workflow (any
entrypoint, including API-key-origin and nested Agent calls) executes without
creating approval requests, while an Agent call still honours the stored tool
policy. A workflow execution parked by the retired layers is cancelled instead
of being approved or silently executed.
"""

from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolApprovalRequest,
    ToolExecution,
    ToolExecutionStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ApprovalRequestStatus,
    PolicySource,
    ToolExecutionCancelReason,
)
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    execute_stored_tool,
)


async def _grant_team_read(user: User) -> None:
    permission = await Permission.filter(code="team:read").first()
    if permission is None:
        permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"policy user {uuid4().hex[:6]}")
    await role.permissions.add(permission)
    await user.roles.add(role)


async def _fixture(*, approval_policy):
    user = await User.create(
        username=f"policy_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@policy.test",
        hashed_password="x",
    )
    await _grant_team_read(user)
    team = await Team.create(name=f"Policy {uuid4().hex[:6]}")
    await TeamMember.create(team=team, user=user, role="owner")
    tool = await Tool.create(
        name=f"policy_tool_{uuid4().hex[:6]}",
        display_name="Policy tool",
        description="",
        team=team,
        created_by=user,
        type="custom",
        approval_policy=approval_policy,
    )
    return user, team, tool


def _context(
    user,
    team,
    entrypoint,
    *,
    run_kind=None,
    run_id=None,
    tool_call_id=None,
    interactive,
    entrypoint_id=None,
    require_approval=False,
):
    return ToolCallContext(
        actor=user,
        team_id=team.id,
        entrypoint=entrypoint,
        entrypoint_id=entrypoint_id or str(uuid4()),
        run_kind=run_kind,
        run_id=run_id,
        tool_call_id=tool_call_id,
        interactive=interactive,
        require_approval=require_approval,
    )


@pytest.mark.asyncio
async def test_tool_policy_still_gates_non_interactive_agent_call():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            }
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as blocked:
            await execute_stored_tool(
                tool,
                "read",
                {},
                _context(
                    user,
                    team,
                    ExecutionEntrypoint.SCHEDULE,
                    run_kind=ExecutionRunKind.AGENT,
                    run_id=uuid4(),
                    tool_call_id="scheduled:1",
                    interactive=False,
                ),
                invoke,
            )

        assert blocked.value.code == (
            ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert calls == []
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_tool_policy_pauses_agent_call_for_caller():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            }
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        result = await execute_stored_tool(
            tool,
            "read",
            {},
            _context(user, team, ExecutionEntrypoint.CHAT, interactive=True),
            invoke,
        )

        assert isinstance(result, PendingToolApproval)
        assert calls == []
        assert await ToolApprovalRequest.filter(
            execution_id=result.execution_id, status=ApprovalRequestStatus.PENDING
        ).exists()
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_workflow_api_key_entrypoint_never_gates():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            }
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        run_id = uuid4()
        result = await execute_stored_tool(
            tool,
            "read",
            {"x": 1},
            _context(
                user,
                team,
                ExecutionEntrypoint.API_KEY,
                run_kind=ExecutionRunKind.WORKFLOW,
                run_id=run_id,
                tool_call_id="workflow-node:1",
                interactive=False,
                require_approval=True,
            ),
            invoke,
        )

        assert result == {"ok": True}
        assert calls == [{"x": 1}]
        assert await ToolApprovalRequest.all().count() == 0
        execution = await ToolExecution.get(run_id=run_id)
        assert execution.status == ToolExecutionStatus.SUCCEEDED
        assert execution.policy_snapshot["evaluation"]["decision"] == "allow"
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_nested_agent_inside_workflow_never_gates():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            }
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        result = await execute_stored_tool(
            tool,
            "read",
            {},
            _context(
                user,
                team,
                ExecutionEntrypoint.NESTED_AGENT,
                run_kind=ExecutionRunKind.WORKFLOW,
                run_id=uuid4(),
                tool_call_id="workflow-agent:1",
                interactive=False,
                require_approval=True,
            ),
            invoke,
        )

        assert result == {"ok": True}
        assert len(calls) == 1
        assert await ToolApprovalRequest.all().count() == 0
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_workflow_ignores_legacy_external_tool_audience():
    """A deprecated audience must not park or reject a workflow call."""
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "team_role", "roles": ["owner"]}],
            }
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        result = await execute_stored_tool(
            tool,
            "read",
            {},
            _context(
                user,
                team,
                ExecutionEntrypoint.API_KEY,
                run_kind=ExecutionRunKind.WORKFLOW,
                run_id=uuid4(),
                tool_call_id="workflow-node:legacy",
                interactive=False,
            ),
            invoke,
        )

        assert result == {"ok": True}
        assert len(calls) == 1
        assert await ToolApprovalRequest.all().count() == 0
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_parked_workflow_execution_is_cancelled_not_resumed():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(approval_policy={"default_decision": "allow"})
        run_id = uuid4()
        tool_call_id = "workflow-node:parked"
        execution = await ToolExecution.create(
            actor_user=user,
            team=team,
            tool=tool,
            tool_definition_version=tool.definition_version,
            operation="read",
            entrypoint=ExecutionEntrypoint.API_KEY,
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=run_id,
            tool_call_id=tool_call_id,
            parameters_cipher="gAAAAA-ciphertext",
            parameters_digest="a" * 64,
            policy_snapshot={
                "layers": [
                    {
                        "source": PolicySource.TEAM.value,
                        "label": "team",
                        "policy": {
                            "default_decision": "require_approval",
                            "gates": [{"kind": "caller"}],
                        },
                    }
                ]
            },
            policy_hash="b" * 64,
            binding_hash="c" * 64,
            status=ToolExecutionStatus.AWAITING_APPROVAL,
        )
        request = await ToolApprovalRequest.create(
            execution=execution,
            stage_index=0,
            stage_key="caller:0",
            gate_kind="caller",
            approver_user_ids=[],
            approver_roles=[],
            allow_self_approval=False,
            status=ApprovalRequestStatus.PENDING,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as blocked:
            await execute_stored_tool(
                tool,
                "read",
                {},
                _context(
                    user,
                    team,
                    ExecutionEntrypoint.API_KEY,
                    run_kind=ExecutionRunKind.WORKFLOW,
                    run_id=run_id,
                    tool_call_id=tool_call_id,
                    interactive=False,
                ),
                invoke,
            )

        assert blocked.value.code == ResponseCode.TOOL_APPROVAL_BINDING_CHANGED
        assert calls == []
        await execution.refresh_from_db()
        await request.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED
        assert execution.cancel_reason == ToolExecutionCancelReason.CANCELLED
        assert request.status == ApprovalRequestStatus.CANCELLED
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_approved_api_key_execution_claims_and_runs_original_parameters():
    """Decision -> READY -> worker re-entry keeps the stored policy hash.

    Re-entering ``execute_stored_tool`` for an approved API-key execution must
    claim it even though the resume path does not pass the creation-only
    ``caller_self_approvable`` hint: that hint affects configuration errors,
    not the policy fingerprint. Empty/placeholder resume arguments are ignored
    in favour of the approved encrypted parameters.
    """
    from app.models.agent import Agent, Conversation
    from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
    from app.models.api_key import APIKey
    from app.schemas.tool_approval import ApprovalVote
    from app.services import tool_approvals
    from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            }
        )
        agent = await Agent.create(id=uuid4(), team_id=team.id, name="api-key-agent")
        conversation = await Conversation.create(
            id=uuid4(), agent_id=agent.id, user_id=user.id
        )
        run = await AgentRun.create(
            id=uuid4(),
            agent_id=agent.id,
            conversation_id=conversation.id,
            user_id=user.id,
            mode=AgentRunMode.SEND,
            status=AgentRunStatus.RUNNING,
        )
        key = await APIKey.create(
            id=uuid4(),
            name="bound key",
            key_prefix=f"clou_{uuid4().hex[:6]}"[:12],
            key_hash="x",
            user_id=user.id,
            is_active=True,
        )
        run.api_key_id = key.id
        await run.save(update_fields=["api_key_id"])

        identity = RuntimeToolIdentity(
            run_id=run.id,
            tool_call_id="call-1",
            entrypoint=ExecutionEntrypoint.API_KEY.value,
            entrypoint_id=str(key.id),
            api_key_id=key.id,
            interactive=False,
        )
        context = _context(
            user,
            team,
            ExecutionEntrypoint.API_KEY,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run.id,
            tool_call_id="call-1",
            interactive=False,
            entrypoint_id=str(key.id),
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        with tool_identity_scope(identity):
            pending = await execute_stored_tool(
                tool, "read", {"ticket": "T-1"}, context, invoke
            )
        assert isinstance(pending, PendingToolApproval)
        execution = await ToolExecution.get(id=pending.execution_id)
        assert execution.api_key_id == key.id
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL
        request = await ToolApprovalRequest.get(
            execution_id=execution.id, status=ApprovalRequestStatus.PENDING
        )

        await tool_approvals.decide_approval(
            request.id,
            user,
            decision=ApprovalVote.APPROVE,
            idempotency_key="api-key-resume-1",
            api_key=key,
        )
        assert (
            await ToolExecution.get(id=execution.id)
        ).status == ToolExecutionStatus.READY

        with tool_identity_scope(identity):
            result = await execute_stored_tool(tool, "read", {}, context, invoke)

        assert result == {"ok": True}
        assert calls == [{"ticket": "T-1"}]
        stored = await ToolExecution.get(id=execution.id)
        assert stored.status == ToolExecutionStatus.SUCCEEDED
        assert stored.api_key_id == key.id
    finally:
        await Tortoise.close_connections()
