"""Behavioral tests for the template node executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.workflow.executors.template import TemplateNodeExecutor


@pytest.fixture
def context():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(
        side_effect=lambda ref: {
            "{{start.name}}": "Alice",
            "{{start.items}}": ["one", "two"],
        }[ref]
    )
    return context


@pytest.mark.asyncio
async def test_renders_frontend_config_with_resolved_inputs(context):
    node = {
        "data": {
            "templateConfig": {
                "template": "Hello {{ name | upper }}: {% for item in items %}{{ item }}{% if not loop.last %}, {% endif %}{% endfor %}",
                "inputs": [
                    {"name": "name", "variableRef": "{{start.name}}"},
                    {"name": "items", "variableRef": "{{start.items}}"},
                ],
                "outputVariable": "message",
            }
        }
    }

    result = await TemplateNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"message": "Hello ALICE: one, two"}
    assert result.error is None


@pytest.mark.asyncio
async def test_uses_legacy_config_and_default_output_name(context):
    node = {
        "data": {
            "config": {
                "template": "Hello {{ name }}",
                "inputs": [{"name": "name", "variableRef": "{{start.name}}"}],
            }
        }
    }

    result = await TemplateNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"output": "Hello Alice"}


@pytest.mark.asyncio
async def test_empty_template_returns_configured_empty_output_without_resolving(
    context,
):
    node = {
        "data": {
            "templateConfig": {
                "template": "",
                "inputs": [{"name": "name", "variableRef": "{{start.name}}"}],
                "outputVariable": "message",
            }
        }
    }

    result = await TemplateNodeExecutor().execute(node, context, MagicMock())

    assert result.outputs == {"message": ""}
    context.resolve_variable_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_plain_missing_variable_renders_empty_string():
    result = await TemplateNodeExecutor().execute(
        {"data": {"templateConfig": {"template": "Value: {{ missing }}"}}},
        MagicMock(),
        MagicMock(),
    )

    assert result.outputs == {"output": "Value: "}
    assert result.error is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template", "expected_error"),
    [
        ("{% if %}", "validation_error"),
        ("{{ missing.attribute }}", "validation_error"),
    ],
)
async def test_reports_invalid_templates(template, expected_error):
    result = await TemplateNodeExecutor().execute(
        {"data": {"templateConfig": {"template": template}}},
        MagicMock(),
        MagicMock(),
    )

    assert result.outputs == {}
    assert result.error == expected_error


@pytest.mark.asyncio
async def test_reports_unexpected_rendering_error(monkeypatch):
    executor = TemplateNodeExecutor()

    def fail(_template):
        raise RuntimeError("render failed")

    monkeypatch.setattr(executor.env, "from_string", fail)

    result = await executor.execute(
        {"data": {"templateConfig": {"template": "Hello"}}},
        MagicMock(),
        MagicMock(),
    )

    assert result.error == "workflow_execution_error"


def test_output_metadata_uses_configured_name():
    executor = TemplateNodeExecutor()

    assert executor.get_output_variables({"outputVariable": "message"}) == [
        {"name": "message", "type": "string"}
    ]
    specs = executor.get_output_specs({"outputVariable": "message"})
    assert len(specs) == 1
    assert specs[0].name == "message"
    assert specs[0].type.kind == "string"
