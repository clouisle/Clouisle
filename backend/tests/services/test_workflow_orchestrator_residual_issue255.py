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
