from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.workflow.executors import iteration


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("executor", "node", "parent_id"),
    [
        (
            iteration.IterationStartNodeExecutor(),
            {"id": "start", "data": {"parentIterationId": "iteration"}},
            "iteration",
        ),
        (
            iteration.LoopStartNodeExecutor(),
            {"id": "start", "parentId": "loop"},
            "loop",
        ),
    ],
)
async def test_start_nodes_filter_internal_parent_outputs(executor, node, parent_id):
    context = MagicMock()
    context.get_node_outputs = AsyncMock(
        return_value={"value": 1, "_iteration_complete": False}
    )

    result = await executor.execute(node, context, MagicMock())

    assert result.outputs == {"value": 1}
    context.get_node_outputs.assert_awaited_once_with(parent_id)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("executor", "node"),
    [
        (iteration.IterationStartNodeExecutor(), {"id": "start", "data": {}}),
        (
            iteration.LoopStartNodeExecutor(),
            {"id": "start", "data": {"parentLoopId": "loop"}},
        ),
    ],
)
async def test_start_nodes_return_empty_without_parent_outputs(executor, node):
    context = MagicMock()
    context.get_node_outputs = AsyncMock(return_value=None)

    result = await executor.execute(node, context, MagicMock())

    assert result.outputs == {}


@pytest.mark.anyio
async def test_array_iteration_handles_empty_scalar_limit_and_completion(monkeypatch):
    publisher = MagicMock()
    publisher.publish_iteration = AsyncMock()
    stream_manager = MagicMock(return_value=publisher)
    monkeypatch.setattr(iteration, "StreamManager", stream_manager)
    executor = iteration.IterationNodeExecutor()
    context = MagicMock(run_id="run")
    context.resolve_variable_ref = AsyncMock(side_effect=[None, "one", [1, 2]])
    context.get_variable = AsyncMock(
        side_effect=[None, {"index": 0, "results": ["done"]}]
    )
    context.set_variable = AsyncMock()

    empty = await executor.execute(
        {"id": "iter", "data": {"iterationConfig": {"iteratorVariable": "x"}}},
        context,
        MagicMock(),
    )
    scalar = await executor.execute(
        {"id": "iter", "data": {"config": {"inputVariable": "x"}}},
        context,
        MagicMock(),
    )
    complete = await executor.execute(
        {
            "id": "iter",
            "data": {"iterationConfig": {"iteratorVariable": "x", "maxIterations": 1}},
        },
        context,
        MagicMock(),
    )

    assert empty.outputs["_iteration_complete"] is True
    assert scalar.outputs == {
        "item": "one",
        "index": 0,
        "total": 1,
        "results": [],
        "_iteration_complete": False,
        "_iteration_index": 0,
    }
    assert complete.outputs == {
        "item": None,
        "index": 1,
        "total": 1,
        "results": ["done"],
        "_iteration_complete": True,
    }
    publisher.publish_iteration.assert_awaited_once_with(
        node_id="iter", iteration=1, total=1, is_start=True, item="one"
    )


@pytest.mark.anyio
async def test_object_iteration_handles_invalid_active_and_complete(monkeypatch):
    publisher = MagicMock()
    publisher.publish_iteration = AsyncMock()
    monkeypatch.setattr(iteration, "StreamManager", MagicMock(return_value=publisher))
    executor = iteration.IterationNodeExecutor()
    context = MagicMock(run_id="run")
    context.resolve_variable_ref = AsyncMock(
        side_effect=["not-an-object", {"a": 1, "b": 2}, {"a": 1}]
    )
    context.get_variable = AsyncMock(side_effect=[None, {"index": 0, "results": [1]}])
    context.set_variable = AsyncMock()
    node = {
        "id": "iter",
        "data": {
            "iterationConfig": {
                "iteratorVariable": "x",
                "iteratorType": "object",
                "keyVariable": "name",
                "valueVariable": "content",
                "maxIterations": 1,
            }
        },
    }

    invalid = await executor.execute(node, context, MagicMock())
    active = await executor.execute(node, context, MagicMock())
    complete = await executor.execute(node, context, MagicMock())

    assert invalid.outputs["_iteration_complete"] is True
    assert active.outputs["name"] == "a"
    assert active.outputs["content"] == 1
    assert active.outputs["total"] == 1
    assert complete.outputs == {
        "name": None,
        "content": None,
        "total": 1,
        "results": [1],
        "_iteration_complete": True,
    }
    publisher.publish_iteration.assert_awaited_once_with(
        node_id="iter", iteration=1, total=1, is_start=True, item="a"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("config", "loop_state", "resolved", "reason"),
    [
        ({"maxIterations": 0}, None, [], "max_iterations"),
        (
            {
                "exitConditions": [
                    {"variable": "x", "operator": "equals", "value": "yes"},
                    {"variable": "y", "operator": "equals", "value": "no"},
                ],
                "exitLogicOperator": "or",
            },
            None,
            ["yes", "yes"],
            "exit_conditions_met",
        ),
        (
            {
                "conditionVariable": "x",
                "conditionOperator": "greater_than",
                "conditionValue": "bad-number",
            },
            None,
            [1],
            "condition_false",
        ),
    ],
)
async def test_loop_stop_reasons(config, loop_state, resolved, reason):
    context = MagicMock()
    context.get_variable = AsyncMock(side_effect=[loop_state, None])
    context.resolve_variable_ref = AsyncMock(side_effect=resolved)

    result = await iteration.LoopNodeExecutor().execute(
        {"id": "loop", "data": {"loopConfig": config}}, context, MagicMock()
    )

    assert result.outputs["_loop_complete"] is True
    assert result.outputs["_loop_reason"] == reason
    context.set_variable.assert_not_called()


@pytest.mark.anyio
async def test_loop_continues_with_updated_results_and_existing_variables():
    context = MagicMock()
    context.get_variable = AsyncMock(
        side_effect=[
            {"count": 1, "results": []},
            ["updated"],
            "kept",
            None,
        ]
    )
    context.set_variable = AsyncMock()
    config = {
        "maxIterations": 5,
        "counterVariable": "count",
        "outputVariable": "items",
        "loopVariables": [{"name": "saved"}, {"name": "missing"}, {}],
    }

    result = await iteration.LoopNodeExecutor().execute(
        {"id": "loop", "data": {"config": config}}, context, MagicMock()
    )

    assert result.outputs == {
        "count": 2,
        "items": ["updated"],
        "_loop_complete": False,
        "_loop_iteration": 2,
        "saved": "kept",
    }
    context.set_variable.assert_awaited_once_with(
        "loop._loop_state", {"count": 2, "results": ["updated"]}
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operator", "actual", "compare", "expected"),
    [
        ("not_equals", "a", "b", True),
        ("less_than", 1, "2", True),
        ("is_true", 1, "", True),
        ("is_false", 0, "", True),
        ("is_not_empty", "", "", False),
        ("unknown", [], "", False),
    ],
)
async def test_loop_condition_operators(operator, actual, compare, expected):
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(side_effect=[actual, compare])

    result = await iteration.LoopNodeExecutor()._evaluate_condition(
        context, "{{actual}}", operator, "{{compare}}"
    )

    assert result is expected
