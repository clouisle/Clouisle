import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
)
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.orchestrator import WorkflowOrchestrator


def _plan(*stages: list[str]) -> MagicMock:
    plan = MagicMock()
    plan.stages = [SimpleNamespace(node_ids=node_ids) for node_ids in stages]
    plan.get_node.side_effect = lambda node_id: SimpleNamespace(
        node_type="answer" if node_id == "taken" else "code",
        node_data={"data": {"label": node_id.title()}},
        upstream=set(),
        handle_map={"taken": ["taken"], "skipped": ["skipped"]}
        if node_id == "condition"
        else {},
    )
    plan.get_all_downstream.return_value = []
    return plan


@pytest.mark.asyncio
async def test_execute_rejects_timeout_before_stage() -> None:
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    context = MagicMock()

    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=301),
        pytest.raises(ExecutionTimeoutError),
    ):
        await orchestrator._execute(
            _plan(["node"]), context, MagicMock(), None, start_time=0
        )

    context.get_status.assert_not_called()


@pytest.mark.asyncio
async def test_execute_rejects_cancelled_context() -> None:
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    context = MagicMock(get_status=AsyncMock(return_value="cancelled"))

    with pytest.raises(ExecutionCancelledError):
        await orchestrator._execute(
            _plan(["node"]), context, MagicMock(), None, start_time=time.time()
        )


@pytest.mark.asyncio
async def test_execute_enforces_maximum_node_count() -> None:
    orchestrator = WorkflowOrchestrator(
        max_nodes=1, enable_cache=False, enable_metrics=False
    )
    orchestrator._execute_node = AsyncMock(return_value=ExecutionResult(outputs={}))
    context = MagicMock(get_status=AsyncMock(return_value="running"))

    with pytest.raises(NodeExecutionError, match="Exceeded maximum node count: 1"):
        await orchestrator._execute(
            _plan(["first", "second"]),
            context,
            MagicMock(),
            None,
            start_time=time.time(),
        )

    assert orchestrator._execute_node.await_count == 1


@pytest.mark.asyncio
async def test_execute_prunes_untaken_branch_and_collects_answer() -> None:
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    orchestrator._execute_node = AsyncMock(
        side_effect=[
            ExecutionResult(outputs={}, next_handles=["taken"]),
            ExecutionResult(outputs={"answer": "yes"}),
        ]
    )
    context = MagicMock(get_status=AsyncMock(return_value="running"))
    stream = MagicMock(publish_node_skip=AsyncMock())
    plan = _plan(["condition"], ["skipped", "taken"])

    outputs, node_count = await orchestrator._execute(
        plan, context, MagicMock(), stream, start_time=time.time()
    )

    assert outputs == {"answer": "yes"}
    assert node_count == 2
    assert [
        item.kwargs["node_id"] for item in orchestrator._execute_node.await_args_list
    ] == [
        "condition",
        "taken",
    ]
    assert stream.publish_node_skip.await_args == call(
        node_id="skipped",
        reason="branch_not_taken",
        node_type="code",
        node_label="Skipped",
    )
