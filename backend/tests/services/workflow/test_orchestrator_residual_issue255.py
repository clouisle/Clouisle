from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus
from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
    WorkflowNotFoundError,
)
from app.services.workflow.orchestrator import WorkflowOrchestrator, get_node_type_label


@pytest.mark.anyio
async def test_node_type_label_handles_unknown_and_translates_known():
    assert await get_node_type_label("unknown") is None
    with patch(
        "app.services.workflow.orchestrator.get_default_language",
        new=AsyncMock(return_value="en"),
    ):
        assert await get_node_type_label("answer")


@pytest.mark.anyio
async def test_definition_cache_miss_without_updated_at_and_run_creation():
    cache = MagicMock(
        get_workflow=AsyncMock(return_value=None), set_workflow=AsyncMock()
    )
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    service._cache = cache
    workflow = SimpleNamespace(
        id=uuid4(), definition={"nodes": []}, updated_at=None, trigger_type="manual"
    )

    assert await service._get_workflow_definition(workflow) == workflow.definition
    cache.set_workflow.assert_awaited_once_with(
        str(workflow.id), workflow.definition, version=None
    )

    with patch(
        "app.services.workflow.orchestrator.WorkflowRun.create", new=AsyncMock()
    ) as create:
        create.return_value = SimpleNamespace(id=uuid4())
        await service._create_run(workflow, {"x": 1}, uuid4(), uuid4())
    assert create.await_args.kwargs["workflow_id"] == workflow.id


@pytest.mark.anyio
async def test_run_with_run_id_rejects_missing_record():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow = SimpleNamespace(id=uuid4(), name="Workflow", definition={"nodes": []})
    service._load_workflow = AsyncMock(return_value=workflow)

    query = MagicMock()
    query.first = AsyncMock(return_value=None)
    with patch(
        "app.services.workflow.orchestrator.WorkflowRun.filter", return_value=query
    ):
        with pytest.raises(WorkflowNotFoundError):
            await service.run_with_run_id(uuid4(), workflow.id, {}, uuid4())


@pytest.mark.anyio
async def test_completion_debug_inference_and_notification_failure_are_isolated():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=True,
        total_token_usage=None,
        triggered_by_id=uuid4(),
        triggered_by=None,
        fetch_related=AsyncMock(),
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(id=workflow_id, team_id=None, name="Workflow")
    executions = [SimpleNamespace(status=NodeStatus.SUCCESS)]
    node_query = MagicMock(all=AsyncMock(return_value=executions))
    workflow_query = MagicMock(
        first=AsyncMock(return_value=workflow), update=AsyncMock()
    )

    with (
        patch(
            "app.services.workflow.orchestrator.NodeExecution.filter",
            return_value=node_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Workflow.filter",
            return_value=workflow_query,
        ),
        patch(
            "app.services.workflow.schema_inference.merge_run_into_workflow",
            new=AsyncMock(),
        ) as merge,
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService.send_to_user",
            new=AsyncMock(side_effect=RuntimeError("notification down")),
        ),
    ):
        await service._complete_run(run, {"answer": "ok"}, 12)

    merge.assert_awaited_once_with(workflow_id, executions)
    assert run.status == NodeStatus.SUCCESS.value


@pytest.mark.anyio
async def test_fail_run_handles_empty_error_and_team_notification_failure():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        total_token_usage={"prompt": None, "completion": 0},
        triggered_by_id=None,
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(id=workflow_id, team_id=uuid4(), name="Workflow")
    node_query = MagicMock(all=AsyncMock(return_value=[]))
    workflow_query = MagicMock(
        first=AsyncMock(return_value=workflow), update=AsyncMock()
    )

    with (
        patch(
            "app.services.workflow.orchestrator.NodeExecution.filter",
            return_value=node_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Workflow.filter",
            return_value=workflow_query,
        ),
        patch(
            "app.services.workflow.orchestrator.get_default_language",
            new=AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService.send_to_team",
            new=AsyncMock(side_effect=RuntimeError("notification down")),
        ),
    ):
        await service._fail_run(run, "", 5)

    assert run.error_message == ""


