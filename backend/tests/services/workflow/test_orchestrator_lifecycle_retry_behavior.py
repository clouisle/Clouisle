"""Behavioral coverage for orchestrator node lifecycle and retry routing."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus
from app.services.workflow.errors import NodeExecutionError
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
