"""
Workflow value type system.

Defines:
- WorkflowValue: the recursive native type carried between nodes
- TypeSpec: structural description of a workflow value (string/number/object{...}/array<T>/...)
- infer_type_spec / merge_type_spec: build TypeSpec from real values, union-merge two specs
- to_text: deterministic stringification used at the few points where text is required
  (template interpolation, prompt assembly, answer rendering)
"""

from __future__ import annotations

import json
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

WorkflowValue = Union[
    str,
    int,
    float,
    bool,
    None,
    list["WorkflowValue"],
    dict[str, "WorkflowValue"],
]

TypeKind = Literal[
    "string",
    "number",
    "boolean",
    "object",
    "array",
    "file",
    "image",
    "files",
    "images",
    "null",
    "any",
]


class TypeSpec(BaseModel):
    """Structural type description for a workflow variable.

    `kind` is the head; `item` describes array elements; `fields` describes object
    members. `source` distinguishes user-declared specs from debug-inferred ones,
    and `nullable` marks unions with null observed during inference.
    """

    model_config = ConfigDict(extra="forbid")

    kind: TypeKind
    item: TypeSpec | None = None
    fields: dict[str, TypeSpec] | None = None
    nullable: bool = False
    source: Literal["declared", "inferred"] = "declared"
    sample: Any | None = Field(default=None, exclude=False)


TypeSpec.model_rebuild()


_SAMPLE_STR_LIMIT = 200


def _trim_sample(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _SAMPLE_STR_LIMIT:
        return value[:_SAMPLE_STR_LIMIT] + "..."
    return value


def infer_type_spec(
    value: Any, *, source: Literal["inferred"] = "inferred"
) -> TypeSpec:
    """Best-effort recursive inference of a TypeSpec from a real runtime value.

    Heterogeneous arrays collapse to the union (merged) of element specs.
    Dicts produce object specs whose `fields` reflects the keys observed.
    """
    if value is None:
        return TypeSpec(kind="null", source=source, nullable=True)
    if isinstance(value, bool):
        return TypeSpec(kind="boolean", source=source, sample=value)
    if isinstance(value, (int, float)):
        return TypeSpec(kind="number", source=source, sample=value)
    if isinstance(value, str):
        return TypeSpec(kind="string", source=source, sample=_trim_sample(value))
    if isinstance(value, list):
        if not value:
            return TypeSpec(kind="array", source=source)
        item_spec = infer_type_spec(value[0], source=source)
        for item in value[1:]:
            item_spec = merge_type_spec(item_spec, infer_type_spec(item, source=source))
        return TypeSpec(kind="array", item=item_spec, source=source)
    if isinstance(value, dict):
        fields = {str(k): infer_type_spec(v, source=source) for k, v in value.items()}
        return TypeSpec(kind="object", fields=fields or None, source=source)
    return TypeSpec(kind="any", source=source)


def merge_type_spec(a: TypeSpec | None, b: TypeSpec | None) -> TypeSpec:
    """Union-merge two specs.

    Same kind: recurse into item / fields. Different kinds: collapse to `any`
    and propagate `nullable`. The result keeps the "weakest" source — declared
    wins over inferred only when both sides agree on kind.
    """
    if a is None and b is None:
        return TypeSpec(kind="any", source="inferred")
    if a is None:
        return b  # type: ignore[return-value]
    if b is None:
        return a

    nullable = a.nullable or b.nullable

    if a.kind == "null" and b.kind != "null":
        merged = b.model_copy(update={"nullable": True})
        return merged
    if b.kind == "null" and a.kind != "null":
        merged = a.model_copy(update={"nullable": True})
        return merged

    if a.kind != b.kind:
        return TypeSpec(kind="any", nullable=nullable, source="inferred")

    source: Literal["declared", "inferred"] = (
        "declared" if a.source == "declared" and b.source == "declared" else "inferred"
    )

    if a.kind == "array":
        return TypeSpec(
            kind="array",
            item=merge_type_spec(a.item, b.item) if (a.item or b.item) else None,
            nullable=nullable,
            source=source,
        )

    if a.kind == "object":
        fa = a.fields or {}
        fb = b.fields or {}
        keys = set(fa) | set(fb)
        fields = {k: merge_type_spec(fa.get(k), fb.get(k)) for k in keys}
        # Fields seen on only one side become nullable.
        for k in keys:
            if k not in fa or k not in fb:
                fields[k] = fields[k].model_copy(update={"nullable": True})
        return TypeSpec(
            kind="object",
            fields=fields or None,
            nullable=nullable,
            source=source,
        )

    return TypeSpec(kind=a.kind, nullable=nullable, source=source)


def to_text(value: Any) -> str:
    """Deterministic stringification for the text-only boundaries.

    - dict / list → JSON (ensure_ascii=False) so users see structure, not Python repr
    - None → "" (matches existing behaviour at insertion sites)
    - everything else → str(value)
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


__all__ = [
    "TypeSpec",
    "TypeKind",
    "WorkflowValue",
    "infer_type_spec",
    "merge_type_spec",
    "to_text",
]
