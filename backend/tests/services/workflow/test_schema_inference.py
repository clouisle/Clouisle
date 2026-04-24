"""Tests for the debug-run schema inference + workflow definition merge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.workflow.schema_inference import (
    infer_run_schemas,
    merge_into_definition,
)


@dataclass
class _FakeExecution:
    node_id: str
    outputs: dict[str, Any] | None


class TestInferRunSchemas:
    def test_single_node_outputs_become_field_specs(self):
        execs = [
            _FakeExecution(
                "code-1",
                {"items": [{"id": 1, "name": "x"}], "count": 1},
            )
        ]
        result = infer_run_schemas(execs)
        assert set(result.keys()) == {"code-1"}
        items_spec = result["code-1"]["items"]
        assert items_spec.kind == "array"
        assert items_spec.item is not None and items_spec.item.kind == "object"
        assert items_spec.item.fields is not None
        assert set(items_spec.item.fields) == {"id", "name"}
        assert result["code-1"]["count"].kind == "number"

    def test_multiple_executions_for_same_node_union_merge(self):
        execs = [
            _FakeExecution("iter-1", {"item": {"a": 1}}),
            _FakeExecution("iter-1", {"item": {"a": 2, "b": "x"}}),
        ]
        result = infer_run_schemas(execs)
        item = result["iter-1"]["item"]
        assert item.kind == "object"
        assert item.fields is not None
        assert set(item.fields) == {"a", "b"}
        # 'b' was missing in the first iteration -> nullable
        assert item.fields["b"].nullable is True

    def test_internal_underscore_keys_skipped(self):
        execs = [
            _FakeExecution(
                "iter-1",
                {
                    "item": "hi",
                    "_iteration_state": {"index": 1},
                    "_iteration_complete": False,
                },
            )
        ]
        result = infer_run_schemas(execs)
        assert set(result["iter-1"].keys()) == {"item"}

    def test_skips_executions_without_outputs(self):
        execs = [
            _FakeExecution("a", None),
            _FakeExecution("b", {"x": 1}),
        ]
        result = infer_run_schemas(execs)
        assert set(result.keys()) == {"b"}


class TestMergeIntoDefinition:
    def _def(self, *nodes: dict) -> dict:
        return {"nodes": list(nodes), "edges": []}

    def test_writes_inferred_schema_onto_matching_node(self):
        execs = [_FakeExecution("code-1", {"v": 1})]
        inferred = infer_run_schemas(execs)
        defn = self._def({"id": "code-1", "data": {"label": "x"}})
        out = merge_into_definition(defn, inferred)
        node = out["nodes"][0]
        assert node["data"]["label"] == "x"
        schema = node["data"]["inferredSchema"]
        assert "v" in schema
        assert schema["v"]["kind"] == "number"
        assert schema["v"]["source"] == "inferred"

    def test_unrelated_nodes_left_untouched(self):
        execs = [_FakeExecution("code-1", {"v": 1})]
        inferred = infer_run_schemas(execs)
        defn = self._def(
            {"id": "code-1", "data": {}},
            {"id": "other", "data": {"k": "keep"}},
        )
        out = merge_into_definition(defn, inferred)
        assert out["nodes"][1]["data"] == {"k": "keep"}

    def test_existing_inferred_schema_union_merged(self):
        # First debug run: only field 'a' seen
        execs1 = [_FakeExecution("c", {"obj": {"a": 1}})]
        inferred1 = infer_run_schemas(execs1)
        defn1 = self._def({"id": "c", "data": {}})
        defn2 = merge_into_definition(defn1, inferred1)
        # Second debug run: only field 'b' seen
        execs2 = [_FakeExecution("c", {"obj": {"b": "x"}})]
        inferred2 = infer_run_schemas(execs2)
        defn3 = merge_into_definition(defn2, inferred2)
        schema = defn3["nodes"][0]["data"]["inferredSchema"]
        obj = schema["obj"]
        assert obj["kind"] == "object"
        assert set(obj["fields"].keys()) == {"a", "b"}
        # both seen on only one of the two runs -> nullable in the merged view
        assert obj["fields"]["a"]["nullable"] is True
        assert obj["fields"]["b"]["nullable"] is True

    def test_no_executions_returns_definition_unchanged(self):
        defn = self._def({"id": "c", "data": {}})
        out = merge_into_definition(defn, {})
        assert out["nodes"][0]["data"] == {}

    def test_handles_missing_nodes_key_gracefully(self):
        out = merge_into_definition({}, {"c": {"v": _spec("number")}})
        assert out == {}

    def test_handles_node_id_not_in_inferred(self):
        defn = self._def({"id": "c", "data": {}})
        out = merge_into_definition(defn, {"other": {"v": _spec("number")}})
        assert "inferredSchema" not in out["nodes"][0]["data"]


def _spec(kind: str):
    from app.services.workflow.types import TypeSpec

    return TypeSpec(kind=kind)  # type: ignore[arg-type]
