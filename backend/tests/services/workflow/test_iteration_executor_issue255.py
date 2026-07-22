from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.iteration import (
    IterationNodeExecutor,
    IterationStartNodeExecutor,
    LoopNodeExecutor,
    LoopStartNodeExecutor,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executor", "node"),
    [
        (IterationStartNodeExecutor(), {"id": "start", "parentId": "iteration"}),
        (
            LoopStartNodeExecutor(),
            {"id": "start", "data": {"parentLoopId": "loop"}},
        ),
    ],
)
async def test_start_executors_filter_internal_parent_outputs(executor, node):
    context = MagicMock()
    context.get_node_outputs = AsyncMock(
        return_value={"item": "value", "_iteration_complete": False}
    )

    result = await executor.execute(node, context, MagicMock())

    assert result.outputs == {"item": "value"}


@pytest.mark.asyncio
async def test_start_executor_without_parent_returns_empty_outputs():
    context = MagicMock()
    context.get_node_outputs = AsyncMock()

    result = await IterationStartNodeExecutor().execute(
        {"id": "start"}, context, MagicMock()
    )

    assert result.outputs == {}
    context.get_node_outputs.assert_not_awaited()


@pytest.mark.asyncio
async def test_array_iteration_limits_items_and_publishes_safe_event_value():
    context = MagicMock(run_id="run-1")
    context.resolve_variable_ref = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
    context.get_variable = AsyncMock(return_value=None)
    context.set_variable = AsyncMock()
    stream = MagicMock()
    stream.publish_iteration = AsyncMock()
    node = {
        "id": "iteration",
        "data": {
            "iterationConfig": {
                "iteratorVariable": "{{items}}",
                "itemVariable": "entry",
                "indexVariable": "position",
                "maxIterations": 1,
            }
        },
    }

    with patch(
        "app.services.workflow.executors.iteration.StreamManager",
        return_value=stream,
    ):
        result = await IterationNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {
        "entry": {"id": 1},
        "position": 0,
        "total": 1,
        "results": [],
        "_iteration_complete": False,
        "_iteration_index": 0,
    }
    stream.publish_iteration.assert_awaited_once_with(
        node_id="iteration", iteration=1, total=1, is_start=True, item=None
    )


@pytest.mark.asyncio
async def test_array_iteration_wraps_scalar_then_completes_with_prior_results():
    context = MagicMock(run_id="run-1")
    context.resolve_variable_ref = AsyncMock(return_value="only")
    context.get_variable = AsyncMock(
        return_value={"index": 0, "results": ["processed"]}
    )
    context.set_variable = AsyncMock()

    result = await IterationNodeExecutor().execute(
        {"id": "iteration", "data": {"config": {"inputVariable": "value"}}},
        context,
        MagicMock(),
    )

    assert result.outputs == {
        "item": None,
        "index": 1,
        "total": 1,
        "results": ["processed"],
        "_iteration_complete": True,
    }
    context.set_variable.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [None, "not-an-object"])
async def test_object_iteration_rejects_non_mapping_values(items):
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=items)

    result = await IterationNodeExecutor().execute(
        {
            "id": "iteration",
            "data": {"iterationConfig": {"iteratorType": "object"}},
        },
        context,
        MagicMock(),
    )

    assert result.outputs == {
        "key": None,
        "value": None,
        "total": 0,
        "results": [],
        "_iteration_complete": True,
    }


@pytest.mark.asyncio
async def test_object_iteration_uses_custom_names_and_publishes_key():
    context = MagicMock(run_id="run-1")
    context.resolve_variable_ref = AsyncMock(return_value={"first": 1, "second": 2})
    context.get_variable = AsyncMock(return_value=None)
    context.set_variable = AsyncMock()
    stream = MagicMock()
    stream.publish_iteration = AsyncMock()

    with patch(
        "app.services.workflow.executors.iteration.StreamManager",
        return_value=stream,
    ):
        result = await IterationNodeExecutor().execute(
            {
                "id": "iteration",
                "data": {
                    "iterationConfig": {
                        "iteratorType": "object",
                        "keyVariable": "name",
                        "valueVariable": "amount",
                    }
                },
            },
            context,
            MagicMock(),
        )

    assert result.outputs["name"] == "first"
    assert result.outputs["amount"] == 1
    assert result.outputs["_iteration_complete"] is False
    stream.publish_iteration.assert_awaited_once_with(
        node_id="iteration", iteration=1, total=2, is_start=True, item="first"
    )


