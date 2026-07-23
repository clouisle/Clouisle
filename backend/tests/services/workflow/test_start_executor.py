"""Behavioral tests for workflow start node executors."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.services.workflow.context import ExecutionContext
from app.services.workflow.executors.start import (
    TriggerNodeExecutor,
    UserInputNodeExecutor,
)


class TestUserInputNodeExecutor:
    @pytest.mark.asyncio
    async def test_uses_parameters_fallback_defaults_and_skips_unnamed_inputs(self):
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=[None, "7"])
        node = {
            "data": {
                "parameters": [
                    {},
                    {"name": "query", "default": "fallback"},
                    {"name": "limit", "type": "number"},
                ]
            }
        }

        result = await UserInputNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"query": "fallback", "limit": 7}
        assert context.get_variable.await_args_list == [
            call("sys.inputs.query"),
            call("sys.inputs.limit"),
        ]

    @pytest.mark.asyncio
    async def test_missing_required_input_returns_error(self):
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value=None)
        node = {
            "data": {
                "config": {
                    "variables": [
                        {"name": "query", "required": True, "default": "ignored"}
                    ]
                }
            }
        }

        result = await UserInputNodeExecutor().execute(node, context, MagicMock())

        assert result.success is False
        assert result.error == "Required input 'query' not provided"

    @pytest.mark.asyncio
    async def test_empty_configuration_produces_no_outputs(self):
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock()

        result = await UserInputNodeExecutor().execute({}, context, MagicMock())

        assert result.outputs == {}
        context.get_variable.assert_not_awaited()

    @pytest.mark.parametrize(
        "value,var_type,expected",
        [
            ("1.5", "number", 1.5),
            ("invalid", "number", "invalid"),
            (True, "boolean", True),
            ("YES", "boolean", True),
            ("no", "boolean", False),
            ([1], "array", [1]),
            (1, "array", [1]),
            ({"a": 1}, "object", {"a": 1}),
            (1, "object", {"value": 1}),
            (9, "string", "9"),
            (None, "string", None),
        ],
    )
    def test_type_conversions(self, value, var_type, expected):
        assert UserInputNodeExecutor()._coerce_type(value, var_type) == expected

    def test_declares_named_outputs_with_default_string_type(self):
        config = {
            "variables": [
                {},
                {"name": "query"},
                {"name": "count", "type": "number"},
            ]
        }
        executor = UserInputNodeExecutor()

        assert executor.get_output_variables(config) == [
            {"name": "query", "type": "string"},
            {"name": "count", "type": "number"},
        ]
        assert [
            (decl.name, decl.type.kind) for decl in executor.get_output_specs(config)
        ] == [
            ("query", "string"),
            ("count", "number"),
        ]


class TestTriggerNodeExecutor:
    @pytest.mark.asyncio
    async def test_applies_trigger_defaults_and_includes_metadata(self):
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=[None, "payload"])
        node = {
            "data": {
                "config": {
                    "variables": [
                        {},
                        {"name": "event", "default": "created"},
                        {"name": "body"},
                    ]
                }
            }
        }

        result = await TriggerNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs["_trigger_type"] == "manual"
        assert result.outputs["_trigger_time"]
        assert result.outputs["event"] == "created"
        assert result.outputs["body"] == "payload"
        assert context.get_variable.await_args_list == [
            call("sys.inputs.event"),
            call("sys.inputs.body"),
        ]

    def test_declares_metadata_and_named_outputs(self):
        config = {"variables": [{}, {"name": "event", "type": "object"}]}
        executor = TriggerNodeExecutor()

        assert executor.get_output_variables(config) == [
            {"name": "_trigger_type", "type": "string"},
            {"name": "_trigger_time", "type": "string"},
            {"name": "event", "type": "object"},
        ]
        assert [
            (decl.name, decl.type.kind) for decl in executor.get_output_specs(config)
        ] == [
            ("_trigger_type", "string"),
            ("_trigger_time", "string"),
            ("event", "object"),
        ]
