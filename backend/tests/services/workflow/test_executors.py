"""
Tests for node executors.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.sandbox.models import SandboxResult
from app.services.workflow.executors.answer import AnswerNodeExecutor
from app.services.workflow.executors.code import CodeNodeExecutor
from app.services.workflow.executors.condition import ConditionNodeExecutor
from app.services.workflow.executors.start import (
    TriggerNodeExecutor,
    UserInputNodeExecutor,
)
from app.services.workflow.executors.template import TemplateNodeExecutor


class TestStartExecutors:
    @pytest.mark.asyncio
    async def test_user_input_reads_values_and_applies_defaults(self):
        node = {
            "id": "start_1",
            "data": {
                "config": {
                    "variables": [
                        {"name": "query", "type": "string", "required": True},
                        {"name": "limit", "type": "number", "default": 10},
                    ]
                }
            },
        }
        context = MagicMock()
        context.get_variable = AsyncMock(side_effect=["test query", None])

        result = await UserInputNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"query": "test query", "limit": 10}
        assert context.get_variable.await_args_list == [
            call("sys.inputs.query"),
            call("sys.inputs.limit"),
        ]

    @pytest.mark.asyncio
    async def test_user_input_rejects_missing_required_value(self):
        node = {
            "id": "start_1",
            "data": {
                "config": {
                    "variables": [{"name": "query", "type": "string", "required": True}]
                }
            },
        }
        context = MagicMock()
        context.get_variable = AsyncMock(return_value=None)

        result = await UserInputNodeExecutor().execute(node, context, MagicMock())

        assert result.error == "Required input 'query' not provided"

    @pytest.mark.asyncio
    async def test_trigger_includes_configured_values_and_metadata(self):
        node = {
            "id": "trigger_1",
            "data": {
                "config": {
                    "triggerType": "webhook",
                    "variables": [{"name": "event", "default": "created"}],
                }
            },
        }
        context = MagicMock()
        context.get_variable = AsyncMock(return_value=None)

        result = await TriggerNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs["_trigger_type"] == "webhook"
        assert result.outputs["_trigger_time"]
        assert result.outputs["event"] == "created"


class TestAnswerExecutor:
    @pytest.mark.asyncio
    async def test_concatenates_configured_outputs(self):
        node = {
            "id": "answer_1",
            "data": {
                "answerConfig": {
                    "outputs": [
                        {"sourceVariable": "{{first.value}}"},
                        {"sourceVariable": "{{second.value}}"},
                    ]
                }
            },
        }
        context = MagicMock(run_id="run_1")
        context.get_node_outputs = AsyncMock(return_value={})
        context.resolve_variable_ref = AsyncMock(side_effect=["hello", {"ok": True}])

        with patch(
            "app.services.workflow.stream.StreamManager.publish_token",
            new=AsyncMock(),
        ) as publish_token:
            result = await AnswerNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"answer": 'hello\n{"ok": true}'}
        assert publish_token.await_args_list == [
            call("answer_1", "hello"),
            call("answer_1", "\n"),
            call("answer_1", '{"ok": true}'),
        ]


class TestConditionExecutor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("score", "expected_branch"),
        [(75, "high"), (25, "else")],
    )
    async def test_selects_matching_or_default_branch(self, score, expected_branch):
        node = {
            "id": "condition_1",
            "data": {
                "branches": [
                    {
                        "id": "high",
                        "conditions": [
                            {
                                "variable": "{{score}}",
                                "operator": "greater_than",
                                "value": 50,
                            }
                        ],
                    },
                    {"id": "else", "isDefault": True},
                ]
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=score)
        context.set_branch = AsyncMock()

        result = await ConditionNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs["matched_branch"] == expected_branch
        assert result.next_handles == [expected_branch]
        context.set_branch.assert_awaited_once_with("condition_1", expected_branch)


class TestCodeExecutor:
    @pytest.mark.asyncio
    async def test_returns_sandbox_outputs(self):
        node = {
            "id": "code_1",
            "data": {
                "codeConfig": {
                    "language": "python",
                    "code": "def main(inputs):\n    return {'result': inputs['value'] * 2}",
                    "inputs": [
                        {
                            "name": "value",
                            "source": "variable",
                            "variableRef": "{{start.value}}",
                        }
                    ],
                }
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=21)

        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job_1", success=True, result={"result": 42}
                )
            ),
        ):
            result = await CodeNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"result": 42}

    @pytest.mark.asyncio
    async def test_rejects_missing_code(self):
        result = await CodeNodeExecutor().execute(
            {"id": "code_1", "data": {"codeConfig": {}}},
            MagicMock(),
            MagicMock(),
        )

        assert result.error == "tool_code_not_defined"


class TestTemplateExecutor:
    @pytest.mark.asyncio
    async def test_renders_frontend_template_config(self):
        node = {
            "id": "template_1",
            "data": {
                "templateConfig": {
                    "template": "Hello, {{ name }}! You have {{ count }} messages.",
                    "inputs": [
                        {
                            "name": "name",
                            "source": "constant",
                            "constantValue": "Alice",
                        },
                        {
                            "name": "count",
                            "source": "variable",
                            "variableRef": "{{start.count}}",
                        },
                    ],
                    "outputVariable": "message",
                }
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=5)

        result = await TemplateNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"message": "Hello, Alice! You have 5 messages."}

    @pytest.mark.asyncio
    async def test_reports_template_syntax_error(self):
        node = {
            "id": "template_1",
            "data": {"templateConfig": {"template": "{% if %}"}},
        }

        result = await TemplateNodeExecutor().execute(node, MagicMock(), MagicMock())

        assert result.error == "validation_error"
