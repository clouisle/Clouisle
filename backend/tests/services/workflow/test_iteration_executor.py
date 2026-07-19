"""Tests for workflow iteration executors."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.iteration import (
    MAX_ITERATIONS,
    IterationNodeExecutor,
    IterationStartNodeExecutor,
    LoopNodeExecutor,
    LoopStartNodeExecutor,
)


@pytest.fixture
def context():
    context = MagicMock()
    context.run_id = "run-1"
    context.resolve_variable_ref = AsyncMock()
    context.get_variable = AsyncMock(return_value=None)
    context.set_variable = AsyncMock()
    context.get_node_outputs = AsyncMock()
    return context


@pytest.fixture
def iteration():
    return IterationNodeExecutor()


def node(config: dict) -> dict:
    return {"id": "iterate", "data": {"iterationConfig": config}}


@pytest.mark.asyncio
async def test_array_iteration_advances_with_context_state(iteration, context):
    context.resolve_variable_ref.return_value = ["first", "second"]

    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ) as publish:
        first = await iteration.execute(
            node({"iteratorVariable": "{{input.items}}"}), context, MagicMock()
        )
        context.get_variable.return_value = {
            "index": 0,
            "results": ["first result"],
        }
        second = await iteration.execute(
            node({"iteratorVariable": "{{input.items}}"}), context, MagicMock()
        )
        context.get_variable.return_value = {
            "index": 1,
            "results": ["first result", "second result"],
        }
        complete = await iteration.execute(
            node({"iteratorVariable": "{{input.items}}"}), context, MagicMock()
        )

    assert first.outputs == {
        "item": "first",
        "index": 0,
        "total": 2,
        "results": [],
        "_iteration_complete": False,
        "_iteration_index": 0,
    }
    assert second.outputs["item"] == "second"
    assert second.outputs["results"] == ["first result"]
    assert complete.outputs == {
        "item": None,
        "index": 2,
        "total": 2,
        "results": ["first result", "second result"],
        "_iteration_complete": True,
    }
    assert context.set_variable.await_count == 2
    assert publish.await_count == 2


@pytest.mark.asyncio
async def test_parallel_configuration_uses_current_one_step_context_api(
    iteration, context
):
    context.resolve_variable_ref.return_value = [1, 2]

    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ):
        result = await iteration.execute(
            node(
                {
                    "iteratorVariable": "{{input.items}}",
                    "parallel": True,
                    "maxParallel": 2,
                }
            ),
            context,
            MagicMock(),
        )

    assert result.outputs["item"] == 1
    assert result.outputs["_iteration_index"] == 0
    context.set_variable.assert_awaited_once()


@pytest.mark.asyncio
async def test_array_empty_none_scalar_and_maximum_paths(iteration, context):
    context.resolve_variable_ref.return_value = None
    none_result = await iteration.execute(node({}), context, MagicMock())

    context.resolve_variable_ref.return_value = "only"
    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ):
        scalar_result = await iteration.execute(node({}), context, MagicMock())

    context.resolve_variable_ref.return_value = list(range(MAX_ITERATIONS + 1))
    context.get_variable.return_value = {"index": MAX_ITERATIONS - 2, "results": []}
    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ):
        capped_result = await iteration.execute(
            node({"maxIterations": MAX_ITERATIONS + 100}), context, MagicMock()
        )

    assert none_result.outputs["_iteration_complete"] is True
    assert scalar_result.outputs["item"] == "only"
    assert capped_result.outputs["item"] == MAX_ITERATIONS - 1
    assert capped_result.outputs["total"] == MAX_ITERATIONS


@pytest.mark.asyncio
async def test_object_iteration_and_non_object_error_path(iteration, context):
    context.resolve_variable_ref.return_value = {"a": 1, "b": 2}
    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ) as publish:
        result = await iteration.execute(
            node(
                {
                    "iteratorType": "object",
                    "keyVariable": "name",
                    "valueVariable": "amount",
                }
            ),
            context,
            MagicMock(),
        )

    context.resolve_variable_ref.return_value = ["not", "an", "object"]
    invalid_result = await iteration.execute(
        node({"iteratorType": "object"}), context, MagicMock()
    )

    assert result.outputs["name"] == "a"
    assert result.outputs["amount"] == 1
    publish.assert_awaited_once_with(
        node_id="iterate", iteration=1, total=2, is_start=True, item="a"
    )
    assert invalid_result.outputs["_iteration_complete"] is True
    assert invalid_result.outputs["total"] == 0


@pytest.mark.asyncio
async def test_iteration_start_and_loop_start_filter_internal_parent_outputs(context):
    context.get_node_outputs.return_value = {"item": "value", "_internal": True}

    iteration_result = await IterationStartNodeExecutor().execute(
        {"data": {"parentIterationId": "parent"}}, context, MagicMock()
    )
    loop_result = await LoopStartNodeExecutor().execute(
        {"parentId": "parent"}, context, MagicMock()
    )
    context.get_node_outputs.return_value = None
    missing_result = await IterationStartNodeExecutor().execute(
        {"data": {}}, context, MagicMock()
    )

    assert iteration_result.outputs == {"item": "value"}
    assert loop_result.outputs == {"item": "value"}
    assert missing_result.outputs == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "errors"),
    [
        ({}, ["Iteration variable is required"]),
        (
            {"iteratorVariable": "{{items}}", "iteratorType": "set"},
            ["Iterator type must be 'array' or 'object'"],
        ),
        (
            {"iteratorVariable": "{{items}}", "maxIterations": 0},
            ["Maximum iterations must be a positive integer"],
        ),
        (
            {"iteratorVariable": "{{items}}", "maxIterations": "many"},
            ["Maximum iterations must be a positive integer"],
        ),
        (
            {
                "iteratorVariable": "{{items}}",
                "parallel": True,
                "maxParallel": 0,
            },
            ["Maximum parallelism must be a positive integer"],
        ),
    ],
)
async def test_validate_config_rejects_invalid_iteration_modes(
    iteration, config, errors
):
    assert await iteration.validate_config(config) == errors


@pytest.mark.asyncio
async def test_validate_config_accepts_legacy_and_parallel_config(iteration):
    assert (
        await iteration.validate_config(
            {
                "inputVariable": "{{items}}",
                "iteratorType": "object",
                "maxIterations": 1,
                "parallel": True,
                "maxParallel": 2,
            }
        )
        == []
    )


@pytest.mark.asyncio
async def test_loop_returns_maximum_and_condition_completion(context):
    loop = LoopNodeExecutor()
    context.get_variable.side_effect = [
        {"count": 0, "results": ["saved"]},
        None,
    ]
    maximum = await loop.execute(
        {"id": "loop", "data": {"loopConfig": {"maxIterations": 1}}},
        context,
        MagicMock(),
    )

    context.get_variable.side_effect = [None, None]
    context.resolve_variable_ref.return_value = False
    condition = await loop.execute(
        {
            "id": "loop",
            "data": {
                "loopConfig": {
                    "conditionVariable": "{{input.continue}}",
                    "conditionOperator": "is_true",
                }
            },
        },
        context,
        MagicMock(),
    )

    assert maximum.outputs["_loop_reason"] == "max_iterations"
    assert maximum.outputs["results"] == ["saved"]
    assert condition.outputs["_loop_reason"] == "condition_false"


@pytest.mark.asyncio
async def test_loop_continues_custom_values_and_exit_conditions(context):
    loop = LoopNodeExecutor()
    context.get_variable.side_effect = [None, None, "carried"]
    result = await loop.execute(
        {
            "id": "loop",
            "data": {
                "loopConfig": {
                    "loopVariables": [{"name": "custom"}, {}],
                    "outputVariable": "collected",
                }
            },
        },
        context,
        MagicMock(),
    )

    context.get_variable.side_effect = [None, None]
    context.resolve_variable_ref.return_value = "stop"
    exit_result = await loop.execute(
        {
            "id": "loop",
            "data": {
                "loopConfig": {
                    "exitConditions": [
                        {"variable": "{{input.state}}", "value": "stop"}
                    ],
                    "exitLogicOperator": "or",
                }
            },
        },
        context,
        MagicMock(),
    )

    assert result.outputs["custom"] == "carried"
    assert result.outputs["_loop_complete"] is False
    assert exit_result.outputs["_loop_reason"] == "exit_conditions_met"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operator", "actual", "expected"),
    [
        ("equals", "2", True),
        ("not_equals", "2", False),
        ("greater_than", 3, True),
        ("less_than", 3, False),
        ("is_true", 1, True),
        ("is_false", 0, True),
        ("is_not_empty", "", False),
        ("unknown", "value", True),
        ("greater_than", "bad", False),
    ],
)
async def test_loop_condition_operators(
    loop_operator_context, operator, actual, expected
):
    loop = LoopNodeExecutor()
    loop_operator_context.resolve_variable_ref.return_value = actual
    assert (
        await loop._evaluate_condition(
            loop_operator_context, "{{value}}", operator, "2"
        )
        is expected
    )


@pytest.fixture
def loop_operator_context():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock()
    return context


def test_output_declarations_follow_iteration_mode(iteration):
    assert [item["name"] for item in iteration.get_output_variables({})] == [
        "item",
        "index",
        "total",
        "results",
    ]
    assert [
        item.name for item in iteration.get_output_specs({"iteratorType": "object"})
    ] == [
        "key",
        "value",
        "total",
        "results",
    ]
