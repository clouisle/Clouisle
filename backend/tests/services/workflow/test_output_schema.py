"""Tests for NodeExecutor.get_output_specs across executors.

Validates the structural TypeSpec returned for each node type, including:
- the default fallback that lifts legacy `get_output_variables` dicts
- the richer overrides on llm / code / parameter_extractor
"""

from __future__ import annotations

import pytest

from app.services.workflow.executor import NodeExecutor
from app.services.workflow.executors.code import CodeNodeExecutor
from app.services.workflow.executors.condition import ConditionNodeExecutor
from app.services.workflow.executors.llm import LLMNodeExecutor
from app.services.workflow.executors.variable import ParameterExtractorNodeExecutor
from app.services.workflow.types import NodeOutputDecl, TypeSpec


class TestDefaultLegacyConversion:
    def test_default_lifts_string_type(self):
        class _E(NodeExecutor):
            async def execute(self, node, context, run):  # pragma: no cover
                raise NotImplementedError

            def get_output_variables(self, config):
                return [{"name": "out", "type": "string"}]

        decls = _E().get_output_specs({})
        assert decls == [NodeOutputDecl(name="out", type=TypeSpec(kind="string"))]

    def test_default_unknown_type_becomes_any(self):
        class _E(NodeExecutor):
            async def execute(self, node, context, run):  # pragma: no cover
                raise NotImplementedError

            def get_output_variables(self, config):
                return [{"name": "x", "type": "weird-thing"}]

        decls = _E().get_output_specs({})
        assert decls[0].type.kind == "any"

    def test_default_skips_entries_without_name(self):
        class _E(NodeExecutor):
            async def execute(self, node, context, run):  # pragma: no cover
                raise NotImplementedError

            def get_output_variables(self, config):
                return [{"type": "string"}, {"name": "ok", "type": "number"}]

        decls = _E().get_output_specs({})
        assert [d.name for d in decls] == ["ok"]

    def test_condition_returns_string_and_object_specs(self):
        decls = ConditionNodeExecutor().get_output_specs({})
        kinds = {d.name: d.type.kind for d in decls}
        assert kinds == {"matched_branch": "string", "condition_results": "object"}


class TestLLMOverride:
    def test_llm_outputs_response_reasoning_and_structured_usage(self):
        decls = LLMNodeExecutor().get_output_specs({})
        by_name = {d.name: d for d in decls}
        assert set(by_name) == {"response", "reasoning", "usage"}
        assert by_name["response"].type.kind == "string"
        assert by_name["reasoning"].type.kind == "string"
        usage = by_name["usage"].type
        assert usage.kind == "object"
        assert usage.fields is not None
        assert set(usage.fields) == {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }
        assert all(f.kind == "number" for f in usage.fields.values())


class TestCodeOverride:
    def test_code_default_when_outputs_missing(self):
        decls = CodeNodeExecutor().get_output_specs({})
        assert decls == [NodeOutputDecl(name="result", type=TypeSpec(kind="any"))]

    def test_code_legacy_type_string_translated(self):
        decls = CodeNodeExecutor().get_output_specs(
            {"outputs": [{"name": "n", "type": "number"}]}
        )
        assert decls[0].type == TypeSpec(kind="number")

    def test_code_user_declared_type_spec_honoured(self):
        spec = {
            "kind": "array",
            "item": {
                "kind": "object",
                "fields": {
                    "id": {"kind": "number"},
                    "name": {"kind": "string"},
                },
            },
        }
        decls = CodeNodeExecutor().get_output_specs(
            {"outputs": [{"name": "rows", "typeSpec": spec}]}
        )
        assert decls[0].type.kind == "array"
        assert decls[0].type.item is not None
        assert decls[0].type.item.kind == "object"
        assert decls[0].type.item.fields is not None
        assert set(decls[0].type.item.fields) == {"id", "name"}

    def test_code_skips_entries_without_name(self):
        decls = CodeNodeExecutor().get_output_specs(
            {"outputs": [{"type": "string"}, {"name": "ok", "type": "number"}]}
        )
        assert [d.name for d in decls] == ["ok"]


class TestParameterExtractorOverride:
    def test_parameters_become_decls_plus_confidence(self):
        config = {
            "parameters": [
                {"name": "date", "type": "string"},
                {"name": "count", "type": "number"},
            ]
        }
        decls = ParameterExtractorNodeExecutor().get_output_specs(config)
        names = [d.name for d in decls]
        assert names == ["date", "count", "_extraction_confidence"]
        kinds = {d.name: d.type.kind for d in decls}
        assert kinds == {
            "date": "string",
            "count": "number",
            "_extraction_confidence": "number",
        }

    def test_user_typeSpec_on_parameter_honoured(self):
        config = {
            "parameters": [
                {
                    "name": "items",
                    "typeSpec": {"kind": "array", "item": {"kind": "string"}},
                }
            ]
        }
        decls = ParameterExtractorNodeExecutor().get_output_specs(config)
        assert decls[0].type.kind == "array"
        assert decls[0].type.item is not None and decls[0].type.item.kind == "string"

    def test_empty_parameters_still_returns_confidence(self):
        decls = ParameterExtractorNodeExecutor().get_output_specs({"parameters": []})
        assert [d.name for d in decls] == ["_extraction_confidence"]
