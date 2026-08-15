"""Behavioral coverage for orchestrator node lifecycle and retry routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus
from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
)
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.orchestrator import WorkflowOrchestrator


@pytest.fixture
def node_plan():
    """Build the minimum plan data needed for one node execution."""
    node = MagicMock()
    node.node_type = "llm"
    node.node_data = {"data": {"label": "Generate"}}
    plan = MagicMock()
    plan.get_node.return_value = node
    return plan


@pytest.fixture
def workflow_run():
    """Build the minimum workflow run needed for node persistence."""
    run = MagicMock()
    run.id = uuid4()
    return run


@pytest.mark.asyncio
async def test_execute_node_persists_serializable_success_output(
    node_plan, workflow_run
):
    """A successful node stores outputs, marks success, and emits completion."""
    orchestrator = WorkflowOrchestrator(enable_retry=False, enable_cache=False)
    context = MagicMock(set_node_outputs=AsyncMock())
    stream = MagicMock(
        publish_node_start=AsyncMock(), publish_node_complete=AsyncMock()
    )
    node_execution = MagicMock(save=AsyncMock())
    executor = MagicMock(
        execute=AsyncMock(return_value=ExecutionResult(outputs={"text": "ok"}))
    )

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as executions,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
    ):
        executions.filter.return_value.all = AsyncMock(return_value=[])
        executions.create = AsyncMock(return_value=node_execution)

        result = await orchestrator._execute_node(
            node_id="generate",
            plan=node_plan,
            context=context,
            run=workflow_run,
            stream_manager=stream,
        )

    assert result.outputs == {"text": "ok"}
    assert node_execution.status == NodeStatus.SUCCESS
    assert node_execution.outputs == {"text": "ok"}
    context.set_node_outputs.assert_awaited_once_with("generate", {"text": "ok"})
    stream.publish_node_complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_node_marks_failed_result_and_emits_public_error(
    node_plan, workflow_run
):
    """A failed executor result is persisted and surfaced as a node error."""
    orchestrator = WorkflowOrchestrator(enable_retry=False, enable_cache=False)
    context = MagicMock()
    stream = MagicMock(publish_node_start=AsyncMock(), publish_node_error=AsyncMock())
    node_execution = MagicMock(save=AsyncMock())
    executor = MagicMock(
        execute=AsyncMock(return_value=ExecutionResult(error="executor failed"))
    )

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as executions,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
    ):
        executions.filter.return_value.all = AsyncMock(return_value=[])
        executions.create = AsyncMock(return_value=node_execution)

        with pytest.raises(NodeExecutionError):
            await orchestrator._execute_node(
                node_id="generate",
                plan=node_plan,
                context=context,
                run=workflow_run,
                stream_manager=stream,
            )

    assert node_execution.status == NodeStatus.FAILED
    assert node_execution.error_type == "NodeExecutionError"
    stream.publish_node_error.assert_awaited_once_with(
        node_id="generate", error=node_execution.error_message
    )


@pytest.mark.asyncio
async def test_execute_node_routes_enabled_retry_through_retryable_executor(
    node_plan, workflow_run
):
    """Retry-enabled nodes use the retry wrapper before completing normally."""
    orchestrator = WorkflowOrchestrator(enable_retry=True, enable_cache=False)
    context = MagicMock(set_node_outputs=AsyncMock())
    node_execution = MagicMock(save=AsyncMock())
    executor = MagicMock()
    retryable = MagicMock(
        execute=AsyncMock(return_value=ExecutionResult(outputs={"text": "retried"}))
    )

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as executions,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
        patch(
            "app.services.workflow.orchestrator.RetryableExecutor",
            return_value=retryable,
        ) as retryable_class,
    ):
        executions.filter.return_value.all = AsyncMock(return_value=[])
        executions.create = AsyncMock(return_value=node_execution)

        result = await orchestrator._execute_node(
            node_id="generate",
            plan=node_plan,
            context=context,
            run=workflow_run,
            stream_manager=None,
        )

    assert result.outputs == {"text": "retried"}
    retryable_class.assert_called_once()
    retryable.execute.assert_awaited_once_with(
        node=node_plan.get_node.return_value.node_data,
        context=context,
        run=workflow_run,
    )
    executor.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "run_status", "notification_method"),
    [
        ("_complete_run", NodeStatus.SUCCESS, "send_to_user"),
        ("_fail_run", NodeStatus.FAILED, "send_to_team"),
    ],
)
async def test_run_finalization_persists_statistics_tokens_and_notification(
    method_name, run_status, notification_method
):
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    team_id = uuid4()
    executions = [
        SimpleNamespace(status=NodeStatus.SUCCESS),
        SimpleNamespace(status=NodeStatus.FAILED),
        SimpleNamespace(status=NodeStatus.SKIPPED),
    ]
    triggered_by_id = uuid4() if method_name == "_complete_run" else None
    run = MagicMock(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=False,
        triggered_by_id=triggered_by_id,
        total_token_usage={"prompt": 2, "completion": 3},
        save=AsyncMock(),
        fetch_related=AsyncMock(),
    )
    run.triggered_by = SimpleNamespace(locale="zh")
    workflow = SimpleNamespace(id=workflow_id, team_id=team_id, name="Release workflow")

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
        patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
        patch("app.services.workflow.orchestrator.Team") as team_model,
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService"
        ) as notifications,
        patch(
            "app.services.workflow.orchestrator.get_default_language",
            new=AsyncMock(return_value="en"),
        ),
    ):
        node_model.filter.return_value.all = AsyncMock(return_value=executions)
        workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
        workflow_model.filter.return_value.update = AsyncMock()
        team_model.filter.return_value.update = AsyncMock()
        notifications.send_to_user = AsyncMock()
        notifications.send_to_team = AsyncMock()

        if method_name == "_complete_run":
            await orchestrator._complete_run(run, {"answer": "done"}, 42)
            assert run.outputs == {"answer": "done"}
        else:
            await orchestrator._fail_run(run, "provider failed", 42)
            assert run.error_message == "provider failed"

    assert run.status == run_status
    assert (
        run.total_nodes,
        run.executed_nodes,
        run.failed_nodes,
        run.skipped_nodes,
    ) == (
        3,
        1,
        1,
        1,
    )
    run.save.assert_awaited_once()
    workflow_model.filter.return_value.update.assert_awaited_once()
    team_model.filter.return_value.update.assert_awaited_once()
    getattr(notifications, notification_method).assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_iteration_body_enforces_timeout_and_cancellation():
    orchestrator = WorkflowOrchestrator(
        timeout=1, enable_cache=False, enable_metrics=False
    )
    context = MagicMock(
        get_status=AsyncMock(return_value="cancelled"),
        get_node_outputs=AsyncMock(return_value={}),
    )

    with pytest.raises(ExecutionTimeoutError):
        await orchestrator._execute_iteration_body(
            "loop", ["child"], MagicMock(), context, MagicMock(), None, 0, set(), set()
        )

    with pytest.raises(ExecutionCancelledError):
        await orchestrator._execute_iteration_body(
            "loop",
            ["child"],
            MagicMock(),
            context,
            MagicMock(),
            None,
            __import__("time").time(),
            set(),
            set(),
        )
