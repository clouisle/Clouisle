"""Tests for the workflow TypeSpec system."""

from __future__ import annotations

import pytest

from app.services.workflow.types import (
    TypeSpec,
    infer_type_spec,
    merge_type_spec,
    to_text,
)


class TestInferTypeSpec:
    def test_infer_primitives(self):
        assert infer_type_spec("hi").kind == "string"
        assert infer_type_spec(1).kind == "number"
        assert infer_type_spec(1.5).kind == "number"
        assert infer_type_spec(True).kind == "boolean"
        spec = infer_type_spec(None)
        assert spec.kind == "null"
        assert spec.nullable is True

    def test_infer_object_fields(self):
        spec = infer_type_spec({"a": 1, "b": "x"})
        assert spec.kind == "object"
        assert spec.fields is not None
        assert spec.fields["a"].kind == "number"
        assert spec.fields["b"].kind == "string"

    def test_infer_empty_object_has_no_fields(self):
        spec = infer_type_spec({})
        assert spec.kind == "object"
        assert spec.fields is None

    def test_infer_homogeneous_array(self):
        spec = infer_type_spec([{"a": 1}, {"a": 2}])
        assert spec.kind == "array"
        assert spec.item is not None
        assert spec.item.kind == "object"
        assert spec.item.fields is not None
        assert spec.item.fields["a"].kind == "number"

    def test_infer_heterogeneous_array_collapses_to_any(self):
        spec = infer_type_spec([1, "x"])
        assert spec.kind == "array"
        assert spec.item is not None
        assert spec.item.kind == "any"

    def test_infer_empty_array_has_no_item(self):
        spec = infer_type_spec([])
        assert spec.kind == "array"
        assert spec.item is None

    def test_string_sample_truncated(self):
        spec = infer_type_spec("x" * 500)
        assert spec.kind == "string"
        assert spec.sample is not None
        assert len(spec.sample) <= 210


class TestMergeTypeSpec:
    def test_merge_same_primitive(self):
        a = TypeSpec(kind="string", source="inferred")
        b = TypeSpec(kind="string", source="inferred")
        merged = merge_type_spec(a, b)
        assert merged.kind == "string"

    def test_merge_with_null_marks_nullable(self):
        a = TypeSpec(kind="string", source="inferred")
        b = TypeSpec(kind="null", source="inferred", nullable=True)
        merged = merge_type_spec(a, b)
        assert merged.kind == "string"
        assert merged.nullable is True

    def test_merge_different_kinds_collapses_to_any(self):
        a = TypeSpec(kind="string", source="inferred")
        b = TypeSpec(kind="number", source="inferred")
        merged = merge_type_spec(a, b)
        assert merged.kind == "any"

    def test_merge_object_takes_field_union(self):
        a = infer_type_spec({"a": 1, "b": "x"})
        b = infer_type_spec({"b": "y", "c": True})
        merged = merge_type_spec(a, b)
        assert merged.kind == "object"
        assert merged.fields is not None
        assert set(merged.fields.keys()) == {"a", "b", "c"}
        # 'a' only in left and 'c' only in right -> nullable
        assert merged.fields["a"].nullable is True
        assert merged.fields["c"].nullable is True
        # 'b' present in both, both string -> not forced nullable
        assert merged.fields["b"].kind == "string"
        assert merged.fields["b"].nullable is False

    def test_merge_array_recurses_into_item(self):
        a = infer_type_spec([{"a": 1}])
        b = infer_type_spec([{"a": 2, "b": "x"}])
        merged = merge_type_spec(a, b)
        assert merged.kind == "array"
        assert merged.item is not None and merged.item.kind == "object"
        assert merged.item.fields is not None
        assert set(merged.item.fields.keys()) == {"a", "b"}
        assert merged.item.fields["b"].nullable is True

    def test_merge_handles_none(self):
        spec = TypeSpec(kind="string", source="declared")
        assert merge_type_spec(None, spec) is spec
        assert merge_type_spec(spec, None) is spec
        assert merge_type_spec(None, None).kind == "any"

    def test_declared_source_kept_only_when_both_declared(self):
        a = TypeSpec(kind="string", source="declared")
        b = TypeSpec(kind="string", source="declared")
        assert merge_type_spec(a, b).source == "declared"
        c = TypeSpec(kind="string", source="inferred")
        assert merge_type_spec(a, c).source == "inferred"


class TestToText:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, ""),
            ("", ""),
            ("hi", "hi"),
            (1, "1"),
            (1.5, "1.5"),
            (True, "True"),
        ],
    )
    def test_scalars(self, value, expected):
        assert to_text(value) == expected

    def test_dict_renders_as_json(self):
        assert to_text({"a": 1}) == '{"a": 1}'

    def test_list_renders_as_json(self):
        assert to_text([1, "x", {"a": 2}]) == '[1, "x", {"a": 2}]'

    def test_chinese_not_escaped(self):
        assert to_text({"name": "张三"}) == '{"name": "张三"}'
