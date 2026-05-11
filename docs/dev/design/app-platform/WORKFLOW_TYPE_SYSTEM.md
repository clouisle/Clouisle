# Workflow Type System

This document describes the type system that flows values between workflow
nodes, the on-disk and in-memory shapes involved, the schema-inference loop
that surfaces structural information from debug runs, and the rules that
govern when string conversion is allowed.

Implementation reference:
- Backend: `backend/app/services/workflow/types.py`,
  `backend/app/services/workflow/serialization.py`,
  `backend/app/services/workflow/schema_inference.py`
- Frontend: `frontend/lib/workflow/type-spec.ts`

---

## Goals

1. **Native type passthrough.** A `dict` produced by an upstream node arrives
   at a downstream node as a `dict`, not as the JSON string
   `"{'k': 'v'}"`. Lists, numbers, booleans, and nulls keep their identity.
2. **Single source of truth for "is this an array of objects?"** Editor
   autocomplete, prompt-hint generators, and runtime validators all read the
   same `TypeSpec`.
3. **Zero hand-written schemas required.** First-time users get useful
   field-level autocomplete after a single debug run via inferred TypeSpecs.
4. **No silent string ↔ object coercions.** The places that need text
   (template interpolation, LLM prompt assembly, the answer node) call a
   single helper and own that conversion explicitly.

---

## Value model

`WorkflowValue` is the recursive native type carried between nodes:

```python
WorkflowValue = (
    str | int | float | bool | None
    | list["WorkflowValue"]
    | dict[str, "WorkflowValue"]
)
```

This is the type signature of every node's `outputs` dict, every variable
written through `ExecutionContext.set_variable`, and every value resolved by
`ExecutionContext.resolve_variable_ref` for a single `{{node.field}}`
reference.

Non-native primitives crossing the serialization boundary are normalised to
JSON-friendly types: `datetime` / `date` → ISO string; `UUID` → string;
`Decimal` → float; `set` → list. Anything else fails fast at
`serialization.dumps_value` rather than producing silent garbage.

## Structural type description

`TypeSpec` describes the structure of a value without committing to an
external schema standard:

```python
class TypeSpec(BaseModel):
    kind: Literal["string", "number", "boolean", "object", "array",
                  "file", "image", "files", "images", "null", "any"]
    item: TypeSpec | None = None              # array element type
    fields: dict[str, TypeSpec] | None = None # object field types
    nullable: bool = False
    source: Literal["declared", "inferred"] = "declared"
    sample: Any | None = None                 # populated only on inference
```

The frontend mirrors this in `frontend/lib/workflow/type-spec.ts`.

JSON Schema was considered and rejected: too heavyweight for the editor UI
and gives more expressivity than the current rules need. `TypeSpec` covers
the cases that change autocomplete behaviour (object field set, array item
type) and degrades to `kind: "any"` whenever it can't be more specific.

### Helpers

- `infer_type_spec(value)` — best-effort recursive inference from a real
  runtime value. Used by the post-debug merger.
- `merge_type_spec(a, b)` — union merge: same kind recurses into fields and
  items; different kinds collapse to `any`; null on either side propagates
  `nullable`. Object fields seen on only one side become nullable in the
  merged view.
- `to_text(value)` — the only stringification helper allowed at text-only
  boundaries. dict / list render as JSON (UTF-8, `ensure_ascii=False`); None
  renders as the empty string; everything else delegates to `str()`.
- `legacy_type_to_spec(type_str)` — translates the historical "string" /
  "array" / "object" / etc. type strings into a flat `TypeSpec`. Used by the
  default `NodeExecutor.get_output_specs` and by frontend migration paths.

---

## Serialization

The Redis-backed `ExecutionContext` and the workflow `WorkflowCache`
serialize via msgpack rather than JSON. msgpack preserves native dict / list
/ scalar round-trip without forcing every value to be re-decoded by the
caller. Because the shared Redis pool runs with `decode_responses=True`,
msgpack bytes are wrapped in a base64 frame with the prefix `mp1:` so the
text-mode pool can carry them; `loads_value` rejects anything missing the
prefix so a botched migration surfaces immediately rather than silently
producing garbage.

What stays JSON:
- Stream events (SSE / Pub-Sub) — frontend consumers expect JSON.
- Celery task arguments — task params are simple dicts.
- Database `JSONField` columns (Tortoise ORM handles encoding).
- API responses — Pydantic dump.
- Answer-node final output — the displayed value is text by definition.

What never escapes JSON / Python repr:
- Variable interpolation (`resolve_variable_ref`, `resolve_template`) calls
  `to_text` for embedded values. A dict in the middle of a template renders
  as `{"k": "v"}`, not `{'k': 'v'}`.
- LLM prompt input concatenation in `executors/llm.py` calls `to_text` per
  field for the same reason.

