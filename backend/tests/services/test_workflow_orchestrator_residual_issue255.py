from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus, RunStatus
from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
)
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.orchestrator import WorkflowOrchestrator
from app.services.workflow.plan import ExecutionPlan, ExecutionStage, NodeDependency


@pytest.fixture
def orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        timeout=10,
        max_nodes=2,
        enable_retry=False,
        enable_cache=False,
        enable_metrics=False,
    )


@pytest.mark.asyncio
async def test_execute_rejects_timeout_before_reading_context(orchestrator):
    plan = MagicMock(stages=[ExecutionStage(0, [])])
    context = MagicMock(get_status=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=11),
        pytest.raises(ExecutionTimeoutError),
    ):
        await orchestrator._execute(plan, context, MagicMock(), None, 0)

    context.get_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_rejects_cancelled_context(orchestrator):
    plan = MagicMock(stages=[ExecutionStage(0, [])])
    context = MagicMock(get_status=AsyncMock(return_value="cancelled"))

    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=1),
        pytest.raises(ExecutionCancelledError),
    ):
        await orchestrator._execute(plan, context, MagicMock(), None, 0)


@pytest.mark.asyncio
async def test_execute_marks_untaken_branch_and_descendants_skipped(orchestrator):
    condition = NodeDependency(
        "condition",
        "condition",
        {"data": {"label": "Choose"}},
        handle_map={"yes": ["answer"], "no": ["unused"]},
    )
    unused = NodeDependency("unused", "template", {"data": {}})
    answer = NodeDependency("answer", "answer", {"data": {"label": "Answer"}})
    plan = ExecutionPlan(
        {},
        nodes={"condition": condition, "unused": unused, "answer": answer},
        stages=[
            ExecutionStage(0, ["condition"]),
            ExecutionStage(1, ["unused", "answer"]),
        ],
    )
    plan.get_all_downstream = MagicMock(return_value={"unused-child"})
    context = MagicMock(get_status=AsyncMock(return_value="running"))
    stream = MagicMock(
        publish_node_skip=AsyncMock(),
    )
    orchestrator._execute_node = AsyncMock(
        side_effect=[
            ExecutionResult(next_handles=["yes"]),
            ExecutionResult(outputs={"text": "done"}),
        ]
    )

    with patch("app.services.workflow.orchestrator.time.time", return_value=1):
        outputs, count = await orchestrator._execute(
            plan, context, MagicMock(), stream, 0
        )

    assert outputs == {"text": "done"}
    assert count == 2
    assert [
        call.kwargs["node_id"] for call in orchestrator._execute_node.await_args_list
    ] == [
        "condition",
        "answer",
    ]
    stream.publish_node_skip.assert_awaited_once_with(
        node_id="unused",
        reason="branch_not_taken",
        node_type="template",
        node_label="unused",
    )


@pytest.mark.asyncio
async def test_iteration_body_stops_on_cancellation(orchestrator):
    context = MagicMock(get_status=AsyncMock(return_value="cancelled"))
    orchestrator._execute_node = AsyncMock()

    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=1),
        pytest.raises(ExecutionCancelledError),
    ):
        await orchestrator._execute_iteration_body(
            "loop",
            ["child"],
            MagicMock(),
            context,
            MagicMock(),
            None,
            0,
            set(),
            set(),
        )

    orchestrator._execute_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_node_persists_and_streams_unexpected_error(orchestrator):
    node = NodeDependency("broken", "code", {"data": {"label": "Broken"}})
    plan = MagicMock(get_node=MagicMock(return_value=node))
    execution = MagicMock(save=AsyncMock())
    executor = MagicMock(execute=AsyncMock(side_effect=RuntimeError("secret")))
    context = MagicMock()
    stream = MagicMock(publish_node_start=AsyncMock(), publish_node_error=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as execution_model,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
        patch(
            "app.services.workflow.orchestrator.translate_public_workflow_error",
            return_value="public error",
        ),
    ):
        execution_model.filter.return_value.all = AsyncMock(return_value=[])
        execution_model.create = AsyncMock(return_value=execution)
        with pytest.raises(NodeExecutionError, match="public error"):
            await orchestrator._execute_node(
                "broken", plan, context, SimpleNamespace(id=uuid4()), stream
            )

    assert execution.status == NodeStatus.FAILED
    assert execution.error_message == "public error"
    assert execution.error_type == "RuntimeError"
    execution.save.assert_awaited_once()
    stream.publish_node_error.assert_awaited_once_with(
        node_id="broken", error="public error"
    )