@pytest.mark.anyio
async def test_execute_covers_timeout_cancel_limit_and_missing_downstream_node():
    service = WorkflowOrchestrator(
        timeout=1, max_nodes=0, enable_cache=False, enable_metrics=False
    )
    context = MagicMock(
        get_status=AsyncMock(return_value="running"),
        get_node_outputs=AsyncMock(return_value={}),
    )
    plan = SimpleNamespace(stages=[SimpleNamespace(node_ids=[])])

    with pytest.raises(ExecutionTimeoutError):
        await service._execute(plan, context, MagicMock(), None, 0)

    context.get_status.return_value = "cancelled"
    with patch("app.services.workflow.orchestrator.time.time", return_value=0):
        with pytest.raises(ExecutionCancelledError):
            await service._execute(plan, context, MagicMock(), None, 0)

    node = SimpleNamespace(node_type="answer", upstream=set(), handle_map={})
    plan = MagicMock(stages=[SimpleNamespace(node_ids=["node"])])
    plan.get_node.return_value = node
    context.get_status.return_value = "running"
    with patch("app.services.workflow.orchestrator.time.time", return_value=0):
        with pytest.raises(NodeExecutionError, match="maximum node count"):
            await service._execute(plan, context, MagicMock(), None, 0)

    service.max_nodes = 10
    branch = SimpleNamespace(
        node_type="condition",
        upstream=set(),
        handle_map={"yes": [], "no": ["missing"]},
    )
    plan.get_node.side_effect = lambda node_id: (
        branch if node_id == "condition" else None
    )
    plan.stages = [SimpleNamespace(node_ids=["condition"])]
    plan.get_all_downstream.return_value = []
    service._execute_node = AsyncMock(
        return_value=SimpleNamespace(outputs={}, next_handles=["yes"])
    )
    stream = MagicMock(publish_node_skip=AsyncMock())
    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=0),
        patch("app.services.workflow.orchestrator.NodeExecution") as node_cls,
    ):
        node_cls.filter.return_value.first = AsyncMock(return_value=None)
        node_cls.filter.return_value.all = AsyncMock(return_value=[])
        node_cls.create = AsyncMock()
        assert await service._execute(plan, context, MagicMock(), stream, 0) == ({}, 1)
    stream.publish_node_skip.assert_awaited_once_with(
        node_id="missing",
        reason="branch_not_taken",
        node_type=None,
        node_label="missing",
    )


@pytest.mark.anyio
async def test_iteration_body_checks_timeout_and_cancellation():
    service = WorkflowOrchestrator(timeout=1, enable_cache=False, enable_metrics=False)
    context = MagicMock(
        get_status=AsyncMock(return_value="running"),
        get_node_outputs=AsyncMock(return_value={}),
    )

    with pytest.raises(ExecutionTimeoutError):
        await service._execute_iteration_body(
            "loop", ["child"], MagicMock(), context, MagicMock(), None, 0, set(), set()
        )

    context.get_status.return_value = "cancelled"
    with patch("app.services.workflow.orchestrator.time.time", return_value=0):
        with pytest.raises(ExecutionCancelledError):
            await service._execute_iteration_body(
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


@pytest.mark.anyio
async def test_fail_run_without_workflow_still_persists_failure():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=uuid4(),
        total_token_usage={},
        save=AsyncMock(),
    )
    node_query = MagicMock(all=AsyncMock(return_value=[]))
    workflow_query = MagicMock(first=AsyncMock(return_value=None))

    with (
        patch(
            "app.services.workflow.orchestrator.NodeExecution.filter",
            return_value=node_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Workflow.filter",
            return_value=workflow_query,
        ),
    ):
        await service._fail_run(run, "failed", 5)

    assert run.status.value == "failed"
    assert run.error_message == "failed"


@pytest.mark.anyio
async def test_persist_skipped_node_does_not_duplicate_existing_execution():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    existing = SimpleNamespace(id=uuid4())
    query = MagicMock(first=AsyncMock(return_value=existing))

    with patch(
        "app.services.workflow.orchestrator.NodeExecution.filter",
        return_value=query,
    ):
        await service._persist_skipped_node(
            SimpleNamespace(id=uuid4()), "branch", "condition", "Branch"
        )

    query.first.assert_awaited_once()


@pytest.mark.anyio
async def test_iteration_body_rejects_waiting_child_node():
    service = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    context = MagicMock(
        get_node_outputs=AsyncMock(return_value={}),
        get_status=AsyncMock(return_value="running"),
    )
    service._execute_node = AsyncMock(
        return_value=SimpleNamespace(waiting=True, outputs={})
    )

    with pytest.raises(NodeExecutionError, match="Pause nodes"):
        await service._execute_iteration_body(
            "iteration",
            ["child"],
            MagicMock(),
            context,
            MagicMock(),
            None,
            __import__("time").time(),
            set(),
            set(),
        )

    context.pop_iteration_scope.assert_called_once()