---

## Per-node output declarations

Each `NodeExecutor` exposes `get_output_specs(config) -> list[NodeOutputDecl]`.

```python
class NodeOutputDecl(BaseModel):
    name: str
    type: TypeSpec
    description: str | None = None
```

The base class default lifts the legacy
`get_output_variables(config) -> list[dict]` through `legacy_type_to_spec`,
so executors that don't override `get_output_specs` keep working. Targeted
overrides (the only ones today):

- `LLMNodeExecutor` — fixed: `response: string`, `reasoning: string`,
  `usage: object{prompt_tokens, completion_tokens, total_tokens: number}`.
- `CodeNodeExecutor` — honours user-declared `typeSpec` on each output entry
  (set via the schema editor in the code-node config panel); falls back to
  the legacy type string.
- `ParameterExtractorNodeExecutor` — per-parameter `typeSpec` honoured;
  always emits a trailing `_extraction_confidence: number`.

Other executors stay on the auto-converted default; they can opt in
incrementally as their UIs gain richer schema editing.

---

## Schema inference loop

After a debug run completes, `_complete_run` in `orchestrator.py` calls
`schema_inference.merge_run_into_workflow(workflow_id, node_executions)`.

```
NodeExecution.outputs (real values)
    └──► infer_type_spec  (per-output recursive)
           └──► merge_type_spec across all rows of the same node_id
                 └──► union-merge with existing inferredSchema in
                      workflow.definition.nodes[].data.inferredSchema
```

Properties:
- **Debug only.** `WorkflowRun.is_debug` gates the merge so production
  traffic shape never drifts the editor schema.
- **Soft typing.** Inferred specs are tagged `source="inferred"` and the
  runtime never validates against them — they only feed UI affordances.
- **Internal field filter.** Output keys starting with `_`
  (`_iteration_state`, `_loop_complete`, `_iteration_index`, …) are filtered
  out so the editor schema reflects what downstream nodes can actually
  reference.
- **Best-effort.** Any failure during merge is logged and swallowed; the
  successful run never observes the inference work.

The frontend variable picker reads `node.data.inferredSchema` (alongside any
declared output spec on the node config) to render `array<object{id, name}>`
style labels and to grey out incompatible options when an input declares an
`acceptType`.

---

## Frontend wiring

- `frontend/lib/workflow/type-spec.ts` mirrors backend types and provides
  `legacyTypeToSpec`, `describeTypeSpec`, and `isAssignable`.
- `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/
  variable-selector.tsx` accepts an optional `acceptType: TypeSpec` prop;
  variables with a known `typeSpec` not assignable to it render greyed out
  (still selectable, with a tooltip explaining the mismatch). Variables
  without `typeSpec` info pass through unchanged.
- `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/
  type-spec-editor.tsx` is the recursive editor: kind picker (locked when
  invoked from a code-node output row), array item editor, object field
  editor with add / rename / remove.
- `frontend/app/(platform)/app/apps/workflow/[id]/_components/node-config/
  configs/code-node-config.tsx` mounts the editor inline when output type is
  object or array, and renders the `inferredSchema` as a read-only field
  list beneath.
- `frontend/app/(platform)/app/apps/workflow/[id]/_components/
  workflow-run-drawer.tsx` exposes `onDebugRunComplete`; the page calls
  `getWorkflow` and `setNodes` so the freshly inferred schema appears
  without a manual reload.

---

## Migration & versioning

Workflow definitions stamp `schema_version: int` (added in stage 8). The
hard cutover means:

- Definitions created before this work load with `schema_version` missing or
  < 2. The editor flags them and disables run; the user must re-save to opt
  in.
- Redis runtime state from the previous JSON-serialised era is incompatible
  with the new `mp1:`-framed format; `loads_value` raises `ValueError` on
  the old shape. Operators clear `workflow:run:*` and `wf:cache:*` at the
  cutover (helper script: `scripts/clear_workflow_runtime.py`).

---

## Testing

- `backend/tests/services/workflow/test_serialization.py` — round-trip,
  normalisation, framing.
- `backend/tests/services/workflow/test_types.py` — `infer_type_spec`,
  `merge_type_spec`, `to_text`.
- `backend/tests/services/workflow/test_native_passthrough.py` — end-to-end
  via a tiny in-memory async Redis stub: dict / list survive across
  `set_node_outputs` / `get_node_outputs`, single variable references
  return native values, embedded interpolation renders as JSON, branches
  round-trip as lists.
- `backend/tests/services/workflow/test_output_schema.py` — default
  legacy-type lift; LLM / code / parameter_extractor overrides; user
  `typeSpec` honoured.
- `backend/tests/services/workflow/test_schema_inference.py` — inference,
  union merge across iterations, read / write of `inferredSchema` on
  workflow definitions.