@pytest.mark.asyncio
async def test_cancel_pending_run_survives_missing_context(orchestrator):
    run = MagicMock(status=RunStatus.PENDING, save=AsyncMock())
    stream = MagicMock(publish_workflow_error=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            new=AsyncMock(side_effect=RuntimeError("not created")),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)
        assert await orchestrator.cancel(str(uuid4())) is True

    assert run.status == RunStatus.CANCELLED
    run.save.assert_awaited_once()
    stream.publish_workflow_error.assert_awaited_once()


def test_get_child_nodes_preserves_plan_order(orchestrator):
    plan = MagicMock(
        nodes={
            "later": SimpleNamespace(node_data={"parentId": "loop"}),
            "outside": SimpleNamespace(node_data={"parentId": "other"}),
            "first": SimpleNamespace(node_data={"parentId": "loop"}),
        },
        get_execution_order=MagicMock(return_value=["first", "outside", "later"]),
    )

    assert orchestrator._get_child_nodes(plan, "loop") == ["first", "later"]


@pytest.mark.asyncio
async def test_run_success_path_streams_metrics_and_profiling(monkeypatch):
    orchestrator = WorkflowOrchestrator(
        timeout=10,
        max_nodes=2,
        enable_retry=False,
        enable_cache=False,
        enable_metrics=True,
        enable_profiling=True,
    )
    workflow = SimpleNamespace(id=uuid4(), name="Flow")
    run = SimpleNamespace(id=uuid4())
    plan = MagicMock()
    plan.validate.return_value = []
    context = MagicMock()
    context.set_inputs = AsyncMock()
    context.set_variable = AsyncMock()
    metrics = MagicMock(
        record_workflow_start=AsyncMock(), record_workflow_complete=AsyncMock()
    )
    stream = MagicMock(
        publish_workflow_start=AsyncMock(),
        publish_workflow_complete=AsyncMock(),
    )
    profiler = MagicMock()
    profiler.to_dict.return_value = {"steps": []}
    monkeypatch.setattr(
        orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        orchestrator, "_get_workflow_definition", AsyncMock(return_value={})
    )
    monkeypatch.setattr(orchestrator, "_create_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        orchestrator, "_get_execution_plan", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(orchestrator, "_execute", AsyncMock(return_value=({}, 1)))
    monkeypatch.setattr(orchestrator, "_complete_run", AsyncMock())
    monkeypatch.setattr(orchestrator, "_metrics", metrics)
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.get_redis",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionContext",
        MagicMock(create=AsyncMock(return_value=context)),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.StreamManager",
        lambda run_id: stream,
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionProfiler",
        lambda **kwargs: profiler,
    )

    result = await orchestrator.run(
        workflow_id=workflow.id,
        inputs={},
        user_id=uuid4(),
        stream=True,
    )

    assert result == str(run.id)
    metrics.record_workflow_start.assert_awaited_once()
    metrics.record_workflow_complete.assert_awaited_once()
    stream.publish_workflow_start.assert_awaited_once()
    stream.publish_workflow_complete.assert_awaited_once()
    profiler.finish.assert_called_once()
    context.set_variable.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_without_stream_skips_stream_manager(monkeypatch):
    orchestrator = WorkflowOrchestrator(
        timeout=10,
        max_nodes=2,
        enable_retry=False,
        enable_cache=False,
        enable_metrics=False,
        enable_profiling=False,
    )
    workflow = SimpleNamespace(id=uuid4(), name="Flow")
    run = SimpleNamespace(id=uuid4())
    plan = MagicMock()
    plan.validate.return_value = []
    context = MagicMock()
    context.set_inputs = AsyncMock()
    monkeypatch.setattr(
        orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        orchestrator, "_get_workflow_definition", AsyncMock(return_value={})
    )
    monkeypatch.setattr(orchestrator, "_create_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        orchestrator, "_get_execution_plan", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(orchestrator, "_execute", AsyncMock(return_value=({}, 1)))
    monkeypatch.setattr(orchestrator, "_complete_run", AsyncMock())
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.get_redis",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionContext",
        MagicMock(create=AsyncMock(return_value=context)),
    )

    result = await orchestrator.run(
        workflow_id=workflow.id,
        inputs={},
        user_id=uuid4(),
        stream=False,
    )

    assert result == str(run.id)


