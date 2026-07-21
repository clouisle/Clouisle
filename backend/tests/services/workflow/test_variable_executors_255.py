"""Focused coverage for workflow variable executors (issue #255)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.workflow.executors.variable import (
    ParameterExtractorNodeExecutor,
    VariableAggregatorNodeExecutor,
    VariableAssignmentNodeExecutor,
)


class MemoryContext:
    def __init__(self) -> None:
        self.variables = {}
        self.node_outputs = {}
        self.references = {}

    async def resolve_variable_ref(self, reference):
        return self.references.get(reference)

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


@pytest.mark.asyncio
async def test_assignment_operations_and_global_updates():
    context = MemoryContext()
    context.variables.update(text="old", count=3, mapping={"old": 1}, incompatible=True)
    context.references.update(
        {
            "{{source}}": "new",
            "{{suffix}}": "!",
            "{{amount}}": 2,
            "{{mapping}}": {"new": 2},
            "{{item}}": "entry",
            "{{other}}": 4,
        }
    )
    context.node_outputs["start"] = {"text": "old", "untouched": True}
    assignments = [
        {"targetVariable": "conversation.text", "variableRef": "{{source}}"},
        {
            "targetVariable": "conversation.text",
            "operation": "append",
            "variableRef": "{{suffix}}",
        },
        {
            "targetVariable": "count",
            "operation": "append",
            "variableRef": "{{amount}}",
        },
        {
            "targetVariable": "mapping",
            "operation": "append",
            "variableRef": "{{mapping}}",
        },
        {
            "targetVariable": "missing",
            "operation": "append",
            "variableRef": "{{item}}",
        },
        {
            "targetVariable": "incompatible",
            "operation": "append",
            "variableRef": "{{other}}",
        },
        {"targetVariable": "constant", "operation": "set", "constantValue": 0},
        {"targetVariable": "cleared", "operation": "clear"},
        {"targetVariable": "unknown", "operation": "unsupported"},
        {"targetVariable": ""},
    ]

    result = await VariableAssignmentNodeExecutor().execute(
        {
            "id": "assign",
            "data": {"variableAssignmentConfig": {"assignments": assignments}},
        },
        context,
        object(),
    )

    assert result.outputs == {
        "text": "new!",
        "count": 5,
        "mapping": {"old": 1, "new": 2},
        "missing": ["entry"],
        "incompatible": 5,
        "constant": 0,
        "cleared": None,
        "unknown": None,
    }
    assert context.variables["conversation.count"] == 5
    assert context.node_outputs["start"] == {"text": "new!", "untouched": True}


@pytest.mark.asyncio
async def test_assignment_nested_node_paths_and_iteration_states():
    context = MemoryContext()
    context.references["{{items}}"] = [2, 3]
    context.node_outputs["outer.inner"] = {"results": [0]}
    context.variables.update(
        {
            "outer.inner._iteration_state": {"results": [1]},
            "outer.inner._loop_state": {"results": [9]},
        }
    )

    result = await VariableAssignmentNodeExecutor().execute(
        {
            "data": {
                "config": {
                    "assignments": [
                        {
                            "targetVariable": "outer.inner.results",
                            "operation": "append",
                            "variableRef": "{{items}}",
                        },
                        {
                            "targetVariable": "sys.status",
                            "operation": "set",
                            "constantValue": "ready",
                        },
                    ]
                }
            }
        },
        context,
        object(),
    )

    assert result.outputs == {"results": [1, 2, 3], "sys.status": "ready"}
    assert context.node_outputs["outer.inner"]["results"] == [1, 2, 3]
    assert context.variables["outer.inner._iteration_state"]["results"] == [1, 2, 3]
    assert context.variables["outer.inner._loop_state"]["results"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_assignment_node_output_fallback_and_empty_config():
    context = MemoryContext()
    context.references["{{item}}"] = "b"
    context.node_outputs["iteration"] = {"results": ["a"]}

    result = await VariableAssignmentNodeExecutor().execute(
        {
            "data": {
                "config": {
                    "assignments": [
                        {
                            "targetVariable": "iteration.results",
                            "operation": "append",
                            "variableRef": "{{item}}",
                        },
                        {
                            "targetVariable": "node.value",
                            "operation": "set",
                            "constantValue": "x",
                        },
                    ]
                }
            }
        },
        context,
        object(),
    )
    empty = await VariableAssignmentNodeExecutor().execute({}, context, object())

    assert result.outputs == {"results": ["a", "b"], "value": "x"}
    assert context.node_outputs["node"] == {"value": "x"}
    assert empty.outputs == {}


@pytest.mark.asyncio
async def test_assignment_node_path_without_outputs_and_sys_append():
    context = MemoryContext()
    context.references.update({"{{item}}": "first", "{{tail}}": " tail"})

    result = await VariableAssignmentNodeExecutor().execute(
        {
            "data": {
                "config": {
                    "assignments": [
                        {
                            "targetVariable": "iteration.results",
                            "operation": "append",
                            "variableRef": "{{item}}",
                        },
                        {
                            "targetVariable": "sys.status",
                            "operation": "append",
                            "variableRef": "{{tail}}",
                        },
                    ]
                }
            }
        },
        context,
        object(),
    )

    assert result.outputs == {"results": ["first"], "sys.status": [" tail"]}
    assert context.node_outputs["iteration"] == {"results": ["first"]}
    assert context.variables["conversation.sys.status"] == [" tail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "values", "expected"),
    [
        ("array", [1, None], [1, None]),
        ("object", [1, 2], {"left": 1, "right": 2}),
        ("concat", ["a", None], "a"),
        (
            "merge",
            [{"nested": {"left": 1}, "old": 0}, {"nested": {"right": 2}}, "skip"],
            {"nested": {"left": 1, "right": 2}, "old": 0},
        ),
        ("unsupported", [1, 2], {"left": 1, "right": 2}),
    ],
)
async def test_aggregator_modes(mode, values, expected):
    context = MemoryContext()
    variables = []
    for index, value in enumerate(values):
        reference = f"{{{{v{index}}}}}"
        context.references[reference] = value
        variables.append(
            {
                "id": "right" if index else "left",
                "sourceVariable": reference,
                **({"targetKey": f"item{index}"} if index > 1 else {}),
            }
        )

    result = await VariableAggregatorNodeExecutor().execute(
        {
            "data": {
                "variableAggregatorConfig": {
                    "mode": mode,
                    "variables": variables,
                    "outputVariable": "combined",
                    "separator": "|",
                }
            }
        },
        context,
        object(),
    )

    assert result.outputs == {"combined": expected}


def test_variable_output_declarations():
    assignment = VariableAssignmentNodeExecutor()
    config = {"assignments": [{"name": "kept"}, {"targetVariable": "ignored"}]}
    assert assignment.get_output_variables(config) == [{"name": "kept", "type": "any"}]
    assert assignment.get_output_specs(config)[0].type.kind == "any"

    aggregator = VariableAggregatorNodeExecutor()
    for mode, expected in [
        ("array", "array"),
        ("object", "object"),
        ("merge", "object"),
        ("concat", "string"),
    ]:
        assert aggregator.get_output_variables({"mode": mode})[0]["type"] == expected
        assert aggregator.get_output_specs({"mode": mode})[0].type.kind == expected


@pytest.mark.asyncio
async def test_parameter_extractor_validation_and_routing(monkeypatch):
    executor = ParameterExtractorNodeExecutor()
    context = MemoryContext()
    missing = await executor.execute(
        {"data": {"parameterExtractorConfig": {"sourceVariable": "{{missing}}"}}},
        context,
        object(),
    )
    assert missing.error == "validation_error"

    context.references["{{source}}"] = "input"
    executor._extract_with_regex = AsyncMock(return_value="regex-result")
    executor._extract_with_jsonpath = AsyncMock(return_value="json-result")
    executor._extract_with_llm = AsyncMock(return_value="llm-result")
    for method, expected in [
        ("regex", "regex-result"),
        ("json_path", "json-result"),
        ("llm", "llm-result"),
        ("other", "llm-result"),
    ]:
        result = await executor.execute(
            {
                "data": {
                    "config": {
                        "sourceVariable": "{{source}}",
                        "extractionMethod": method,
                        "parameters": [{"name": "value"}],
                    }
                }
            },
            context,
            object(),
        )
        assert result == expected

    class FakeQuery:
        def prefetch_related(self, name):
            assert name == "model"
            return self

        async def first(self):
            return SimpleNamespace(model=SimpleNamespace(id="model-id"))

    async def fake_chat(**kwargs):
        assert kwargs["model_id"] == "model-id"
        return SimpleNamespace(content='{"value": "ok", "missing": null}')

    monkeypatch.setattr(
        "app.models.model.TeamModel.filter",
        lambda **kwargs: FakeQuery(),
    )
    monkeypatch.setattr("app.llm.model_manager.chat", fake_chat)
    llm = await ParameterExtractorNodeExecutor()._extract_with_llm(
        "input",
        [{"name": "value", "required": True}, {"name": "missing"}],
        {"modelId": "team-model-id"},
        object(),
    )
    assert llm.outputs == {
        "value": "ok",
        "missing": None,
        "_extraction_method": "llm",
        "_extraction_confidence": 0.9,
    }


@pytest.mark.asyncio
async def test_parameter_extractor_llm_errors(monkeypatch):
    executor = ParameterExtractorNodeExecutor()
    assert (
        await executor._extract_with_llm("input", [], {}, object())
    ).error == "validation_error"

    class EmptyQuery:
        def prefetch_related(self, name):
            return self

        async def first(self):
            return None

    monkeypatch.setattr(
        "app.models.model.TeamModel.filter",
        lambda **kwargs: EmptyQuery(),
    )
    monkeypatch.setattr(
        "app.models.model.Model.filter",
        lambda **kwargs: EmptyQuery(),
    )
    assert (
        await executor._extract_with_llm(
            "input", [], {"modelId": "missing-model"}, object()
        )
    ).error == "model_not_found"

    class ModelQuery(EmptyQuery):
        async def first(self):
            return SimpleNamespace(id="model-id")

    monkeypatch.setattr(
        "app.models.model.Model.filter",
        lambda **kwargs: ModelQuery(),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.chat",
        AsyncMock(return_value=SimpleNamespace(content="not json")),
    )
    assert (
        await executor._extract_with_llm("input", [], {"modelId": "model-id"}, object())
    ).error == "workflow_execution_error"

    monkeypatch.setattr(
        "app.llm.model_manager.chat",
        AsyncMock(return_value=SimpleNamespace(content='{"required": null}')),
    )
    assert (
        await executor._extract_with_llm(
            "input",
            [{"name": "required", "required": True}],
            {"modelId": "model-id"},
            object(),
        )
    ).error == "validation_error"

    monkeypatch.setattr(
        "app.llm.model_manager.chat",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    assert (
        await executor._extract_with_llm("input", [], {"modelId": "model-id"}, object())
    ).error


@pytest.mark.asyncio
async def test_regex_extraction_types_defaults_missing_and_errors():
    result = await ParameterExtractorNodeExecutor()._extract_with_regex(
        "age=42 score=1.5 yes=yes tags=a tags=b pair=x-7",
        [
            {"name": "age", "pattern": r"age=(\d+)", "type": "number"},
            {"name": "score", "pattern": r"score=([\d.]+)", "type": "number"},
            {"name": "enabled", "pattern": r"yes=(\w+)", "type": "boolean"},
            {"name": "tags", "pattern": r"tags=(\w+)", "type": "array"},
            {"name": "pair", "pattern": r"pair=(\w+)-(\d+)", "type": "string"},
            {"name": "default", "pattern": r"absent=(\w+)", "defaultValue": "3"},
            {"name": "optional", "pattern": r"none=(\w+)"},
            {"name": "bad", "pattern": "[", "defaultValue": "true", "type": "boolean"},
            {"pattern": "ignored"},
        ],
    )
    required_missing = await ParameterExtractorNodeExecutor()._extract_with_regex(
        "", [{"name": "required", "pattern": "x", "required": True}]
    )
    required_bad_pattern = await ParameterExtractorNodeExecutor()._extract_with_regex(
        "", [{"name": "required", "pattern": "[", "required": True}]
    )

    assert result.outputs == {
        "age": 42,
        "score": 1.5,
        "enabled": True,
        "tags": ["a", "b"],
        "pair": "x",
        "default": "3",
        "optional": None,
        "bad": True,
        "_extraction_method": "regex",
    }
    assert required_missing.error == "validation_error"
    assert required_bad_pattern.error == "validation_error"


@pytest.mark.asyncio
async def test_jsonpath_extraction_nested_paths_defaults_and_errors():
    executor = ParameterExtractorNodeExecutor()
    result = await executor._extract_with_jsonpath(
        {"users": [{"name": "Ada"}, {"name": "Lin"}]},
        [
            {"name": "names", "jsonPath": "$.users[*].name", "type": "array"},
            {"name": "first", "jsonPath": "$.users[0].name"},
            {
                "name": "count",
                "jsonPath": "$.count",
                "defaultValue": "2",
                "type": "number",
            },
            {"name": "optional", "jsonPath": "$.missing"},
            {
                "name": "invalid",
                "jsonPath": "$.[",
                "defaultValue": "[]",
                "type": "array",
            },
            {"jsonPath": "$.ignored"},
        ],
    )
    wrong_type = await executor._extract_with_jsonpath("{}", [])
    required_missing = await executor._extract_with_jsonpath(
        {}, [{"name": "required", "jsonPath": "$.missing", "required": True}]
    )
    required_invalid = await executor._extract_with_jsonpath(
        {}, [{"name": "required", "jsonPath": "$.[", "required": True}]
    )

    assert result.outputs == {
        "names": ["Ada", "Lin"],
        "first": "Ada",
        "count": 2,
        "optional": None,
        "invalid": [],
        "_extraction_method": "json_path",
    }
    assert wrong_type.error == "validation_error"
    assert required_missing.error == "validation_error"
    assert required_invalid.error == "validation_error"


def test_parameter_value_conversion_and_output_specs():
    executor = ParameterExtractorNodeExecutor()
    assert executor._parse_default_value(None, "string") is None
    assert executor._parse_default_value("no", "boolean") is False
    assert executor._parse_default_value('{"a": 1}', "object") == {"a": 1}
    assert executor._parse_default_value("invalid", "array") == "invalid"
    assert executor._convert_value("invalid", "number") == "invalid"
    assert executor._convert_value("NO", "boolean") is False
    assert executor._convert_value("text", "string") == "text"

    config = {
        "parameters": [
            {"name": "plain", "type": "number", "description": "value"},
            {
                "name": "structured",
                "typeSpec": {"kind": "array", "item": {"kind": "string"}},
            },
            {"name": ""},
        ]
    }
    assert [item["name"] for item in executor.get_output_variables(config)] == [
        "plain",
        "structured",
        "_extraction_confidence",
    ]
    specs = executor.get_output_specs(config)
    assert [(spec.name, spec.type.kind) for spec in specs] == [
        ("plain", "number"),
        ("structured", "array"),
        ("_extraction_confidence", "number"),
    ]
