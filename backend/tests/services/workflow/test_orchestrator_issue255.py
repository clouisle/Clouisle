"""Additional branch coverage for the workflow orchestrator (#255)."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus, RunStatus
from app.services.workflow.errors import NodeExecutionError
from app.services.workflow.orchestrator import WorkflowOrchestrator


@pytest.fixture
def orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        enable_cache=False,
        enable_metrics=False,
        enable_retry=False,
    )


@pytest.mark.asyncio
async def test_execute_skips_untaken_branch_and_its_downstream(orchestrator):
    condition = SimpleNamespace(
        node_type="condition",
        node_data={"data": {"label": "Choose"}},
        upstream=set(),
        handle_map={"yes": ["accepted"], "no": ["rejected"]},
    )
    accepted = SimpleNamespace(
        node_type="template",
        node_data={"data": {"label": "Accepted"}},
        upstream={"condition"},
        handle_map={},
    )
    rejected = SimpleNamespace(
        node_type="template",
        node_data={"data": {"label": "Rejected"}},
        upstream={"condition"},
        handle_map={},
    )
    nodes = {
        "condition": condition,
        "accepted": accepted,
        "rejected": rejected,
    }
    plan = SimpleNamespace(
        stages=[
            SimpleNamespace(node_ids=["condition"]),
            SimpleNamespace(node_ids=["accepted", "rejected"]),
        ],
        get_node=MagicMock(side_effect=nodes.get),
        get_all_downstream=MagicMock(return_value=["after-rejected"]),
    )
    orchestrator._execute_node = AsyncMock(
        side_effect=[
            SimpleNamespace(outputs={}, next_handles=["yes"]),
            SimpleNamespace(outputs={}, next_handles=[]),
        ]
    )
    context = SimpleNamespace(get_status=AsyncMock(return_value="running"))
    stream = SimpleNamespace(publish_node_skip=AsyncMock())

    outputs, node_count = await orchestrator._execute(
        plan=plan,
        context=context,
        run=SimpleNamespace(),
        stream_manager=stream,
        start_time=time.time(),
    )

    assert outputs == {}
    assert node_count == 2
    assert [
        call.kwargs["node_id"] for call in orchestrator._execute_node.await_args_list
    ] == [
        "condition",
        "accepted",
    ]
    stream.publish_node_skip.assert_awaited_once_with(
        node_id="rejected",
        reason="branch_not_taken",
        node_type="template",
        node_label="Rejected",
    )


@pytest.mark.asyncio
async def test_execute_node_persists_and_publishes_unexpected_executor_failure(
    orchestrator,
):
    node = SimpleNamespace(
        node_type="provider",
        node_data={"data": {"label": "Provider", "config": {}}},
    )
    plan = SimpleNamespace(get_node=MagicMock(return_value=node))
    node_execution = SimpleNamespace(save=AsyncMock())
    executor = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("secret")))
    stream = SimpleNamespace(
        publish_node_start=AsyncMock(),
        publish_node_error=AsyncMock(),
    )

    with (
        patch("app.services.workflow.orchestrator.NodeExecution") as executions,
        patch(
            "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
            return_value=executor,
        ),
        patch(
            "app.services.workflow.orchestrator.translate_public_workflow_error",
            return_value="safe error",
        ),
    ):
        executions.filter.return_value.all = AsyncMock(return_value=[])
        executions.create = AsyncMock(return_value=node_execution)

        with pytest.raises(NodeExecutionError) as exc_info:
            await orchestrator._execute_node(
                node_id="provider-1",
                plan=plan,
                context=SimpleNamespace(),
                run=SimpleNamespace(id=uuid4()),
                stream_manager=stream,
            )

    assert exc_info.value.node_id == "provider-1"
    assert node_execution.status == NodeStatus.FAILED
    assert node_execution.error_message == "safe error"
    assert node_execution.error_type == "RuntimeError"
    node_execution.save.assert_awaited_once()
    stream.publish_node_error.assert_awaited_once_with(
        node_id="provider-1", error="safe error"
    )


@pytest.mark.asyncio
async def test_execute_node_rejects_missing_plan_node_before_persistence(orchestrator):
    with pytest.raises(NodeExecutionError) as exc_info:
        await orchestrator._execute_node(
            node_id="missing",
            plan=SimpleNamespace(get_node=MagicMock(return_value=None)),
            context=SimpleNamespace(),
            run=SimpleNamespace(id=uuid4()),
            stream_manager=None,
        )

    assert exc_info.value.node_id == "missing"
    assert exc_info.value.node_type == "unknown"


@pytest.mark.asyncio
async def test_cancel_pending_run_survives_missing_context_and_publishes(orchestrator):
    run = SimpleNamespace(status=RunStatus.PENDING, save=AsyncMock(), finished_at=None)
    stream = SimpleNamespace(publish_workflow_error=AsyncMock())

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as runs,
        patch("app.services.workflow.orchestrator.get_redis", new=AsyncMock()),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            new=AsyncMock(side_effect=RuntimeError("context not created")),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
        patch("app.services.workflow.orchestrator.t", return_value="cancelled"),
    ):
        runs.filter.return_value.first = AsyncMock(return_value=run)

        assert await orchestrator.cancel("pending-run") is True

    assert run.status == RunStatus.CANCELLED
    assert run.finished_at is not None
    run.save.assert_awaited_once()
    stream.publish_workflow_error.assert_awaited_once_with(error="cancelled")