@pytest.mark.asyncio
async def test_run_failure_path_streams_error_and_finishes_profiling(monkeypatch):
    orchestrator = WorkflowOrchestrator(
        timeout=10,
        max_nodes=2,
        enable_retry=False,
        enable_cache=False,
        enable_metrics=True,
        enable_profiling=True,
    )
    workflow = SimpleNamespace(id=uuid4(), name="Flow")
    run = SimpleNamespace(id=uuid4())
    plan = MagicMock()
    plan.validate.return_value = []
    context = MagicMock()
    context.set_inputs = AsyncMock()
    metrics = MagicMock(
        record_workflow_start=AsyncMock(), record_workflow_complete=AsyncMock()
    )
    stream = MagicMock(
        publish_workflow_start=AsyncMock(), publish_workflow_error=AsyncMock()
    )
    profiler = MagicMock()
    error = RuntimeError("boom")

    monkeypatch.setattr(
        orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        orchestrator, "_get_workflow_definition", AsyncMock(return_value={})
    )
    monkeypatch.setattr(orchestrator, "_create_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        orchestrator, "_get_execution_plan", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(orchestrator, "_execute", AsyncMock(side_effect=error))
    monkeypatch.setattr(orchestrator, "_fail_run", AsyncMock())
    monkeypatch.setattr(orchestrator, "_metrics", metrics)
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.get_redis",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionContext",
        MagicMock(create=AsyncMock(return_value=context)),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.StreamManager",
        lambda run_id: stream,
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionProfiler",
        lambda **kwargs: profiler,
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.translate_public_workflow_error",
        lambda e: {"message": str(e)},
    )

    with pytest.raises(RuntimeError):
        await orchestrator.run(
            workflow_id=workflow.id,
            inputs={},
            user_id=uuid4(),
            stream=True,
        )

    metrics.record_workflow_complete.assert_awaited_once()
    profiler.finish.assert_called_once()
    stream.publish_workflow_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_failure_without_stream_skips_stream_manager(monkeypatch):
    orchestrator = WorkflowOrchestrator(
        timeout=10,
        max_nodes=2,
        enable_retry=False,
        enable_cache=False,
        enable_metrics=False,
        enable_profiling=False,
    )
    workflow = SimpleNamespace(id=uuid4(), name="Flow")
    run = SimpleNamespace(id=uuid4())
    plan = MagicMock()
    plan.validate.return_value = []
    context = MagicMock()
    context.set_inputs = AsyncMock()

    monkeypatch.setattr(
        orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        orchestrator, "_get_workflow_definition", AsyncMock(return_value={})
    )
    monkeypatch.setattr(orchestrator, "_create_run", AsyncMock(return_value=run))
    monkeypatch.setattr(
        orchestrator, "_get_execution_plan", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(
        orchestrator, "_execute", AsyncMock(side_effect=RuntimeError("boom"))
    )
    monkeypatch.setattr(orchestrator, "_fail_run", AsyncMock())
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.get_redis",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.ExecutionContext",
        MagicMock(create=AsyncMock(return_value=context)),
    )
    monkeypatch.setattr(
        "app.services.workflow.orchestrator.translate_public_workflow_error",
        lambda e: {"message": str(e)},
    )

    with pytest.raises(RuntimeError):
        await orchestrator.run(
            workflow_id=workflow.id,
            inputs={},
            user_id=uuid4(),
            stream=False,
        )
