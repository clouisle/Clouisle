"""Workflow tool node approval parking/resume on real SQLite.

The tool node must never block on an approval and must never run a rejected or
expired request. These tests pin the workflow half of that contract: the parked
node reuses one stable call id, a terminal decision fails the node without a
side effect, and only a waiting workflow run is resumed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_approval import ToolExecution
from app.models.user import Team, TeamMember, User
from app.models.workflow import (
    NodeExecution,
    NodeStatus,
    RunStatus,
    TriggerType,
    Workflow,
    WorkflowRun,
)
from app.schemas.tool_approval import (
    ApprovalVote,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services import tool_approvals
from app.services.tool_execution import PendingToolApproval
from app.services.workflow import tool_approval_resume
from app.services.workflow.execution_origin import (
    ORIGIN_SNAPSHOT_KEY,
    WorkflowExecutionOrigin,
    api_key_origin,
    embed_origin,
    origin_snapshot,
    schedule_origin,
)
from app.services.workflow.executors.tool import ToolNodeExecutor


class _Redis:
    async def set(self, key, value, ex=None, nx=False):
        return True

    async def get(self, key):
        return None

    async def hgetall(self, key):
        return {}

    async def hset(self, key, field=None, value=None, mapping=None):
        return 1

    async def delete(self, key):
        return True

    async def expire(self, key, seconds):
        return True

    async def publish(self, channel, message):
        return 1


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


def _caller_policy() -> dict:
    return {"default_decision": "require_approval", "gates": [{"kind": "caller"}]}


def _allow_policy() -> dict:
    return {"default_decision": "allow"}


async def _actor() -> tuple[User, Team]:
    user = await User.create(
        id=uuid4(),
        username=f"wf_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@workflow-approval.test",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name=f"wf_team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role="owner")
    return user, team


async def _workflow(team: Team) -> Workflow:
    return await Workflow.create(
        id=uuid4(), team_id=team.id, name=f"wf_{uuid4().hex[:6]}"
    )


async def _run(
    workflow: Workflow,
    user: User,
    *,
    status: RunStatus = RunStatus.WAITING,
    trigger: TriggerType = TriggerType.MANUAL,
    origin: WorkflowExecutionOrigin | None = None,
) -> WorkflowRun:
    snapshot = (
        {ORIGIN_SNAPSHOT_KEY: origin_snapshot(origin)} if origin is not None else {}
    )
    return await WorkflowRun.create(
        id=uuid4(),
        workflow_id=workflow.id,
        trigger_type=trigger,
        triggered_by_id=user.id,
        status=status,
        inputs={},
        context_snapshot=snapshot,
    )


async def _node_execution(
    run: WorkflowRun,
    node_id: str = "tool_1",
    *,
    order: int = 0,
    status: NodeStatus = NodeStatus.RUNNING,
) -> NodeExecution:
    return await NodeExecution.create(
        run_id=run.id,
        node_id=node_id,
        node_type="tool",
        node_name="Tool",
        execution_order=order,
        status=status,
    )


async def _tool(team: Team, policy: dict, tool_type=ToolType.CUSTOM) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"wf_tool_{uuid4().hex[:8]}",
        display_name="Workflow approval tool",
        description="workflow approval test",
        type=tool_type,
        custom_type=CustomToolType.HTTP if tool_type == ToolType.CUSTOM else None,
        approval_policy=policy,
    )


def _node(tool: Tool, *, mcp_tool_name: str | None = None) -> dict:
    config: dict = {"toolId": str(tool.id), "toolType": "custom"}
    if mcp_tool_name is not None:
        config["mcpToolName"] = mcp_tool_name
    return {"id": "tool_1", "type": "tool", "data": {"toolConfig": config}}


def _context() -> MagicMock:
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value="value")
    return context


async def _deferred_execution(
    *,
    tool: Tool,
    user: User,
    team: Team,
    workflow: Workflow,
    run: WorkflowRun,
    node_id: str = "tool_1",
    operation: str | None = None,
) -> tuple[ToolExecution, str]:
    """Create the execution the parked node would have created."""
    token = await tool_approval_resume.token_for_attempt(run, node_id)
    execution = await tool_approvals.create_execution(
        tool=tool,
        operation=operation or tool.name,
        parameters={"id": 7},
        actor=user,
        team_id=team.id,
        entrypoint=ExecutionEntrypoint.WORKFLOW,
        entrypoint_id=str(workflow.id),
        run_kind=ExecutionRunKind.WORKFLOW,
        run_id=run.id,
        tool_call_id=token,
    )
    return execution, token


@pytest.mark.asyncio
async def test_park_reuses_one_stable_call_id_across_resume():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.RUNNING)
        node_execution = await _node_execution(run)
        tool = await _tool(team, _caller_policy())
        node = _node(tool, mcp_tool_name="search_code")

        pending = PendingToolApproval(execution_id=uuid4(), tool_name=tool.name)
        boundary = AsyncMock(return_value=pending)
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            first = await ToolNodeExecutor().execute(node, _context(), run)
            first_context = boundary.await_args.kwargs["context"]

            # The orchestrator reuses the same WAITING NodeExecution on resume.
            node_execution.status = NodeStatus.WAITING
            await node_execution.save()
            node_execution.status = NodeStatus.RUNNING
            await node_execution.save()
            second = await ToolNodeExecutor().execute(node, _context(), run)
            second_context = boundary.await_args.kwargs["context"]

        assert first.waiting is True
        assert second.waiting is True
        expected_token = tool_approval_resume.tool_call_token(node_execution.id)
        assert first_context.tool_call_id == expected_token
        assert second_context.tool_call_id == expected_token
        assert first_context.actor.id == user.id
        assert first_context.team_id == team.id
        assert first_context.entrypoint is ExecutionEntrypoint.WORKFLOW
        assert first_context.entrypoint_id == str(workflow.id)
        assert first_context.run_kind is ExecutionRunKind.WORKFLOW
        assert first_context.run_id == run.id
        assert first_context.interactive is False
        assert first_context.connection_mode is None
        # The MCP original tool name, not a model-facing alias, is the operation.
        assert boundary.await_args.kwargs["operation"] == "search_code"


@pytest.mark.asyncio
async def test_new_node_attempt_gets_a_new_call_id():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.RUNNING)
        first = await _node_execution(run, order=0)
        second = await _node_execution(run, order=1)

        assert await tool_approval_resume.token_for_attempt(
            run, "tool_1"
        ) == tool_approval_resume.tool_call_token(second.id)
        assert tool_approval_resume.tool_call_token(first.id) != (
            tool_approval_resume.tool_call_token(second.id)
        )


@pytest.mark.asyncio
async def test_rejected_approval_fails_the_node_without_executing():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user)
        await _node_execution(run, status=NodeStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=run
        )
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL

        request = await tool_approvals.ToolApprovalRequest.filter(
            execution_id=execution.id
        ).first()
        with patch("app.tasks.workflow.resume_workflow_task.delay"):
            await tool_approvals.decide_approval(
                request.id,
                user,
                decision=ApprovalVote.REJECT,
                idempotency_key="reject-1",
            )

        boundary = AsyncMock()
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            result = await ToolNodeExecutor().execute(_node(tool), _context(), run)

        assert result.success is False
        assert result.error == "tool_approval_rejected"
        assert result.outputs["status"] == "error"
        assert result.outputs["result"] is None
        boundary.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_approval_fails_the_node_without_executing():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user)
        await _node_execution(run, status=NodeStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=run
        )
        await ToolExecution.filter(id=execution.id).update(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        )

        boundary = AsyncMock()
        with (
            patch("app.services.tool.ToolExecutor.execute", new=boundary),
            patch("app.tasks.workflow.resume_workflow_task.delay"),
        ):
            result = await ToolNodeExecutor().execute(_node(tool), _context(), run)

        assert result.error == "tool_approval_expired"
        boundary.assert_not_awaited()
        stored = await ToolExecution.get(id=execution.id)
        assert stored.status == ToolExecutionStatus.CANCELLED
        assert stored.cancel_reason == ToolExecutionCancelReason.EXPIRED


@pytest.mark.asyncio
async def test_approved_execution_runs_the_stored_call_once():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user)
        await _node_execution(run, status=NodeStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, token = await _deferred_execution(
            tool=tool,
            user=user,
            team=team,
            workflow=workflow,
            run=run,
            operation="search_code",
        )
        request = await tool_approvals.ToolApprovalRequest.filter(
            execution_id=execution.id
        ).first()
        with patch("app.tasks.workflow.resume_workflow_task.delay"):
            await tool_approvals.decide_approval(
                request.id,
                user,
                decision=ApprovalVote.APPROVE,
                idempotency_key="approve-1",
            )
        assert (await ToolExecution.get(id=execution.id)).status == (
            ToolExecutionStatus.READY
        )

        boundary = AsyncMock(return_value={"ok": True})
        with (
            patch("app.services.tool.ToolExecutor.execute", new=boundary),
            patch("app.tasks.workflow.resume_workflow_task.delay"),
        ):
            result = await ToolNodeExecutor().execute(
                _node(tool, mcp_tool_name="search_code"), _context(), run
            )

        assert result.success is True
        assert result.outputs["result"] == {"ok": True}
        boundary.assert_awaited_once()
        kwargs = boundary.await_args.kwargs
        assert kwargs["context"].tool_call_id == token
        assert kwargs["operation"] == "search_code"
        assert kwargs["tool"].id == tool.id
        assert kwargs["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_allow_policy_tool_executes_without_parking():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.RUNNING)
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            result = await ToolNodeExecutor().execute(_node(tool), _context(), run)

        assert result.waiting is False
        assert result.success is True
        boundary.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_run_of_a_cron_workflow_keeps_the_workflow_surface():
    """Regression: trigger_type mirrors configuration, not provenance."""
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(
            workflow, user, status=RunStatus.RUNNING, trigger=TriggerType.CRON
        )
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            await ToolNodeExecutor().execute(_node(tool), _context(), run)

        context = boundary.await_args.kwargs["context"]
        assert context.entrypoint is ExecutionEntrypoint.WORKFLOW
        assert context.entrypoint_id == str(workflow.id)
        assert context.interactive is False


@pytest.mark.asyncio
async def test_schedule_origin_uses_the_schedule_surface():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(
            workflow,
            user,
            status=RunStatus.RUNNING,
            origin=schedule_origin(workflow.id),
        )
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            await ToolNodeExecutor().execute(_node(tool), _context(), run)

        context = boundary.await_args.kwargs["context"]
        assert context.entrypoint is ExecutionEntrypoint.SCHEDULE
        assert context.entrypoint_id == str(workflow.id)
        assert context.interactive is False


@pytest.mark.asyncio
async def test_api_key_origin_binds_the_key_and_node_config_cannot_override_it():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        api_key_id = uuid4()
        run = await _run(
            workflow,
            user,
            status=RunStatus.RUNNING,
            trigger=TriggerType.MANUAL,
            origin=api_key_origin(api_key_id),
        )
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())
        connection_id = uuid4()
        grant_id = uuid4()
        node = _node(tool)
        node["data"]["toolConfig"].update(
            {
                "toolType": "custom",
                "connectionMode": "personal",
                "connectionId": str(connection_id),
                "grantId": str(grant_id),
            }
        )

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            await ToolNodeExecutor().execute(node, _context(), run)

        context = boundary.await_args.kwargs["context"]
        # The surface comes from persisted provenance (the API key), never from
        # node config or the workflow's configured trigger.
        assert context.entrypoint is ExecutionEntrypoint.API_KEY
        assert context.entrypoint_id == str(api_key_id)
        assert context.interactive is False
        assert context.connection_mode == "personal"
        assert context.connection_id == connection_id
        assert context.grant_id == grant_id


@pytest.mark.asyncio
async def test_embed_origin_is_its_own_surface():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(
            workflow,
            user,
            status=RunStatus.RUNNING,
            origin=embed_origin(workflow.id),
        )
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            await ToolNodeExecutor().execute(_node(tool), _context(), run)

        context = boundary.await_args.kwargs["context"]
        assert context.entrypoint is ExecutionEntrypoint.EMBED
        assert context.entrypoint_id == str(workflow.id)


@pytest.mark.asyncio
async def test_anonymous_run_never_executes_a_tool():
    async with _database():
        _user, team = await _actor()
        workflow = await _workflow(team)
        run = await WorkflowRun.create(
            id=uuid4(),
            workflow_id=workflow.id,
            trigger_type=TriggerType.WEBHOOK,
            triggered_by_id=None,
            status=RunStatus.RUNNING,
            inputs={},
        )
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            result = await ToolNodeExecutor().execute(_node(tool), _context(), run)

        assert result.error == "user_context_required"
        boundary.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_tool_without_internal_operation_fails_closed():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.RUNNING)
        await _node_execution(run)
        tool = await _tool(team, _allow_policy(), tool_type=ToolType.MCP)

        boundary = AsyncMock(return_value={"ok": True})
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            result = await ToolNodeExecutor().execute(_node(tool), _context(), run)

        assert result.error == "invalid_tool_arguments"
        boundary.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_approval_inside_a_container_cancels_and_fails():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.RUNNING)
        await _node_execution(run)
        tool = await _tool(team, _allow_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=run
        )
        # Confirm the fixture starts awaiting, then let the boundary report it.
        assert execution.status in {
            ToolExecutionStatus.READY,
            ToolExecutionStatus.AWAITING_APPROVAL,
        }
        node = _node(tool)
        node["data"]["parentId"] = "iteration_1"

        boundary = AsyncMock(return_value=PendingToolApproval(execution.id, tool.name))
        with patch("app.services.tool.ToolExecutor.execute", new=boundary):
            result = await ToolNodeExecutor().execute(node, _context(), run)

        assert result.waiting is False
        assert result.error == "tool_approval_inside_container"
        stored = await ToolExecution.get(id=execution.id)
        assert stored.status == ToolExecutionStatus.CANCELLED
        assert stored.cancel_reason == ToolExecutionCancelReason.CANCELLED


@pytest.mark.asyncio
async def test_resume_dispatch_only_for_a_waiting_workflow_run():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        waiting = await _run(workflow, user, status=RunStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=waiting
        )

        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            run = await tool_approval_resume.schedule_workflow_run_approval_resume(
                execution
            )
        assert run is not None and run.id == waiting.id
        dispatch.assert_called_once_with(str(waiting.id))

        stopped = await _run(workflow, user, status=RunStatus.CANCELLED)
        stopped_execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=stopped
        )
        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            assert (
                await tool_approval_resume.schedule_workflow_run_approval_resume(
                    stopped_execution
                )
                is None
            )
        dispatch.assert_not_called()

        # A non-workflow execution is never routed by the workflow scheduler.
        assert (
            await tool_approval_resume.schedule_workflow_run_approval_resume(None)
            is None
        )


@pytest.mark.asyncio
async def test_park_race_resumes_when_the_decision_is_already_committed():
    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.WAITING)
        await _node_execution(run, status=NodeStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=run
        )

        # Still awaiting: the decision hook owns the resume.
        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            assert (
                await tool_approval_resume.ensure_resume_after_park(run, "tool_1")
                is False
            )
        dispatch.assert_not_called()

        request = await tool_approvals.ToolApprovalRequest.filter(
            execution_id=execution.id
        ).first()
        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            await tool_approvals.decide_approval(
                request.id,
                user,
                decision=ApprovalVote.APPROVE,
                idempotency_key="race-1",
            )
        # The decision was made while the run was still RUNNING at decision
        # time in the real race; here the run is already WAITING and both paths
        # converge on one dispatch per call.
        for call in dispatch.call_args_list:
            assert call.args == (str(run.id),)

        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            assert (
                await tool_approval_resume.ensure_resume_after_park(run, "tool_1")
                is True
            )
        dispatch.assert_called_once_with(str(run.id))


@pytest.mark.asyncio
async def test_stopping_a_waiting_run_cancels_its_pending_approval():
    from app.services.workflow import WorkflowOrchestrator

    async with _database():
        user, team = await _actor()
        workflow = await _workflow(team)
        run = await _run(workflow, user, status=RunStatus.WAITING)
        await _node_execution(run, status=NodeStatus.WAITING)
        tool = await _tool(team, _caller_policy())
        execution, _ = await _deferred_execution(
            tool=tool, user=user, team=team, workflow=workflow, run=run
        )

        stream_manager = MagicMock()
        stream_manager.publish_workflow_error = AsyncMock()
        with (
            patch(
                "app.services.workflow.orchestrator.get_redis",
                new=AsyncMock(return_value=_Redis()),
            ),
            patch(
                "app.services.workflow.orchestrator.StreamManager",
                return_value=stream_manager,
            ),
            patch(
                "app.services.workflow.orchestrator._persist_observability_summary",
                new=AsyncMock(),
            ),
            patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch,
        ):
            assert await WorkflowOrchestrator().cancel(str(run.id)) is True

        stored = await ToolExecution.get(id=execution.id)
        assert stored.status == ToolExecutionStatus.CANCELLED
        assert stored.cancel_reason == ToolExecutionCancelReason.RUN_STOPPED
        dispatch.assert_not_called()
