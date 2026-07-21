"""Focused coverage for start and template workflow executors."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.workflow.executors.start import (
    TriggerNodeExecutor,
    UserInputNodeExecutor,
)
from app.services.workflow.executors.template import TemplateNodeExecutor


class TestUserInputNodeExecutor:
    @pytest.mark.asyncio
    async def test_frontend_parameters_fallback_coerces_inputs_and_defaults(self):
        context = MagicMock()
        context.get_variable = AsyncMock(
            side_effect=lambda name: {
                "sys.inputs.query": "hello",
                "sys.inputs.limit": "3",
                "sys.inputs.enabled": "yes",
            }.get(name)
        )

        result = await UserInputNodeExecutor().execute(
            {
                "data": {
                    "parameters": [
                        {"name": "query", "type": "string", "required": True},
                        {"name": "limit", "type": "number"},
                        {"name": "enabled", "type": "boolean"},
                        {"name": "tags", "type": "array", "default": "new"},
                        {"name": "metadata", "type": "object", "default": "raw"},
                        {"type": "string", "default": "ignored"},
                    ]
                }
            },
            context,
            MagicMock(),
        )

        assert result.success
        assert result.outputs == {
            "query": "hello",
            "limit": 3,
            "enabled": True,
            "tags": ["new"],
            "metadata": {"value": "raw"},
        }

    @pytest.mark.asyncio
    async def test_required_missing_input_fails_fast(self):
        context = MagicMock()
        context.get_variable = AsyncMock(return_value=None)

        result = await UserInputNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "variables": [
                            {"name": "query", "type": "string", "required": True}
                        ]
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.error == "Required input 'query' not provided"


class TestTriggerNodeExecutor:
    @pytest.mark.asyncio
    async def test_trigger_outputs_metadata_and_variable_defaults(self):
        context = MagicMock()
        context.get_variable = AsyncMock(return_value=None)

        result = await TriggerNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "triggerType": "webhook",
                        "variables": [{"name": "payload", "default": {"ok": True}}],
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.success
        assert result.outputs["_trigger_type"] == "webhook"
        assert result.outputs["_trigger_time"]
        assert result.outputs["payload"] == {"ok": True}


class TestTemplateNodeExecutor:
    @pytest.mark.asyncio
    async def test_template_config_renders_resolved_inputs_to_custom_output(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(
            side_effect=lambda ref: {
                "{{start.user}}": {"name": "Ada"},
                "{{start.items}}": ["docs", "tests"],
            }[ref]
        )

        result = await TemplateNodeExecutor().execute(
            {
                "data": {
                    "templateConfig": {
                        "template": (
                            "Hello {{ user.name }}:"
                            "{% for item in items %} {{ item }}{% endfor %}"
                        ),
                        "inputs": [
                            {"name": "user", "variableRef": "{{start.user}}"},
                            {"name": "items", "variableRef": "{{start.items}}"},
                        ],
                        "outputVariable": "message",
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.success
        assert result.outputs == {"message": "Hello Ada: docs tests"}

    @pytest.mark.asyncio
    async def test_template_syntax_error_returns_validation_error(self):
        result = await TemplateNodeExecutor().execute(
            {"data": {"config": {"template": "Hello {% if broken"}}},
            MagicMock(),
            MagicMock(),
        )

        assert result.error == "validation_error"
