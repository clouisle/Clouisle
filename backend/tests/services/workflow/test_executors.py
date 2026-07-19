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


class VariableExecutionContext:
    """In-memory context matching variable executor interactions."""

    def __init__(self, variables=None, node_outputs=None):
        self.variables = variables or {}
        self.node_outputs = node_outputs or {}

    async def resolve_variable_ref(self, reference):
        return self.variables.get(reference)

    async def get_variable(self, name):
        return self.variables.get(name)

    async def set_variable(self, name, value):
        self.variables[name] = value

    async def get_node_outputs(self, node_id):
        return self.node_outputs.get(node_id)

    async def set_node_outputs(self, node_id, outputs):
        self.node_outputs[node_id] = outputs

    async def get_all_node_outputs(self):
        return self.node_outputs


class TestVariableExecutors:
    @pytest.mark.asyncio
    async def test_assignment_updates_conversation_and_matching_node_outputs(self):
        from app.services.workflow.executors.variable import (
            VariableAssignmentNodeExecutor,
        )

        context = VariableExecutionContext(
            variables={"{{start.query}}": "processed"},
            node_outputs={"start": {"query": "raw"}, "other": {"untouched": 1}},
        )
        result = await VariableAssignmentNodeExecutor().execute(
            {
                "id": "assign",
                "data": {
                    "variableAssignmentConfig": {
                        "assignments": [
                            {
                                "targetVariable": "conversation.query",
                                "operation": "overwrite",
                                "variableRef": "{{start.query}}",
                            },
                            {
                                "targetVariable": "conversation.status",
                                "operation": "set",
                                "constantValue": "complete",
                            },
                            {
                                "targetVariable": "conversation.temp",
                                "operation": "clear",
                            },
                            {"operation": "set", "constantValue": "ignored"},
                        ]
                    }
                },
            },
            context,
            MagicMock(),
        )

        assert result.success
        assert result.outputs == {
            "query": "processed",
            "status": "complete",
            "temp": None,
        }
        assert context.variables["query"] == "processed"
        assert context.variables["conversation.query"] == "processed"
        assert context.node_outputs["start"]["query"] == "processed"
        assert context.node_outputs["other"] == {"untouched": 1}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("current", "appended", "expected"),
        [
            ([1], 2, [1, 2]),
            ([1], [2, 3], [1, 2, 3]),
            ({"left": 1}, {"right": 2}, {"left": 1, "right": 2}),
            ("a", 2, "a2"),
            (1, 2.5, 3.5),
            (None, "first", ["first"]),
            ("wrong", {"value": 1}, ["wrong", {"value": 1}]),
        ],
    )
    async def test_assignment_append_handles_supported_value_types(
        self, current, appended, expected
    ):
        from app.services.workflow.executors.variable import (
            VariableAssignmentNodeExecutor,
        )

        context = VariableExecutionContext({"items": current, "{{value}}": appended})
        result = await VariableAssignmentNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "assignments": [
                            {
                                "targetVariable": "items",
                                "operation": "append",
                                "variableRef": "{{value}}",
                            }
                        ]
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.outputs == {"items": expected}
        assert context.variables["items"] == expected

    @pytest.mark.asyncio
    async def test_assignment_updates_node_and_loop_iteration_result_state(self):
        from app.services.workflow.executors.variable import (
            VariableAssignmentNodeExecutor,
        )

        context = VariableExecutionContext(
            variables={
                "{{next}}": "b",
                "loop.results": ["a"],
                "loop._iteration_state": {"results": ["a"]},
                "loop._loop_state": {"results": ["a"]},
            },
            node_outputs={"loop": {"results": ["a"]}},
        )
        result = await VariableAssignmentNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "assignments": [
                            {
                                "targetVariable": "loop.results",
                                "operation": "append",
                                "variableRef": "{{next}}",
                            }
                        ]
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.outputs == {"results": ["a", "b"]}
        assert context.node_outputs["loop"]["results"] == ["a", "b"]
        assert context.variables["loop._iteration_state"]["results"] == ["a", "b"]
        assert context.variables["loop._loop_state"]["results"] == ["a", "b"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("mode", "variables", "separator", "expected"),
        [
            ("array", [("first", 1), ("second", None)], "", [1, None]),
            ("object", [("first", 1), ("second", 2)], "", {"first": 1, "second": 2}),
            ("concat", [("first", "a"), ("second", None), ("third", 3)], "/", "a/3"),
            (
                "merge",
                [
                    ("first", {"nested": {"left": 1}, "first": True}),
                    ("second", {"nested": {"right": 2}, "second": True}),
                    ("ignored", "not-an-object"),
                ],
                "",
                {"nested": {"left": 1, "right": 2}, "first": True, "second": True},
            ),
            ("unknown", [("first", 1)], "", {"first": 1}),
        ],
    )
    async def test_aggregator_modes_resolve_current_node_shape(
        self, mode, variables, separator, expected
    ):
        from app.services.workflow.executors.variable import (
            VariableAggregatorNodeExecutor,
        )

        context = VariableExecutionContext(
            {f"{{{{{key}}}}}": value for key, value in variables}
        )
        result = await VariableAggregatorNodeExecutor().execute(
            {
                "data": {
                    "variableAggregatorConfig": {
                        "mode": mode,
                        "separator": separator,
                        "outputVariable": "combined",
                        "variables": [
                            {
                                "id": f"id-{key}",
                                "targetKey": key,
                                "sourceVariable": f"{{{{{key}}}}}",
                            }
                            for key, _ in variables
                        ],
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.success
        assert result.outputs == {"combined": expected}

    def test_variable_executor_output_declarations(self):
        from app.services.workflow.executors.variable import (
            VariableAggregatorNodeExecutor,
            VariableAssignmentNodeExecutor,
        )

        assert VariableAssignmentNodeExecutor().get_output_variables(
            {"assignments": [{"name": "value"}, {"targetVariable": "ignored"}]}
        ) == [{"name": "value", "type": "any"}]
        assert (
            VariableAssignmentNodeExecutor()
            .get_output_specs({"assignments": [{"name": "value"}]})[0]
            .type.kind
            == "any"
        )
        assert VariableAggregatorNodeExecutor().get_output_variables(
            {"mode": "merge", "outputVariable": "combined"}
        ) == [{"name": "combined", "type": "object"}]
        assert (
            VariableAggregatorNodeExecutor()
            .get_output_specs({"mode": "concat", "outputVariable": "combined"})[0]
            .type.kind
            == "string"
        )

    def test_aggregator_deep_merge_overwrites_non_matching_values(self):
        from app.services.workflow.executors.variable import (
            VariableAggregatorNodeExecutor,
        )

        assert VariableAggregatorNodeExecutor()._deep_merge(
            {"nested": {"keep": 1}, "replace": 1},
            {"nested": {"add": 2}, "replace": {"now": "object"}},
        ) == {"nested": {"keep": 1, "add": 2}, "replace": {"now": "object"}}

