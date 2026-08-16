from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.workflow.errors import NodeExecutionError
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.orchestrator import WorkflowOrchestrator


@pytest.mark.asyncio
async def test_execute_covers_branch_iteration_and_limit_behaviors():
    context = MagicMock(
        get_status=AsyncMock(return_value="running"),
        get_node_outputs=AsyncMock(return_value={}),
    )
    run = MagicMock()
    stream = MagicMock(publish_node_skip=AsyncMock())

    branch = SimpleNamespace(
        node_type="condition",
        upstream=set(),
        handle_map={"taken": ["answer"], "missed": ["missing"]},
    )
    answer = SimpleNamespace(
        node_type="answer",
        upstream={"missing"},
        node_data={"data": {}},
    )
    plan = MagicMock(
        stages=[
            SimpleNamespace(node_ids=["branch"]),
            SimpleNamespace(node_ids=["answer"]),
        ]
    )
    plan.get_node.side_effect = lambda node_id: {
        "branch": branch,
        "answer": answer,
    }.get(node_id)
    # Keep answer out of the recursive set so the next stage proves upstream propagation.
    plan.get_all_downstream.return_value = set()
    orchestrator = WorkflowOrchestrator(enable_metrics=False)
    orchestrator._execute_node = AsyncMock(
        return_value=ExecutionResult(next_handles=["taken"])
    )

    with (
        patch(
            "app.services.workflow.orchestrator.get_node_type_label",
            new=AsyncMock(return_value="Answer"),
        ),
        patch("app.services.workflow.orchestrator.NodeExecution") as node_cls,
    ):
        node_cls.filter.return_value.first = AsyncMock(return_value=None)
        node_cls.filter.return_value.all = AsyncMock(return_value=[])
        node_cls.create = AsyncMock()
        outputs, count = await orchestrator._execute(plan, context, run, stream, time())

    assert (outputs, count) == ({}, 1)
    assert orchestrator._execute_node.await_args_list == [
        call(
            node_id="branch",
            plan=plan,
            context=context,
            run=run,
            stream_manager=stream,
        )
    ]
    assert stream.publish_node_skip.await_args_list == [
        call(
            node_id="missing",
            reason="branch_not_taken",
            node_type=None,
            node_label="missing",
        ),
        call(
            node_id="answer",
            reason="upstream_skipped",
            node_type="answer",
            node_label="Answer",
        ),
    ]

    iteration = SimpleNamespace(node_type="iteration", upstream=set(), handle_map={})
    child = SimpleNamespace(node_type="code", upstream={"iteration"})
    iteration_plan = MagicMock(
        stages=[
            SimpleNamespace(node_ids=["iteration"]),
            SimpleNamespace(node_ids=["child"]),
        ]
    )
    iteration_plan.get_node.side_effect = lambda node_id: {
        "iteration": iteration,
        "child": child,
    }.get(node_id)
    orchestrator._get_child_nodes = MagicMock(return_value=["child"])
    orchestrator._execute_iteration_body = AsyncMock()
    orchestrator._execute_node = AsyncMock(
        side_effect=[
            ExecutionResult(outputs={"_iteration_complete": False}),
            ExecutionResult(outputs={"_loop_complete": True}),
        ]
    )

    outputs, count = await orchestrator._execute(
        iteration_plan, context, run, None, time()
    )

    assert (outputs, count) == ({}, 1)
    orchestrator._execute_iteration_body.assert_awaited_once()
    assert [
        item.kwargs["node_id"] for item in orchestrator._execute_node.await_args_list
    ] == [
        "iteration",
        "iteration",
    ]

    body_executor = AsyncMock(return_value=ExecutionResult(outputs={"value": 1}))
    orchestrator._execute_node = body_executor
    await WorkflowOrchestrator._execute_iteration_body(
        orchestrator,
        "iteration",
        ["child"],
        iteration_plan,
        context,
        run,
        None,
        time(),
        set(),
        set(),
    )
    body_executor.assert_awaited_once_with(
        node_id="child",
        plan=iteration_plan,
        context=context,
        run=run,
        stream_manager=None,
    )

    limited = WorkflowOrchestrator(max_nodes=0, enable_metrics=False)
    limited._execute_node = AsyncMock()
    unknown_plan = MagicMock(stages=[SimpleNamespace(node_ids=["unknown"])])
    unknown_plan.get_node.return_value = None
    with pytest.raises(NodeExecutionError, match="Exceeded maximum node count: 0"):
        await limited._execute(unknown_plan, context, run, None, time())
    limited._execute_node.assert_not_awaited()
