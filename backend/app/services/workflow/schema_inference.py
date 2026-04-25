"""
Per-node output schema inference for debug runs.

Workflow:
    1. After a debug run completes, read its NodeExecution rows.
    2. For each row, infer a TypeSpec for every output value the node produced.
    3. Union-merge those specs with the schema already stored on the matching
       node in the workflow definition (`data.inferredSchema`).
    4. Persist the updated definition.

The result is consumed by the frontend variable picker / schema UI to give
field-level autocomplete after a single debug run, without forcing the user
to declare schemas by hand.

Inference is intentionally `source="inferred"`, never `"declared"`, so a
user-set schema is never silently overwritten.
"""

from __future__ import annotations

import logging
from uuid import UUID

from .types import TypeSpec, infer_type_spec, merge_type_spec

logger = logging.getLogger(__name__)


# Node output keys starting with "_" are internal markers (e.g. _iteration_state,
# _loop_complete) that downstream nodes never reference. Skip them so the
# inferred schema stays focused on user-visible fields.
def _is_user_visible(key: str) -> bool:
    return not key.startswith("_")


def infer_run_schemas(
    node_executions: list,
) -> dict[str, dict[str, TypeSpec]]:
    """Build {node_id: {output_name: TypeSpec}} from a run's NodeExecution rows.

    Multiple rows for the same `node_id` (iteration / loop bodies that fire
    once per item) get their per-output specs union-merged so the resulting
    schema reflects the true variability seen during the run.
    """
    by_node: dict[str, dict[str, TypeSpec]] = {}
    for execution in node_executions:
        outputs = getattr(execution, "outputs", None)
        node_id = getattr(execution, "node_id", None)
        if not node_id or not isinstance(outputs, dict):
            continue
        bucket = by_node.setdefault(str(node_id), {})
        for name, value in outputs.items():
            if not _is_user_visible(str(name)):
                continue
            new_spec = infer_type_spec(value)
            existing = bucket.get(name)
            bucket[name] = (
                merge_type_spec(existing, new_spec)
                if existing is not None
                else new_spec
            )
    return by_node


def _spec_to_dict(spec: TypeSpec) -> dict:
    return spec.model_dump(exclude_none=True)


def _dict_to_spec(raw: dict | None) -> TypeSpec | None:
    if not isinstance(raw, dict):
        return None
    try:
        return TypeSpec.model_validate(raw)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Discarding invalid stored TypeSpec: {exc}")
        return None


def merge_into_definition(
    definition: dict,
    inferred: dict[str, dict[str, TypeSpec]],
) -> dict:
    """Return a new definition with each node's `data.inferredSchema` union-merged.

    Pure function — does not touch the database. Stage 4's orchestrator hook
    composes this with a workflow read/write to persist.
    """
    if not isinstance(definition, dict):
        return definition

    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        return definition

    new_nodes: list = []
    for node in nodes:
        if not isinstance(node, dict):
            new_nodes.append(node)
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or node_id not in inferred:
            new_nodes.append(node)
            continue

        data = dict(node.get("data") or {})
        existing_raw = data.get("inferredSchema") or {}
        merged: dict = {}

        keys = set(existing_raw.keys()) | set(inferred[node_id].keys())
        for key in keys:
            old_spec = _dict_to_spec(existing_raw.get(key))
            new_spec = inferred[node_id].get(key)
            combined = merge_type_spec(old_spec, new_spec)
            merged[key] = _spec_to_dict(combined)

        data["inferredSchema"] = merged
        new_node = dict(node)
        new_node["data"] = data
        new_nodes.append(new_node)

    new_definition = dict(definition)
    new_definition["nodes"] = new_nodes
    return new_definition


async def merge_run_into_workflow(
    workflow_id: UUID | str,
    node_executions: list,
) -> None:
    """End-to-end: infer schemas from a run's NodeExecutions and persist them
    onto the workflow definition.

    Tolerant of failures — schema inference must never break a successful run.
    """
    inferred = infer_run_schemas(node_executions)
    if not inferred:
        return

    try:
        from app.models.workflow import Workflow

        workflow = await Workflow.filter(id=workflow_id).first()
        if workflow is None:
            logger.debug(
                f"Skip schema merge: workflow {workflow_id} not found at run completion"
            )
            return
        new_def = merge_into_definition(workflow.definition or {}, inferred)
        if new_def is workflow.definition:
            return
        workflow.definition = new_def
        await workflow.save(update_fields=["definition", "updated_at"])
        logger.info(
            f"Updated inferredSchema for {len(inferred)} node(s) on workflow {workflow_id}"
        )
    except Exception as exc:  # pragma: no cover - logged, never raised
        logger.warning(f"Schema inference merge failed for {workflow_id}: {exc}")


__all__ = [
    "infer_run_schemas",
    "merge_into_definition",
    "merge_run_into_workflow",
]
