"""Removed site/team/entrypoint layers must invalidate unstarted work safely.

Only the tool layer remains. Unstarted executions whose frozen snapshot bound a
retired layer are cancelled with ``binding_changed`` so a pending approval from
the old policy can never be approved or executed under the new rules.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.tool_approval_policy_cutover import (
    cancel_unstarted_layer_bound_executions,
    migrate_removed_approval_policy_layers,
    resume_runs_waiting_on_terminal_approval,
    snapshot_has_removed_layers,
)
from app.models.agent import Agent, Conversation, Message, MessageRole
from app.models.agent_run import AgentRun, AgentRunMode, AgentRunStatus
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_approval import (
    ToolApprovalRequest,
    ToolExecution,
)
from app.models.user import Team, User
from app.models.workflow import (
    NodeExecution,
    NodeStatus,
    RunStatus,
    TriggerType,
    Workflow,
    WorkflowRun,
)
from app.schemas.tool_approval import (
    ApprovalGateKind,
    ApprovalRequestStatus,
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.services.workflow.tool_approval_resume import tool_call_token


def _digest(char: str) -> str:
    return char * 64


@pytest.fixture
def run_orm():
    with asyncio.Runner() as runner:

        def run(scenario, *, generate: bool = True):
            async def wrapped():
                async with TortoiseContext() as context:
                    await context.init(
                        db_url="sqlite://:memory:", modules={"models": ["app.models"]}
                    )
                    if generate:
                        await context.generate_schemas()
                    await scenario()

            runner.run(wrapped())

        yield run


def _tool_snapshot() -> dict:
    return {
        "evaluation": {"decision": "allow"},
        "layers": [
            {"source": "tool", "label": "tool", "policy": {"default_decision": "allow"}}
        ],
    }


def _layer_snapshot(source: str = "team") -> dict:
    return {
        "evaluation": {"decision": "require_approval"},
        "layers": [
            {
                "source": "tool",
                "label": "tool",
                "policy": {"default_decision": "allow"},
            },
            {
                "source": source,
                "label": source,
                "policy": {
                    "default_decision": "require_approval",
                    "gates": [{"kind": "caller"}],
                },
            },
        ],
    }


async def _fixtures():
    owner = await User.create(
        username=f"owner_{uuid4().hex[:8]}",
        email=f"owner_{uuid4().hex[:8]}@cutover.test",
        hashed_password="x",
    )
    team = await Team.create(name=f"cutover_{uuid4().hex[:8]}", owner=owner)
    tool = await Tool.create(
        id=uuid4(),
        team=team,
        name=f"tool_{uuid4().hex[:8]}",
        display_name="Cutover tool",
        description="cutover test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        approval_policy={"default_decision": "allow"},
    )
    return owner, team, tool


async def _execution(
    team,
    tool,
    actor,
    *,
    status=ToolExecutionStatus.AWAITING_APPROVAL,
    snapshot=None,
    entrypoint=ExecutionEntrypoint.CHAT,
    run_kind=None,
    run_id=None,
    tool_call_id=None,
    cancel_reason=None,
):
    return await ToolExecution.create(
        actor_user=actor,
        effective_user=actor,
        team=team,
        tool=tool,
        tool_definition_version=1,
        operation="ticket.close",
        entrypoint=entrypoint,
        run_kind=run_kind,
        run_id=run_id,
        tool_call_id=tool_call_id,
        parameters_cipher="gAAAAA-ciphertext",
        parameters_digest=_digest("a"),
        policy_snapshot=snapshot if snapshot is not None else _layer_snapshot(),
        policy_hash=_digest("b"),
        binding_hash=_digest("c"),
        status=status,
        cancel_reason=cancel_reason,
    )


async def _request(execution):
    return await ToolApprovalRequest.create(
        execution=execution,
        stage_index=0,
        stage_key="caller:0",
        gate_kind=ApprovalGateKind.CALLER,
        approver_user_ids=[],
        approver_roles=[],
        allow_self_approval=False,
        status=ApprovalRequestStatus.PENDING,
    )


async def _agent_waiting_run(owner, team, *, pending_tool_call_id="call-1"):
    agent = await Agent.create(
        id=uuid4(), team_id=team.id, name=f"agent_{uuid4().hex[:8]}"
    )
    conversation = await Conversation.create(
        id=uuid4(), agent_id=agent.id, user_id=owner.id
    )
    round_id = uuid4()
    run = await AgentRun.create(
        id=uuid4(),
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=owner.id,
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.WAITING,
        active_round_id=round_id,
        pending_tool_call_id=pending_tool_call_id,
        pending_tool_name="cutover_tool",
        pending_tool_input={"interaction_kind": "tool_approval"},
        pending_tool_round_id=round_id,
        pending_tool_round_index=1,
        pending_tool_iteration_index=0,
        worker_payload={
            "history_override": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": pending_tool_call_id,
                            "name": "cutover_tool",
                            "arguments": {"interaction_kind": "tool_approval"},
                        }
                    ],
                    "round_id": str(round_id),
                    "round_index": 1,
                    "round_role": "assistant_step",
                    "is_round_canonical": False,
                    "iteration_index": 0,
                }
            ],
            "pending_tool_display_name": "Cutover tool",
        },
    )
    return conversation, run


async def _workflow_waiting_run(owner, team):
    workflow = await Workflow.create(
        id=uuid4(), team_id=team.id, name=f"wf_{uuid4().hex[:8]}"
    )
    run = await WorkflowRun.create(
        id=uuid4(),
        workflow_id=workflow.id,
        trigger_type=TriggerType.MANUAL,
        triggered_by_id=owner.id,
        status=RunStatus.WAITING,
        inputs={},
        context_snapshot={},
    )
    node = await NodeExecution.create(
        run_id=run.id,
        node_id="tool_1",
        node_type="tool",
        node_name="Tool",
        execution_order=0,
        status=NodeStatus.WAITING,
    )
    return run, node


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (_tool_snapshot(), False),
        (_layer_snapshot(), True),
        (_layer_snapshot("site"), True),
        (_layer_snapshot("entrypoint"), True),
        ({"layers": []}, False),
        ({"layers": "broken"}, False),
        ({"layers": ["broken"]}, False),
        ({"layers": [{"source": None}]}, False),
        ({}, False),
        (None, False),
    ],
)
def test_snapshot_has_removed_layers(snapshot, expected):
    assert snapshot_has_removed_layers(snapshot) is expected


def test_cancels_awaiting_layer_bound_execution_and_its_gate(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(team, tool, actor)
        request = await _request(execution)

        summary = await cancel_unstarted_layer_bound_executions()

        assert summary == {
            "executions_cancelled": 1,
            "requests_cancelled": 1,
            "agent_runs_resumed": 0,
            "workflow_runs_resumed": 0,
        }
        await execution.refresh_from_db()
        await request.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED
        assert execution.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED
        assert execution.finished_at is not None
        assert request.status == ApprovalRequestStatus.CANCELLED
        assert request.resolved_at is not None

    run_orm(scenario)


def test_cancels_ready_layer_bound_execution(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(
            team, tool, actor, status=ToolExecutionStatus.READY
        )

        summary = await cancel_unstarted_layer_bound_executions()

        assert summary["executions_cancelled"] == 1
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.CANCELLED
        assert execution.cancel_reason == ToolExecutionCancelReason.BINDING_CHANGED

    run_orm(scenario)


def test_preserves_tool_only_unstarted_executions(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        awaiting = await _execution(team, tool, actor, snapshot=_tool_snapshot())
        ready = await _execution(
            team,
            tool,
            actor,
            status=ToolExecutionStatus.READY,
            snapshot=_tool_snapshot(),
        )

        summary = await cancel_unstarted_layer_bound_executions()

        assert summary == {
            "executions_cancelled": 0,
            "requests_cancelled": 0,
            "agent_runs_resumed": 0,
            "workflow_runs_resumed": 0,
        }
        await awaiting.refresh_from_db()
        await ready.refresh_from_db()
        assert awaiting.status == ToolExecutionStatus.AWAITING_APPROVAL
        assert ready.status == ToolExecutionStatus.READY

    run_orm(scenario)


def test_never_cancels_executing_or_terminal_rows(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        executing = await _execution(
            team, tool, actor, status=ToolExecutionStatus.EXECUTING
        )
        succeeded = await _execution(
            team, tool, actor, status=ToolExecutionStatus.SUCCEEDED
        )

        summary = await cancel_unstarted_layer_bound_executions()

        assert summary["executions_cancelled"] == 0
        await executing.refresh_from_db()
        await succeeded.refresh_from_db()
        assert executing.status == ToolExecutionStatus.EXECUTING
        assert succeeded.status == ToolExecutionStatus.SUCCEEDED

    run_orm(scenario)


def test_rerun_is_idempotent(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        execution = await _execution(team, tool, actor)
        request = await _request(execution)

        first = await cancel_unstarted_layer_bound_executions()
        await execution.refresh_from_db()
        await request.refresh_from_db()
        execution_updated_at = execution.updated_at
        request_updated_at = request.updated_at

        second = await cancel_unstarted_layer_bound_executions()

        assert first == {
            "executions_cancelled": 1,
            "requests_cancelled": 1,
            "agent_runs_resumed": 0,
            "workflow_runs_resumed": 0,
        }
        assert second == {
            "executions_cancelled": 0,
            "requests_cancelled": 0,
            "agent_runs_resumed": 0,
            "workflow_runs_resumed": 0,
        }
        await execution.refresh_from_db()
        await request.refresh_from_db()
        assert execution.updated_at == execution_updated_at
        assert request.updated_at == request_updated_at

    run_orm(scenario)


def test_migration_entrypoint_reports_the_cutover(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        await _execution(team, tool, actor)

        summary = await migrate_removed_approval_policy_layers()

        assert summary["executions_cancelled"] == 1

    run_orm(scenario)


def test_cutover_wakes_a_waiting_agent_run_with_the_terminal_error(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        conversation, agent_run = await _agent_waiting_run(actor, team)
        await _execution(
            team,
            tool,
            actor,
            entrypoint=ExecutionEntrypoint.AGENT_RUN,
            run_kind=ExecutionRunKind.AGENT,
            run_id=agent_run.id,
            tool_call_id="call-1",
        )
        dispatch = AsyncMock()

        with (
            patch("app.services.agent_run_store.record_observability_progress"),
            patch(
                "app.services.agent_run_store._write_state_cache",
                new=AsyncMock(),
            ),
            patch("app.services.agent_submission.dispatch_run", new=dispatch),
        ):
            summary = await cancel_unstarted_layer_bound_executions()

        assert summary["executions_cancelled"] == 1
        assert summary["agent_runs_resumed"] == 1
        await agent_run.refresh_from_db()
        assert agent_run.status == AgentRunStatus.QUEUED
        assert agent_run.pending_tool_call_id is None
        message = await Message.filter(
            conversation_id=conversation.id, role=MessageRole.TOOL
        ).first()
        assert message is not None
        assert "binding changed" in message.content
        dispatch.assert_awaited_once()

    run_orm(scenario)


def test_agent_run_with_a_different_pending_call_stays_waiting(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        _conversation, agent_run = await _agent_waiting_run(
            actor, team, pending_tool_call_id="other-call"
        )
        execution = await _execution(
            team,
            tool,
            actor,
            entrypoint=ExecutionEntrypoint.AGENT_RUN,
            run_kind=ExecutionRunKind.AGENT,
            run_id=agent_run.id,
            tool_call_id="call-1",
        )
        dispatch = AsyncMock()

        with (
            patch("app.services.agent_run_store.record_observability_progress"),
            patch(
                "app.services.agent_run_store._write_state_cache",
                new=AsyncMock(),
            ),
            patch("app.services.agent_submission.dispatch_run", new=dispatch),
        ):
            summary = await cancel_unstarted_layer_bound_executions()

        assert summary["executions_cancelled"] == 1
        assert summary["agent_runs_resumed"] == 0
        await agent_run.refresh_from_db()
        await execution.refresh_from_db()
        assert agent_run.status == AgentRunStatus.WAITING
        assert execution.status == ToolExecutionStatus.CANCELLED
        dispatch.assert_not_awaited()

    run_orm(scenario)


@pytest.mark.parametrize(
    "cancel_reason",
    [
        ToolExecutionCancelReason.BINDING_CHANGED,
        ToolExecutionCancelReason.CANCELLED,
    ],
)
def test_restart_reconciliation_wakes_an_already_cancelled_agent_execution(
    run_orm, cancel_reason
):
    async def scenario():
        actor, team, tool = await _fixtures()
        _conversation, agent_run = await _agent_waiting_run(actor, team)
        await _execution(
            team,
            tool,
            actor,
            status=ToolExecutionStatus.CANCELLED,
            cancel_reason=cancel_reason,
            entrypoint=ExecutionEntrypoint.AGENT_RUN,
            run_kind=ExecutionRunKind.AGENT,
            run_id=agent_run.id,
            tool_call_id="call-1",
        )
        dispatch = AsyncMock()

        with (
            patch("app.services.agent_run_store.record_observability_progress"),
            patch(
                "app.services.agent_run_store._write_state_cache",
                new=AsyncMock(),
            ),
            patch("app.services.agent_submission.dispatch_run", new=dispatch),
        ):
            first = await resume_runs_waiting_on_terminal_approval()
            second = await resume_runs_waiting_on_terminal_approval()

        assert first["agent_runs_resumed"] == 1
        assert second["agent_runs_resumed"] == 0
        await agent_run.refresh_from_db()
        assert agent_run.status == AgentRunStatus.QUEUED
        dispatch.assert_awaited_once()

    run_orm(scenario)


def test_cutover_wakes_a_waiting_workflow_run(run_orm):
    async def scenario():
        actor, team, tool = await _fixtures()
        workflow_run, node = await _workflow_waiting_run(actor, team)
        await _execution(
            team,
            tool,
            actor,
            entrypoint=ExecutionEntrypoint.WORKFLOW,
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=workflow_run.id,
            tool_call_id=tool_call_token(node.id),
        )

        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            summary = await cancel_unstarted_layer_bound_executions()

        assert summary["executions_cancelled"] == 1
        assert summary["workflow_runs_resumed"] == 1
        dispatch.assert_called_once_with(str(workflow_run.id))
        await workflow_run.refresh_from_db()
        # The mocked task has not claimed the run yet.
        assert workflow_run.status == RunStatus.WAITING

        workflow_run.status = RunStatus.RUNNING
        await workflow_run.save(update_fields=["status"])
        with patch("app.tasks.workflow.resume_workflow_task.delay") as repeated:
            again = await resume_runs_waiting_on_terminal_approval()
        assert again["workflow_runs_resumed"] == 0
        repeated.assert_not_called()

    run_orm(scenario)


def test_restart_reconciliation_wakes_an_already_cancelled_workflow_execution(
    run_orm,
):
    async def scenario():
        actor, team, tool = await _fixtures()
        workflow_run, node = await _workflow_waiting_run(actor, team)
        await _execution(
            team,
            tool,
            actor,
            status=ToolExecutionStatus.CANCELLED,
            cancel_reason=ToolExecutionCancelReason.BINDING_CHANGED,
            entrypoint=ExecutionEntrypoint.WORKFLOW,
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=workflow_run.id,
            tool_call_id=tool_call_token(node.id),
        )

        with patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch:
            summary = await resume_runs_waiting_on_terminal_approval()

        assert summary["workflow_runs_resumed"] == 1
        dispatch.assert_called_once_with(str(workflow_run.id))

    run_orm(scenario)


def test_missing_tables_are_a_noop(run_orm):
    async def scenario():
        summary = await cancel_unstarted_layer_bound_executions()

        assert summary == {
            "executions_cancelled": 0,
            "requests_cancelled": 0,
            "agent_runs_resumed": 0,
            "workflow_runs_resumed": 0,
        }

    run_orm(scenario, generate=False)
