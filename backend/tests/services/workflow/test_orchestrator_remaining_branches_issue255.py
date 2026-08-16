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


@pytest.mark.asyncio
async def test_existing_run_parks_on_pause_and_pins_definition() -> None:
    from app.services.workflow.errors import NodeWaitingError

    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        is_debug=True,
        context_snapshot={},
        status=RunStatus.PENDING,
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(
        name="Await review",
        definition={"nodes": [{"id": "pause-1", "type": "pause"}]},
    )
    plan = MagicMock(validate=MagicMock(return_value=[]))
    context = MagicMock(set_inputs=AsyncMock(), set_ttl=AsyncMock())
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._load_workflow = AsyncMock(return_value=workflow)
    orchestrator._get_workflow_definition = AsyncMock(return_value=workflow.definition)
    orchestrator._get_execution_plan = AsyncMock(return_value=plan)
    orchestrator._execute = AsyncMock(side_effect=NodeWaitingError("pause-1"))
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
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)
        result = await orchestrator.run_with_run_id(
            run.id, workflow_id, {}, uuid4(), stream=False
        )

    assert result == str(run.id)
    assert run.status == RunStatus.WAITING
    assert run.context_snapshot == {"workflow_definition": workflow.definition}
    assert run.save.await_count == 2
    context.set_ttl.assert_awaited_once_with()
    orchestrator._complete_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_run_parks_on_pause_and_pins_definition() -> None:
    from app.services.workflow.errors import NodeWaitingError

    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        status=RunStatus.PENDING,
        total_duration_ms=None,
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Await review",
        definition={"nodes": [{"id": "pause-1", "type": "pause"}]},
    )
    plan = MagicMock(validate=MagicMock(return_value=[]))
    context = MagicMock(set_inputs=AsyncMock(), set_ttl=AsyncMock())
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._load_workflow = AsyncMock(return_value=workflow)
    orchestrator._get_workflow_definition = AsyncMock(return_value=workflow.definition)
    orchestrator._create_run = AsyncMock(return_value=run)
    orchestrator._get_execution_plan = AsyncMock(return_value=plan)
    orchestrator._execute = AsyncMock(side_effect=NodeWaitingError("pause-1"))

    with (
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.create",
            new=AsyncMock(return_value=context),
        ),
    ):
        result = await orchestrator.run(workflow_id, {}, uuid4(), stream=False)

    assert result == str(run.id)
    assert run.status == RunStatus.WAITING
    assert run.context_snapshot == {"workflow_definition": workflow.definition}
    context.set_ttl.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_resume_existing_run_uses_pinned_pause_definition() -> None:
    workflow_id = uuid4()
    old_definition = {"nodes": [{"id": "pause-1", "type": "pause"}]}
    run = SimpleNamespace(
        id=uuid4(),
        context_snapshot={
            "workflow_definition": old_definition,
            "public_base_url": "https://public.example",
        },
        status=RunStatus.WAITING,
        total_duration_ms=None,
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(
        name="Changed after pause", definition={"nodes": [{"id": "new"}]}
    )
    plan = MagicMock(validate=MagicMock(return_value=[]))
    context = MagicMock(set_inputs=AsyncMock())
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._load_workflow = AsyncMock(return_value=workflow)
    orchestrator._get_workflow_definition = AsyncMock()
    orchestrator._get_execution_plan = AsyncMock(return_value=plan)
    orchestrator._execute = AsyncMock(return_value=({"answer": "done"}, 2))
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
        ) as create_context,
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)
        result = await orchestrator.run_with_run_id(
            run.id, workflow_id, {"input": "value"}, uuid4(), stream=False, resume=True
        )

    assert result == str(run.id)
    orchestrator._get_workflow_definition.assert_not_awaited()
    orchestrator._get_execution_plan.assert_awaited_once_with(
        workflow_id, old_definition
    )
    assert (
        create_context.await_args.kwargs["public_base_url"] == "https://public.example"
    )


@pytest.mark.asyncio
async def test_execute_converts_waiting_result_to_node_waiting_error() -> None:
    """A pause node's waiting result must park the run, not complete it."""
    from app.services.workflow.errors import NodeWaitingError
    from app.services.workflow.executor import ExecutionResult

    pause_node = SimpleNamespace(
        node_type="pause",
        upstream=set(),
        handle_map={},
        node_data={"data": {"label": "Approval", "config": {"mode": "approval"}}},
    )
    plan = MagicMock(
        stages=[SimpleNamespace(node_ids=["pause-1"])],
        get_node=MagicMock(return_value=pause_node),
        get_all_downstream=MagicMock(return_value=[]),
    )
    context = MagicMock(
        get_status=AsyncMock(return_value="running"),
        get_node_outputs=AsyncMock(return_value={}),
    )
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._execute_node = AsyncMock(return_value=ExecutionResult(waiting=True))

    with pytest.raises(NodeWaitingError) as exc_info:
        await orchestrator._execute(
            plan, context, MagicMock(), None, start_time=__import__("time").time()
        )

    assert exc_info.value.node_id == "pause-1"


@pytest.mark.asyncio
async def test_execute_resume_rebuilds_sets_and_runs_only_paused_node() -> None:
    """Resume must re-run only the paused node, never completed or skipped ones.

    Regression guard: if the resume rebuild block is dropped, a resumed run
    would re-execute every prior SUCCESS node (duplicating side effects).
    """
    from app.models.workflow import NodeStatus

    done = SimpleNamespace(
        node_type="llm",
        upstream=set(),
        handle_map={},
        node_data={"data": {"label": "Done"}},
    )
    paused = SimpleNamespace(
        node_type="pause",
        upstream=set(),
        handle_map={},
        node_data={"data": {"label": "Approval", "config": {"mode": "approval"}}},
    )
    skipped = SimpleNamespace(
        node_type="template",
        upstream=set(),
        handle_map={},
        node_data={"data": {}},
    )
    nodes = {"done": done, "paused": paused, "skipped": skipped}
    plan = MagicMock(
        stages=[SimpleNamespace(node_ids=["done", "paused", "skipped"])],
        get_node=MagicMock(side_effect=nodes.get),
        get_all_downstream=MagicMock(return_value=[]),
    )
    context = MagicMock(
        get_status=AsyncMock(return_value="running"),
        get_node_outputs=AsyncMock(return_value={}),
    )
    run = MagicMock(id=uuid4())
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    executed = AsyncMock(
        return_value=SimpleNamespace(outputs={}, waiting=False, next_handles=None)
    )
    orchestrator._execute_node = executed

    with patch("app.services.workflow.orchestrator.NodeExecution") as node_cls:
        node_cls.filter.return_value.all = AsyncMock(
            return_value=[
                SimpleNamespace(node_id="done", status=NodeStatus.SUCCESS),
                SimpleNamespace(node_id="skipped", status=NodeStatus.SKIPPED),
            ]
        )
        outputs, count = await orchestrator._execute(
            plan, context, run, None, start_time=__import__("time").time(), resume=True
        )

    assert count == 1
    assert [call.kwargs["node_id"] for call in executed.await_args_list] == ["paused"]
