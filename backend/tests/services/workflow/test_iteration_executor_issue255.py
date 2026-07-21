from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.iteration import (
    IterationNodeExecutor,
    IterationStartNodeExecutor,
    LoopStartNodeExecutor,
)


def context(**returns):
    value = MagicMock(run_id="run-255")
    value.resolve_variable_ref = AsyncMock(return_value=returns.get("resolved"))
    value.get_variable = AsyncMock(return_value=returns.get("state"))
    value.set_variable = AsyncMock()
    value.get_node_outputs = AsyncMock(return_value=returns.get("outputs"))
    return value


def iteration_node(config):
    return {"id": "iterate", "data": {"iterationConfig": config}}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executor", "node"),
    [
        (IterationStartNodeExecutor(), {"data": {"parentIterationId": "parent"}}),
        (LoopStartNodeExecutor(), {"data": {"parentLoopId": "parent"}}),
    ],
)
async def test_start_nodes_filter_internal_parent_outputs(executor, node):
    ctx = context(outputs={"item": "value", "_internal": True})

    result = await executor.execute(node, ctx, MagicMock())

    assert result.outputs == {"item": "value"}
    ctx.get_node_outputs.assert_awaited_once_with("parent")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "executor", [IterationStartNodeExecutor(), LoopStartNodeExecutor()]
)
async def test_start_nodes_return_empty_without_parent(executor):
    result = await executor.execute({"data": {}}, context(), MagicMock())

    assert result.outputs == {}


@pytest.mark.asyncio
async def test_array_iteration_wraps_scalar_hides_collection_event_and_completes():
    executor = IterationNodeExecutor()
    ctx = context(resolved={"nested": True})

    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ) as publish:
        first = await executor.execute(
            iteration_node({"itemVariable": "entry", "indexVariable": "position"}),
            ctx,
            MagicMock(),
        )
        ctx.get_variable.return_value = {"index": 0, "results": ["saved"]}
        complete = await executor.execute(
            iteration_node({"itemVariable": "entry", "indexVariable": "position"}),
            ctx,
            MagicMock(),
        )

    assert first.outputs == {
        "entry": {"nested": True},
        "position": 0,
        "total": 1,
        "results": [],
        "_iteration_complete": False,
        "_iteration_index": 0,
    }
    assert complete.outputs == {
        "entry": None,
        "position": 1,
        "total": 1,
        "results": ["saved"],
        "_iteration_complete": True,
    }
    assert publish.await_args.kwargs["item"] is None


@pytest.mark.asyncio
async def test_array_none_and_limit_paths():
    executor = IterationNodeExecutor()
    empty_ctx = context(resolved=None)

    empty = await executor.execute(iteration_node({}), empty_ctx, MagicMock())

    limited_ctx = context(resolved=[1, 2, 3])
    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ):
        limited = await executor.execute(
            iteration_node({"maxIterations": 2}), limited_ctx, MagicMock()
        )

    assert empty.outputs["_iteration_complete"] is True
    assert empty.outputs["total"] == 0
    assert limited.outputs["item"] == 1
    assert limited.outputs["total"] == 2


@pytest.mark.asyncio
async def test_object_iteration_limits_continues_and_rejects_non_mapping():
    executor = IterationNodeExecutor()
    ctx = context(resolved={"a": 1, "b": 2})

    with patch(
        "app.services.workflow.executors.iteration.StreamManager.publish_iteration",
        new_callable=AsyncMock,
    ) as publish:
        first = await executor.execute(
            iteration_node(
                {
                    "iteratorType": "object",
                    "keyVariable": "name",
                    "valueVariable": "amount",
                    "maxIterations": 1,
                }
            ),
            ctx,
            MagicMock(),
        )
        ctx.get_variable.return_value = {"index": 0, "results": [1]}
        complete = await executor.execute(
            iteration_node({"iteratorType": "object", "maxIterations": 1}),
            ctx,
            MagicMock(),
        )

    invalid_ctx = context(resolved=["not-a-mapping"])
    invalid = await executor.execute(
        iteration_node({"iteratorType": "object"}), invalid_ctx, MagicMock()
    )

    assert first.outputs["name"] == "a"
    assert first.outputs["amount"] == 1
    assert complete.outputs["_iteration_complete"] is True
    assert complete.outputs["results"] == [1]
    assert invalid.outputs["_iteration_complete"] is True
    publish.assert_awaited_once()


def test_output_metadata_covers_array_and_object_modes():
    executor = IterationNodeExecutor()

    array_variables = executor.get_output_variables(
        {"itemVariable": "entry", "indexVariable": "position"}
    )
    object_variables = executor.get_output_variables(
        {"iteratorType": "object", "keyVariable": "name", "valueVariable": "amount"}
    )
    array_specs = executor.get_output_specs({})
    object_specs = executor.get_output_specs({"iteratorType": "object"})

    assert [variable["name"] for variable in array_variables] == [
        "entry",
        "position",
        "total",
        "results",
    ]
    assert [variable["name"] for variable in object_variables] == [
        "name",
        "amount",
        "total",
        "results",
    ]
    assert [(spec.name, spec.type.kind) for spec in array_specs] == [
        ("item", "any"),
        ("index", "number"),
        ("total", "number"),
        ("results", "array"),
    ]
    assert [(spec.name, spec.type.kind) for spec in object_specs] == [
        ("key", "string"),
        ("value", "any"),
        ("total", "number"),
        ("results", "array"),
    ]
