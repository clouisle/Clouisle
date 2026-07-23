from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus, RunStatus
from app.services.workflow.context import ExecutionContext
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.lazy_stream import LazyStreamResult
from app.services.workflow.orchestrator import WorkflowOrchestrator


class _Unserializable:
    pass


@pytest.mark.asyncio
async def test_complete_debug_run_infers_schema_and_swallows_notification_error():
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    run = MagicMock(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=True,
        total_token_usage={"prompt": 0, "completion": 0},
        triggered_by_id=uuid4(),
        triggered_by=None,
        fetch_related=AsyncMock(),
        save=AsyncMock(),
    )
    workflow = MagicMock(id=workflow_id, team_id=uuid4(), name="Debug Workflow")

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
        patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
        patch(
            "app.services.workflow.schema_inference.merge_run_into_workflow",
            new=AsyncMock(),
        ) as merge_schema,
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService.send_to_user",
            new=AsyncMock(side_effect=RuntimeError("notify failed")),
        ) as notify,
    ):
        node_executions = [MagicMock(status=NodeStatus.SUCCESS)]
        node_model.filter.return_value.all = AsyncMock(return_value=node_executions)
        workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
        workflow_model.filter.return_value.update = AsyncMock()

        await orchestrator._complete_run(run, {"answer": "ok"}, 7)

    merge_schema.assert_awaited_once_with(workflow_id, node_executions)
    notify.assert_awaited_once()
    run.fetch_related.assert_awaited_once_with("triggered_by")
    assert run.status == RunStatus.SUCCESS


@pytest.mark.asyncio
async def test_cancel_pending_run_still_publishes_when_context_load_fails():
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    run = MagicMock(status=RunStatus.PENDING, save=AsyncMock())
    stream = MagicMock(publish_workflow_error=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            new=AsyncMock(side_effect=RuntimeError("missing context")),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)

        assert await orchestrator.cancel(str(uuid4())) is True

    assert run.status == RunStatus.CANCELLED
    run.save.assert_awaited_once()
    stream.publish_workflow_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_node_stores_placeholders_for_unserializable_outputs():
    orchestrator = WorkflowOrchestrator(
        enable_retry=False, enable_cache=False, enable_metrics=False
    )
    run = MagicMock(id=uuid4())
    context = ExecutionContext(run.id, MagicMock())
    context.set_node_outputs = AsyncMock()
    node_execution = MagicMock(save=AsyncMock())
    node = MagicMock(
        node_type="answer",
        node_data={"data": {"label": "Answer", "config": {}}},
    )
    plan = MagicMock(get_node=MagicMock(return_value=node))
    stream = MagicMock(
        publish_node_start=AsyncMock(),
        publish_node_complete=AsyncMock(),
    )

    lazy_output = LazyStreamResult(
        model_id="model",
        messages=[],
        temperature=0,
        max_tokens=None,
        top_p=1,
    )
    executor = MagicMock(
        execute=AsyncMock(
            return_value=ExecutionResult(
                outputs={
                    "lazy": lazy_output,
                    "context": context,
                    "custom": _Unserializable(),
                    "plain": {"ok": True},
                },
            )
        )
    )

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
    ):
        node_model.filter.return_value.all = AsyncMock(return_value=[])
        node_model.create = AsyncMock(return_value=node_execution)

        result = await orchestrator._execute_node("answer", plan, context, run, stream)

    assert result.outputs["plain"] == {"ok": True}
    assert node_execution.outputs == {
        "lazy": "__LAZY_STREAM__",
        "context": "__EXECUTION_CONTEXT__",
        "custom": "__NON_SERIALIZABLE__Unserializable__",
        "plain": {"ok": True},
    }
    stream.publish_node_complete.assert_awaited_once()
