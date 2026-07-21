from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.workflow.executors.variable import (
    ParameterExtractorNodeExecutor,
    VariableAggregatorNodeExecutor,
    VariableAssignmentNodeExecutor,
)


def context(**overrides):
    values = {
        "resolve_variable_ref": AsyncMock(),
        "get_variable": AsyncMock(),
        "set_variable": AsyncMock(),
        "get_node_outputs": AsyncMock(),
        "set_node_outputs": AsyncMock(),
        "get_all_node_outputs": AsyncMock(return_value={}),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_assignment_applies_operations_and_updates_matching_outputs():
    ctx = context(
        resolve_variable_ref=AsyncMock(side_effect=["resolved", 3]),
        get_variable=AsyncMock(side_effect=[[1, 2], None]),
        get_all_node_outputs=AsyncMock(return_value={"start": {"query": "old"}}),
    )
    node = {
        "data": {
            "variableAssignmentConfig": {
                "assignments": [
                    {
                        "targetVariable": "conversation.query",
                        "operation": "overwrite",
                        "variableRef": "start.query",
                    },
                    {
                        "targetVariable": "items",
                        "operation": "append",
                        "variableRef": "next",
                    },
                    {
                        "targetVariable": "status",
                        "operation": "set",
                        "constantValue": "done",
                    },
                    {"targetVariable": "temporary", "operation": "clear"},
                    {"operation": "set", "constantValue": "ignored"},
                ]
            }
        }
    }

    result = await VariableAssignmentNodeExecutor().execute(node, ctx, MagicMock())

    assert result.outputs == {
        "query": "resolved",
        "items": [1, 2, 3],
        "status": "done",
        "temporary": None,
    }
    ctx.set_node_outputs.assert_any_await("start", {"query": "resolved"})
    ctx.set_variable.assert_any_await("conversation.items", [1, 2, 3])


@pytest.mark.asyncio
async def test_assignment_appends_node_results_and_syncs_iteration_states():
    iteration_state = {"results": [1]}
    loop_state = {"results": [1]}
    ctx = context(
        resolve_variable_ref=AsyncMock(return_value=[2, 3]),
        get_variable=AsyncMock(
            side_effect=[iteration_state, iteration_state, loop_state]
        ),
        get_node_outputs=AsyncMock(return_value={"results": [0]}),
    )
    node = {
        "data": {
            "config": {
                "assignments": [
                    {
                        "targetVariable": "iteration.results",
                        "operation": "append",
                        "variableRef": "item",
                    }
                ]
            }
        }
    }

    result = await VariableAssignmentNodeExecutor().execute(node, ctx, MagicMock())

    assert result.outputs == {"results": [1, 2, 3]}
    ctx.set_node_outputs.assert_awaited_once_with("iteration", {"results": [1, 2, 3]})
    ctx.set_variable.assert_any_await(
        "iteration._iteration_state", {"results": [1, 2, 3]}
    )
    ctx.set_variable.assert_any_await("iteration._loop_state", {"results": [1, 2, 3]})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "values", "expected"),
    [
        ("array", {"a": 1, "b": 2}, [1, 2]),
        ("object", {"a": 1}, {"a": 1}),
        ("concat", {"a": "x", "b": None, "c": 2}, "x/2"),
        (
            "merge",
            {"a": {"nested": {"left": 1}}, "b": {"nested": {"right": 2}}, "c": 4},
            {"nested": {"left": 1, "right": 2}},
        ),
        ("unknown", {"a": 1}, {"a": 1}),
    ],
)
async def test_aggregator_modes(monkeypatch, mode, values, expected):
    executor = VariableAggregatorNodeExecutor()
    monkeypatch.setattr(executor, "resolve_inputs", AsyncMock(return_value=values))
    node = {
        "data": {
            "variableAggregatorConfig": {
                "mode": mode,
                "separator": "/",
                "outputVariable": "combined",
                "variables": [
                    {"id": "a", "sourceVariable": "one"},
                    {"targetKey": "b", "sourceVariable": "two"},
                ],
            }
        }
    }

    result = await executor.execute(node, context(), MagicMock())

    assert result.outputs == {"combined": expected}


@pytest.mark.asyncio
async def test_parameter_extractor_routes_and_validates_input(monkeypatch):
    executor = ParameterExtractorNodeExecutor()
    jsonpath = AsyncMock(return_value=MagicMock())
    regex = AsyncMock(return_value=MagicMock())
    llm = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(executor, "_extract_with_jsonpath", jsonpath)
    monkeypatch.setattr(executor, "_extract_with_regex", regex)
    monkeypatch.setattr(executor, "_extract_with_llm", llm)
    ctx = context(
        resolve_variable_ref=AsyncMock(side_effect=[None, {"x": 1}, "abc", "text"])
    )

    missing = await executor.execute({"data": {"config": {}}}, ctx, MagicMock())
    await executor.execute(
        {"data": {"parameterExtractorConfig": {"extractionMethod": "json_path"}}},
        ctx,
        MagicMock(),
    )
    await executor.execute(
        {"data": {"config": {"extractionMethod": "regex"}}}, ctx, MagicMock()
    )
    await executor.execute({"data": {"config": {}}}, ctx, MagicMock())

    assert missing.error == "validation_error"
    jsonpath.assert_awaited_once()
    regex.assert_awaited_once()
    llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_regex_extraction_handles_types_defaults_and_errors():
    executor = ParameterExtractorNodeExecutor()
    result = await executor._extract_with_regex(
        "age=42 tags=a tags=b",
        [
            {"name": "age", "pattern": r"age=(\d+)", "type": "number"},
            {"name": "tags", "pattern": r"tags=(\w+)", "type": "array"},
            {
                "name": "enabled",
                "pattern": "missing",
                "defaultValue": "yes",
                "type": "boolean",
            },
            {"name": "optional", "pattern": "missing"},
            {"name": "broken", "pattern": "[", "defaultValue": "7", "type": "number"},
            {"pattern": ".*"},
        ],
    )

    assert result.outputs == {
        "age": 42,
        "tags": ["a", "b"],
        "enabled": True,
        "optional": None,
        "broken": 7,
        "_extraction_method": "regex",
    }
    required = await executor._extract_with_regex(
        "nothing", [{"name": "value", "pattern": "missing", "required": True}]
    )
    assert required.error == "validation_error"


def test_parameter_helpers_and_output_specs():
    executor = ParameterExtractorNodeExecutor()

    assert executor._parse_default_value("2.5", "number") == 2.5
    assert executor._parse_default_value("[1, 2]", "array") == [1, 2]
    assert executor._parse_default_value("bad", "object") == "bad"
    assert executor._convert_value("bad", "number") == "bad"
    assert executor._convert_value("true", "boolean") is True
    assert [
        item.name
        for item in executor.get_output_specs(
            {"parameters": [{"name": "count", "type": "number"}, {}]}
        )
    ] == [
        "count",
        "_extraction_confidence",
    ]
    assert VariableAggregatorNodeExecutor().get_output_variables({"mode": "merge"}) == [
        {"name": "result", "type": "object"}
    ]