@pytest.mark.asyncio
async def test_loop_stops_at_limit_with_updated_results():
    context = MagicMock()
    context.get_variable = AsyncMock(
        side_effect=[{"count": 0, "results": []}, ["child-result"]]
    )
    node = {
        "id": "loop",
        "data": {
            "loopConfig": {
                "maxIterations": 1,
                "counterVariable": "count",
                "outputVariable": "collected",
            }
        },
    }

    result = await LoopNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {
        "count": 1,
        "collected": ["child-result"],
        "_loop_complete": True,
        "_loop_reason": "max_iterations",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("logic", "values", "reason"),
    [
        ("and", [True, True], "exit_conditions_met"),
        ("or", [False, True], "exit_conditions_met"),
        ("and", [True, False], None),
    ],
)
async def test_loop_exit_condition_logic(logic, values, reason):
    executor = LoopNodeExecutor()
    executor._evaluate_condition = AsyncMock(side_effect=values)
    context = MagicMock()
    context.get_variable = AsyncMock(return_value=None)
    context.set_variable = AsyncMock()
    node = {
        "id": "loop",
        "data": {
            "loopConfig": {
                "exitLogicOperator": logic,
                "exitConditions": [
                    {"variable": "a", "operator": "equals", "value": "1"},
                    {"variable": "b", "operator": "equals", "value": "2"},
                ],
            }
        },
    }

    result = await executor.execute(node, context, MagicMock())

    if reason:
        assert result.outputs["_loop_reason"] == reason
        context.set_variable.assert_not_awaited()
    else:
        assert result.outputs["_loop_complete"] is False
        context.set_variable.assert_awaited_once()


@pytest.mark.asyncio
async def test_loop_old_condition_false_stops():
    executor = LoopNodeExecutor()
    executor._evaluate_condition = AsyncMock(return_value=False)
    context = MagicMock()
    context.get_variable = AsyncMock(return_value=None)

    result = await executor.execute(
        {
            "id": "loop",
            "data": {"config": {"conditionVariable": "{{continue}}"}},
        },
        context,
        MagicMock(),
    )

    assert result.outputs["_loop_reason"] == "condition_false"


@pytest.mark.asyncio
async def test_loop_continuation_includes_existing_custom_variables():
    context = MagicMock()
    context.get_variable = AsyncMock(side_effect=[None, None, "saved", None])
    context.set_variable = AsyncMock()

    result = await LoopNodeExecutor().execute(
        {
            "id": "loop",
            "data": {
                "loopConfig": {
                    "loopVariables": [{"name": "memo"}, {}, {"name": "missing"}]
                }
            },
        },
        context,
        MagicMock(),
    )

    assert result.outputs["memo"] == "saved"
    assert "missing" not in result.outputs
    assert result.outputs["_loop_complete"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actual", "operator", "compare", "expected"),
    [
        (1, "equals", "1", True),
        (1, "not_equals", "2", True),
        (3, "greater_than", "2", True),
        (1, "less_than", "2", True),
        ("yes", "is_true", "", True),
        ("", "is_false", "", True),
        ([], "is_not_empty", "", True),
        (0, "unknown", "", False),
        ("invalid", "greater_than", "2", False),
    ],
)
async def test_loop_condition_operators(actual, operator, compare, expected):
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value=actual)

    result = await LoopNodeExecutor()._evaluate_condition(
        context, "{{actual}}", operator, compare
    )

    assert result is expected


@pytest.mark.asyncio
async def test_loop_condition_resolves_reference_comparison():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(side_effect=[2, 2])

    result = await LoopNodeExecutor()._evaluate_condition(
        context, "{{actual}}", "equals", "{{expected}}"
    )

    assert result is True
