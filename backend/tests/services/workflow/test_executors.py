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

    @pytest.mark.asyncio
    async def test_top_level_condition_reference_selects_branch(self):
        node = {
            "id": "condition_1",
            "data": {
                "conditionConfig": {
                    "conditions": [
                        {
                            "id": "score_high",
                            "variable": "{{score}}",
                            "operator": "greater_than",
                            "value": 50,
                        }
                    ],
                    "branches": [
                        {"id": "high", "conditions": ["score_high"]},
                        {"id": "else", "isDefault": True},
                    ],
                }
            },
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=75)
        context.set_branch = AsyncMock()

        result = await ConditionNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {
            "matched_branch": "high",
            "condition_results": {"score_high": True},
        }
        assert result.next_handles == ["high"]
        context.set_branch.assert_awaited_once_with("condition_1", "high")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("branches", "expected_branch"),
        [
            ([{"id": "fallback", "type": "else"}], "fallback"),
            ([], "else"),
        ],
    )
    async def test_uses_default_or_implicit_fallback(self, branches, expected_branch):
        context = MagicMock()
        context.set_branch = AsyncMock()

        result = await ConditionNodeExecutor().execute(
            {"id": "condition_1", "data": {"branches": branches}},
            context,
            MagicMock(),
        )

        assert result.next_handles == [expected_branch]
        context.set_branch.assert_awaited_once_with("condition_1", expected_branch)

    @pytest.mark.asyncio
    async def test_resolves_comparison_value_reference(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(side_effect=[10, 10])

        result = await ConditionNodeExecutor()._evaluate_condition(
            {
                "variable": "{{source.value}}",
                "operator": "equals",
                "value": "{{other.value}}",
            },
            context,
        )

        assert result is True
        assert context.resolve_variable_ref.await_args_list == [
            (("{{source.value}}",), {}),
            (("{{other.value}}",), {}),
        ]

    @pytest.mark.asyncio
    async def test_unknown_operator_defaults_to_equals(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value="same")

        result = await ConditionNodeExecutor()._evaluate_condition(
            {"variable": "{{value}}", "operator": "unknown", "value": "same"},
            context,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_operator_type_error_returns_false(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value="not-a-number")

        result = await ConditionNodeExecutor()._evaluate_condition(
            {"variable": "{{value}}", "operator": "greater_than", "value": 1},
            context,
        )

        assert result is False


class TestCodeExecutor:
    @pytest.mark.asyncio
    async def test_resolves_inputs_and_returns_mapping(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value="search")
        node = {
            "data": {
                "codeConfig": {
                    "code": "def main(inputs): return inputs",
                    "inputs": [
                        {"name": "query", "variableRef": "{{start.query}}"},
                        {"name": "limit", "source": "constant", "constantValue": 3},
                    ],
                }
            }
        }

        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job_1", success=True, result={"answer": "ok"}
                )
            ),
        ) as submit_and_wait:
            result = await CodeNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"answer": "ok"}
        context.resolve_variable_ref.assert_awaited_once_with("{{start.query}}")
        assert submit_and_wait.await_args.args[0].metadata["params"] == {
            "query": "search",
            "limit": 3,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("sandbox_output", "expected"),
        [(None, {"result": None}), (7, {"result": 7})],
    )
    async def test_wraps_non_mapping_sandbox_outputs(self, sandbox_output, expected):
        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job_1", success=True, result=sandbox_output
                )
            ),
        ):
            result = await CodeNodeExecutor().execute(
                {"data": {"codeConfig": {"code": "def main(inputs): return None"}}},
                MagicMock(),
                MagicMock(),
            )

        assert result.outputs == expected

    @pytest.mark.asyncio
    async def test_translates_sandbox_failure(self):
        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job_1", success=False, error="code_execution_failed"
                )
            ),
        ):
            result = await CodeNodeExecutor().execute(
                {"data": {"codeConfig": {"code": "def main(inputs): return 1"}}},
                MagicMock(),
                MagicMock(),
            )

        assert not result.success
        assert result.error

    @pytest.mark.asyncio
    async def test_rejects_missing_code(self):
        result = await CodeNodeExecutor().execute(
            {"data": {"codeConfig": {}}}, MagicMock(), MagicMock()
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
            ("wrong", {"value": 1}, "wrong{'value': 1}"),
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

    @pytest.mark.asyncio
    async def test_parameter_extractor_rejects_missing_source_value(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value=None)

        result = await ParameterExtractorNodeExecutor().execute(
            {
                "data": {
                    "parameterExtractorConfig": {
                        "sourceVariable": "{{start.payload}}",
                        "extractionMethod": "regex",
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.error == "validation_error"

    @pytest.mark.asyncio
    async def test_parameter_extractor_regex_converts_matches_and_defaults(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(
            return_value="quantity=12 active=yes tags=red tags=blue"
        )
        result = await ParameterExtractorNodeExecutor().execute(
            {
                "data": {
                    "config": {
                        "sourceVariable": "{{payload}}",
                        "extractionMethod": "regex",
                        "parameters": [
                            {
                                "name": "quantity",
                                "pattern": r"quantity=(\d+)",
                                "type": "number",
                            },
                            {
                                "name": "active",
                                "pattern": r"active=(\w+)",
                                "type": "boolean",
                            },
                            {
                                "name": "tags",
                                "pattern": r"tags=(\w+)",
                                "type": "array",
                            },
                            {
                                "name": "missing",
                                "pattern": r"missing=(\w+)",
                                "type": "object",
                                "defaultValue": '{"fallback": true}',
                            },
                            {"name": "optional", "pattern": "absent"},
                            {"name": "ignored"},
                        ],
                    }
                }
            },
            context,
            MagicMock(),
        )

        assert result.outputs == {
            "quantity": 12,
            "active": True,
            "tags": ["red", "blue"],
            "missing": {"fallback": True},
            "optional": None,
            "_extraction_method": "regex",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "parameter",
        [
            {"name": "required", "pattern": "absent", "required": True},
            {"name": "required", "pattern": "[", "required": True},
        ],
    )
    async def test_parameter_extractor_regex_rejects_required_failures(self, parameter):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        result = await ParameterExtractorNodeExecutor()._extract_with_regex(
            "input", [parameter]
        )

        assert result.error == "validation_error"

    @pytest.mark.asyncio
    async def test_parameter_extractor_jsonpath_handles_matches_and_boundaries(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        executor = ParameterExtractorNodeExecutor()
        result = await executor._extract_with_jsonpath(
            {"users": [{"name": "Ada"}, {"name": "Lin"}]},
            [
                {
                    "name": "names",
                    "jsonPath": "$.users[*].name",
                    "type": "array",
                },
                {
                    "name": "limit",
                    "jsonPath": "$.limit",
                    "type": "number",
                    "defaultValue": "2.5",
                },
                {"name": "optional", "jsonPath": "$.optional"},
                {"jsonPath": "$.ignored"},
            ],
        )
        invalid_input = await executor._extract_with_jsonpath("{}", [])
        required_missing = await executor._extract_with_jsonpath(
            {}, [{"name": "value", "jsonPath": "$.value", "required": True}]
        )
        invalid_optional = await executor._extract_with_jsonpath(
            {},
            [
                {
                    "name": "fallback",
                    "jsonPath": "$.[",
                    "type": "array",
                    "defaultValue": "not-json",
                }
            ],
        )

        assert result.outputs == {
            "names": ["Ada", "Lin"],
            "limit": 2.5,
            "optional": None,
            "_extraction_method": "json_path",
        }
        assert invalid_input.error == "validation_error"
        assert required_missing.error == "validation_error"
        assert invalid_optional.outputs == {
            "fallback": "not-json",
            "_extraction_method": "json_path",
        }

    @pytest.mark.asyncio
    async def test_parameter_extractor_llm_requires_a_model(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        result = await ParameterExtractorNodeExecutor()._extract_with_llm(
            "input", [], {}, MagicMock()
        )

        assert result.error == "validation_error"

    @pytest.mark.asyncio
    async def test_parameter_extractor_llm_parses_response_and_required_values(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        team_model = MagicMock()
        team_model.model.id = "model-1"
        query = MagicMock()
        query.prefetch_related.return_value.first = AsyncMock(return_value=team_model)
        chat_result = MagicMock(content='Result: {"date": "2026-07-19"}')

        with (
            patch("app.models.model.TeamModel.filter", return_value=query),
            patch("app.models.model.Model.filter") as model_filter,
            patch(
                "app.llm.model_manager.chat", new=AsyncMock(return_value=chat_result)
            ) as chat,
        ):
            result = await ParameterExtractorNodeExecutor()._extract_with_llm(
                {"text": "July 19"},
                [
                    {"name": "date", "required": True},
                    {"name": "location", "required": False},
                    {},
                ],
                {"modelId": "team-model-1", "systemPrompt": "Extract values"},
                MagicMock(),
            )

        assert result.outputs == {
            "date": "2026-07-19",
            "location": None,
            "_extraction_method": "llm",
            "_extraction_confidence": 0.9,
        }
        model_filter.assert_not_called()
        assert chat.await_args.kwargs["model_id"] == "model-1"
        assert chat.await_args.kwargs["messages"][1]["content"] == '{"text": "July 19"}'

    @pytest.mark.asyncio
    async def test_parameter_extractor_llm_handles_model_and_response_errors(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        missing_query = MagicMock()
        missing_query.prefetch_related.return_value.first = AsyncMock(return_value=None)
        direct_model_query = MagicMock()
        direct_model_query.first = AsyncMock(return_value=None)

        with (
            patch("app.models.model.TeamModel.filter", return_value=missing_query),
            patch("app.models.model.Model.filter", return_value=direct_model_query),
        ):
            missing_model = await ParameterExtractorNodeExecutor()._extract_with_llm(
                "input", [], {"modelId": "missing"}, MagicMock()
            )

        model = MagicMock(id="model-1")
        direct_model_query.first.return_value = model
        with (
            patch("app.models.model.TeamModel.filter", return_value=missing_query),
            patch("app.models.model.Model.filter", return_value=direct_model_query),
            patch(
                "app.llm.model_manager.chat",
                new=AsyncMock(return_value=MagicMock(content="not-json")),
            ),
        ):
            invalid_json = await ParameterExtractorNodeExecutor()._extract_with_llm(
                "input", [], {"modelId": "model-1"}, MagicMock()
            )

        with (
            patch("app.models.model.TeamModel.filter", return_value=missing_query),
            patch("app.models.model.Model.filter", return_value=direct_model_query),
            patch(
                "app.llm.model_manager.chat",
                new=AsyncMock(side_effect=RuntimeError("provider failed")),
            ),
            patch(
                "app.services.workflow.executors.variable.translate_public_workflow_error",
                return_value="workflow_execution_error",
            ),
        ):
            provider_error = await ParameterExtractorNodeExecutor()._extract_with_llm(
                "input", [], {"modelId": "model-1"}, MagicMock()
            )

        assert missing_model.error == "model_not_found"
        assert invalid_json.error == "workflow_execution_error"
        assert provider_error.error == "workflow_execution_error"

    def test_parameter_extractor_value_and_output_declarations(self):
        from app.services.workflow.executors.variable import (
            ParameterExtractorNodeExecutor,
        )

        executor = ParameterExtractorNodeExecutor()

        assert executor._parse_default_value("false", "boolean") is False
        assert executor._parse_default_value("3", "number") == 3
        assert executor._convert_value("3.5", "number") == 3.5
        assert executor._convert_value("invalid", "number") == "invalid"
        assert executor._convert_value("yes", "boolean") is True
        assert executor.get_output_variables(
            {"parameters": [{"name": "count", "type": "number"}, {}]}
        ) == [
            {"name": "count", "type": "number"},
            {"name": "_extraction_confidence", "type": "number"},
        ]
        specs = executor.get_output_specs(
            {
                "parameters": [
                    {
                        "name": "items",
                        "typeSpec": {"kind": "array", "item": {"kind": "string"}},
                        "description": "Extracted items",
                    },
                    {"name": "count", "type": "number"},
                    {"name": ""},
                    "ignored",
                ]
            }
        )
        assert [(spec.name, spec.type.kind) for spec in specs] == [
            ("items", "array"),
            ("count", "number"),
            ("_extraction_confidence", "number"),
        ]
        assert specs[0].description == "Extracted items"
