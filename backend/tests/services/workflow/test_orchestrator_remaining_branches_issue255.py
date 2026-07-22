from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.models.workflow import RunStatus
from app.services.workflow.orchestrator import WorkflowOrchestrator


def _run_boundaries(*, execute: AsyncMock):
    workflow_id = uuid4()
    user_id = uuid4()
    run = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(id=workflow_id, name="Release", definition={"nodes": []})
    plan = MagicMock(validate=MagicMock(return_value=[]))
    context = MagicMock(set_inputs=AsyncMock(), set_variable=AsyncMock())
    stream = MagicMock(
        publish_workflow_start=AsyncMock(),
        publish_workflow_complete=AsyncMock(),
        publish_workflow_error=AsyncMock(),
    )
    metrics = MagicMock(
        record_workflow_start=AsyncMock(), record_workflow_complete=AsyncMock()
    )
    profiler = MagicMock(to_dict=MagicMock(return_value={"duration_ms": 1}))
    orchestrator = WorkflowOrchestrator(
        enable_cache=False, enable_metrics=False, enable_profiling=True
    )
    orchestrator._metrics = metrics
    orchestrator._load_workflow = AsyncMock(return_value=workflow)
    orchestrator._get_workflow_definition = AsyncMock(return_value=workflow.definition)
    orchestrator._create_run = AsyncMock(return_value=run)
    orchestrator._get_execution_plan = AsyncMock(return_value=plan)
    orchestrator._execute = execute
    orchestrator._complete_run = AsyncMock()
    orchestrator._fail_run = AsyncMock()
    return orchestrator, workflow_id, user_id, run, context, stream, metrics, profiler


@pytest.mark.asyncio
async def test_run_reports_streams_and_profiles_success() -> None:
    execute = AsyncMock(return_value=({"answer": "done"}, 3))
    (
        orchestrator,
        workflow_id,
        user_id,
        run,
        context,
        stream,
        metrics,
        profiler,
    ) = _run_boundaries(execute=execute)

    with (
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.create",
            new=AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
        patch(
            "app.services.workflow.orchestrator.ExecutionProfiler",
            return_value=profiler,
        ),
    ):
        result = await orchestrator.run(workflow_id, {"question": "ready?"}, user_id)

    assert result == str(run.id)
    context.set_inputs.assert_awaited_once_with({"question": "ready?"})
    stream.publish_workflow_start.assert_awaited_once()
    stream.publish_workflow_complete.assert_awaited_once_with(
        outputs={"answer": "done"}, duration_ms=pytest.approx(0, abs=1000)
    )
    orchestrator._complete_run.assert_awaited_once()
    assert metrics.record_workflow_complete.await_args.kwargs == {
        "run_id": str(run.id),
        "workflow_id": str(workflow_id),
        "duration_ms": pytest.approx(0, abs=1000),
        "status": "success",
        "node_count": 3,
    }
    profiler.start.assert_called_once_with()
    profiler.finish.assert_called_once_with()
    context.set_variable.assert_awaited_once_with("_profile", {"duration_ms": 1})


@pytest.mark.asyncio
async def test_run_reports_streams_and_profiles_node_failure() -> None:
    error = RuntimeError("provider failed")
    error.node_id = "llm"
    (
        orchestrator,
        workflow_id,
        user_id,
        run,
        context,
        stream,
        metrics,
        profiler,
    ) = _run_boundaries(execute=AsyncMock(side_effect=error))

    with (
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.create",
            new=AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
        patch(
            "app.services.workflow.orchestrator.ExecutionProfiler",
            return_value=profiler,
        ),
        patch(
            "app.services.workflow.orchestrator.translate_public_workflow_error",
            return_value="public failure",
        ),
        pytest.raises(RuntimeError, match="provider failed"),
    ):
        await orchestrator.run(workflow_id, {}, user_id)

    orchestrator._fail_run.assert_awaited_once()
    assert metrics.record_workflow_complete.await_args.kwargs["status"] == "failed"
    assert (
        metrics.record_workflow_complete.await_args.kwargs["error"] == "public failure"
    )
    profiler.finish.assert_called_once_with()
    stream.publish_workflow_error.assert_awaited_once_with(
        error="public failure", node_id="llm"
    )


@pytest.mark.asyncio
async def test_existing_run_succeeds_without_optional_boundaries() -> None:
    workflow_id = uuid4()
    user_id = uuid4()
    run = MagicMock(id=uuid4(), save=AsyncMock())
    workflow = SimpleNamespace(name="Release", definition={"nodes": []})
    plan = MagicMock(validate=MagicMock(return_value=[]))
    context = MagicMock(set_inputs=AsyncMock())
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._load_workflow = AsyncMock(return_value=workflow)
    orchestrator._get_workflow_definition = AsyncMock(return_value=workflow.definition)
    orchestrator._get_execution_plan = AsyncMock(return_value=plan)
    orchestrator._execute = AsyncMock(return_value=({"answer": "done"}, 1))
    orchestrator._complete_run = AsyncMock()

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.create",
            new=AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.orchestrator.StreamManager") as stream_class,
        patch("app.services.workflow.orchestrator.ExecutionProfiler") as profiler_class,
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)
        result = await orchestrator.run_with_run_id(
            run.id, workflow_id, {"question": "ready?"}, user_id, stream=False
        )

    assert result == str(run.id)
    assert run.status == RunStatus.RUNNING
    run.save.assert_awaited_once()
    orchestrator._complete_run.assert_awaited_once_with(
        run, {"answer": "done"}, pytest.approx(0, abs=1000)
    )
    stream_class.assert_not_called()
    profiler_class.assert_not_called()


@pytest.mark.asyncio
async def test_complete_debug_run_infers_schema_without_existing_workflow() -> None:
    workflow_id = uuid4()
    run = MagicMock(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=True,
        total_token_usage=None,
        save=AsyncMock(),
    )
    executions = [SimpleNamespace(status=RunStatus.SUCCESS)]

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
        patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
        patch(
            "app.services.workflow.schema_inference.merge_run_into_workflow",
            new=AsyncMock(),
        ) as merge,
    ):
        node_model.filter.return_value.all = AsyncMock(return_value=executions)
        workflow_model.filter.return_value.first = AsyncMock(return_value=None)
        await WorkflowOrchestrator(
            enable_cache=False, enable_metrics=False
        )._complete_run(run, {}, 1)

    merge.assert_awaited_once_with(workflow_id, executions)
    workflow_model.filter.return_value.update.assert_not_called()


@pytest.mark.asyncio
async def test_complete_run_skips_token_and_team_updates_when_usage_is_empty() -> None:
    workflow_id = uuid4()
    run = MagicMock(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=False,
        triggered_by_id=uuid4(),
        triggered_by=None,
        total_token_usage=None,
        save=AsyncMock(),
        fetch_related=AsyncMock(),
    )
    workflow = SimpleNamespace(id=workflow_id, team_id=uuid4(), name="Release")

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
        patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
        patch("app.services.workflow.orchestrator.Team") as team_model,
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService"
        ) as notifications,
    ):
        node_model.filter.return_value.all = AsyncMock(return_value=[])
        workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
        workflow_model.filter.return_value.update = AsyncMock()
        team_model.filter.return_value.update = AsyncMock()
        notifications.send_to_user = AsyncMock()
        await WorkflowOrchestrator(
            enable_cache=False, enable_metrics=False
        )._complete_run(run, {}, 1)

    team_model.filter.assert_not_called()
    notifications.send_to_user.assert_awaited_once()
    assert workflow_model.filter.call_args_list == [
        call(id=workflow_id),
        call(id=workflow_id),
    ]
