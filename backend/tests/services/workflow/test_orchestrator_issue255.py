from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import RunStatus
from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
    WorkflowNotFoundError,
)
from app.services.workflow.orchestrator import WorkflowOrchestrator


def make_orchestrator(**kwargs):
    return WorkflowOrchestrator(
        enable_retry=False,
        enable_cache=False,
        enable_metrics=False,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_workflow_definition_returns_cached_value():
    orchestrator = make_orchestrator()
    orchestrator._cache = MagicMock(
        get_workflow=AsyncMock(return_value={"nodes": ["cached"]}),
        set_workflow=AsyncMock(),
    )
    workflow = MagicMock(
        id=uuid4(), definition={"nodes": ["database"]}, updated_at=None
    )

    assert await orchestrator._get_workflow_definition(workflow) == {
        "nodes": ["cached"]
    }
    orchestrator._cache.get_workflow.assert_awaited_once_with(
        str(workflow.id), version=None
    )
    orchestrator._cache.set_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_definition_caches_miss_without_version():
    orchestrator = make_orchestrator()
    orchestrator._cache = MagicMock(
        get_workflow=AsyncMock(return_value=None),
        set_workflow=AsyncMock(),
    )
    workflow = MagicMock(
        id=uuid4(), definition={"nodes": ["database"]}, updated_at=None
    )

    assert await orchestrator._get_workflow_definition(workflow) == workflow.definition
    orchestrator._cache.set_workflow.assert_awaited_once_with(
        str(workflow.id), workflow.definition, version=None
    )


def test_get_child_nodes_follows_execution_order():
    orchestrator = make_orchestrator()
    plan = MagicMock()
    plan.nodes = {
        "child-b": MagicMock(node_data={"parentId": "loop"}),
        "other": MagicMock(node_data={"parentId": "different-loop"}),
        "child-a": MagicMock(node_data={"parentId": "loop"}),
    }
    plan.get_execution_order.return_value = ["child-a", "other", "child-b"]

    assert orchestrator._get_child_nodes(plan, "loop") == ["child-a", "child-b"]


@pytest.mark.asyncio
async def test_execute_rejects_timed_out_run_before_reading_context():
    orchestrator = make_orchestrator(timeout=1)
    context = MagicMock(get_status=AsyncMock())
    plan = MagicMock(stages=[SimpleNamespace(node_ids=[])])

    with pytest.raises(ExecutionTimeoutError):
        await orchestrator._execute(plan, context, MagicMock(), None, start_time=0)

    context.get_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_rejects_cancelled_run_before_executing_nodes():
    orchestrator = make_orchestrator()
    orchestrator._execute_node = AsyncMock()
    context = MagicMock(
        get_status=AsyncMock(return_value="cancelled"),
        get_node_outputs=AsyncMock(return_value={}),
    )
    plan = MagicMock(stages=[SimpleNamespace(node_ids=["node"])])

    with pytest.raises(ExecutionCancelledError):
        await orchestrator._execute(plan, context, MagicMock(), None, start_time=10**20)

    orchestrator._execute_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_enforces_maximum_node_count():
    orchestrator = make_orchestrator(max_nodes=0)
    orchestrator._execute_node = AsyncMock()
    context = MagicMock(get_status=AsyncMock(return_value="running"))
    node = SimpleNamespace(node_type="answer", upstream=set())
    plan = MagicMock(
        stages=[SimpleNamespace(node_ids=["answer"])],
        get_node=MagicMock(return_value=node),
    )

    with pytest.raises(NodeExecutionError, match="Exceeded maximum node count"):
        await orchestrator._execute(plan, context, MagicMock(), None, start_time=10**20)

    orchestrator._execute_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_iteration_body_stops_when_run_is_cancelled():
    orchestrator = make_orchestrator()
    orchestrator._execute_node = AsyncMock()
    context = MagicMock(
        get_status=AsyncMock(return_value="cancelled"),
        get_node_outputs=AsyncMock(return_value={}),
    )

    with pytest.raises(ExecutionCancelledError):
        await orchestrator._execute_iteration_body(
            "iteration",
            ["child"],
            MagicMock(),
            context,
            MagicMock(),
            None,
            start_time=10**20,
            executed_nodes=set(),
            skipped_nodes=set(),
        )

    orchestrator._execute_node.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_node_rejects_node_missing_from_plan():
    orchestrator = make_orchestrator()

    with pytest.raises(NodeExecutionError):
        await orchestrator._execute_node(
            "missing",
            MagicMock(get_node=MagicMock(return_value=None)),
            MagicMock(),
            MagicMock(),
            None,
        )


@pytest.mark.asyncio
async def test_run_with_run_id_rejects_missing_run_record():
    orchestrator = make_orchestrator()
    workflow = MagicMock(definition={"nodes": [], "edges": []})

    with (
        patch.object(orchestrator, "_load_workflow", AsyncMock(return_value=workflow)),
        patch.object(
            orchestrator,
            "_get_workflow_definition",
            AsyncMock(return_value=workflow.definition),
        ),
        patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=None)
        with pytest.raises(WorkflowNotFoundError):
            await orchestrator.run_with_run_id(uuid4(), uuid4(), {}, uuid4())


@pytest.mark.asyncio
async def test_cancel_pending_run_survives_missing_context_and_publishes_error():
    orchestrator = make_orchestrator()
    run_id = str(uuid4())
    run = MagicMock(status=RunStatus.PENDING, save=AsyncMock())
    stream = MagicMock(publish_workflow_error=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
        patch("app.services.workflow.orchestrator.get_redis", new=AsyncMock()),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            new=AsyncMock(side_effect=RuntimeError("context unavailable")),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
    ):
        run_model.filter.return_value.first = AsyncMock(return_value=run)
        assert await orchestrator.cancel(run_id) is True

    assert run.status == RunStatus.CANCELLED
    run.save.assert_awaited_once()
    stream.publish_workflow_error.assert_awaited_once()
