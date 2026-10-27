"""Trusted execution provenance for workflow runs.

``WorkflowRun.trigger_type`` mirrors the workflow's *configured* trigger, so it
cannot identify how a specific run started: a manual run of a cron-configured
workflow still reads ``cron``. Tool connection grants, however, are bound to the
entrypoint that actually invoked the run (workflow surface, API key, embed,
schedule), so provenance must be recorded by the trusted creation route and
never inferred from the configuration or from request input.

The origin lives in ``WorkflowRun.context_snapshot`` so it is durable across the
park/resume cycle and needs no schema migration. Resume keeps the snapshot, so a
run cannot change its surface part-way through. Workflow runs are
non-interactive for approval gates: a caller-confirmation gate can never be
satisfied here. A manual run (the ``workflow`` entrypoint) may still resolve the
triggering user's default or sole personal connection automatically, while
background origins (API key, embed, schedule, subworkflow) require an explicit
connection binding.

Only the backend stamps an origin. ``AgentRun`` origins are recorded by the
agent runtime with the same shape (see ``agent_run_worker``).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from uuid import UUID

from app.schemas.tool_approval import ExecutionEntrypoint

logger = logging.getLogger(__name__)

ORIGIN_SNAPSHOT_KEY = "execution_origin"
MAX_ENTRYPOINT_ID_LENGTH = 200

#: Entrypoints a workflow run may legitimately record. Anything else is treated
#: as a malformed snapshot and falls back to the workflow surface.
WORKFLOW_ORIGIN_ENTRYPOINTS: frozenset[ExecutionEntrypoint] = frozenset(
    {
        ExecutionEntrypoint.WORKFLOW,
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.SUBWORKFLOW,
    }
)


@dataclass(frozen=True, slots=True)
class WorkflowExecutionOrigin:
    """The entrypoint that actually started a workflow run."""

    entrypoint: ExecutionEntrypoint
    entrypoint_id: str

    def __post_init__(self) -> None:
        if self.entrypoint not in WORKFLOW_ORIGIN_ENTRYPOINTS:
            raise ValueError(f"unsupported workflow entrypoint: {self.entrypoint}")
        entrypoint_id = (self.entrypoint_id or "").strip()
        if not entrypoint_id:
            raise ValueError("workflow entrypoint_id is required")
        if len(entrypoint_id) > MAX_ENTRYPOINT_ID_LENGTH:
            raise ValueError("workflow entrypoint_id is too long")


def workflow_origin(workflow_id: UUID | str) -> WorkflowExecutionOrigin:
    """Origin for a run invoked through the workflow surface itself."""
    return WorkflowExecutionOrigin(ExecutionEntrypoint.WORKFLOW, str(workflow_id))


def schedule_origin(workflow_id: UUID | str) -> WorkflowExecutionOrigin:
    """Origin for a cron-triggered run (entrypoint id is the workflow id)."""
    return WorkflowExecutionOrigin(ExecutionEntrypoint.SCHEDULE, str(workflow_id))


def api_key_origin(api_key_id: UUID | str) -> WorkflowExecutionOrigin:
    """Origin for a run invoked with an API key (entrypoint id is the key id)."""
    return WorkflowExecutionOrigin(ExecutionEntrypoint.API_KEY, str(api_key_id))


def embed_origin(resource_id: UUID | str) -> WorkflowExecutionOrigin:
    """Origin for a run invoked from the public embed surface."""
    return WorkflowExecutionOrigin(ExecutionEntrypoint.EMBED, str(resource_id))


def origin_snapshot(origin: WorkflowExecutionOrigin) -> dict[str, str]:
    """JSON-serializable snapshot value for ``WorkflowRun.context_snapshot``."""
    return {
        "entrypoint": origin.entrypoint.value,
        "entrypoint_id": origin.entrypoint_id,
    }


def _snapshot_dict(run: Any) -> dict[str, Any] | None:
    snapshot = getattr(run, "context_snapshot", None)
    return snapshot if isinstance(snapshot, dict) else None


def read_run_origin(run: Any) -> WorkflowExecutionOrigin | None:
    """Read the persisted origin, falling back to the workflow surface.

    ``None`` means the run has no workflow id at all, in which case no stable
    entrypoint exists and non-interactive tool execution must fail closed.
    """
    snapshot = _snapshot_dict(run)
    raw = snapshot.get(ORIGIN_SNAPSHOT_KEY) if snapshot else None
    if isinstance(raw, dict):
        try:
            entrypoint = ExecutionEntrypoint(str(raw.get("entrypoint") or ""))
            entrypoint_id = raw.get("entrypoint_id")
            if entrypoint in WORKFLOW_ORIGIN_ENTRYPOINTS and isinstance(
                entrypoint_id, str
            ):
                return WorkflowExecutionOrigin(entrypoint, entrypoint_id)
        except (TypeError, ValueError):
            pass
        logger.warning(
            "Ignoring malformed workflow execution origin for run %s",
            getattr(run, "id", None),
        )
    workflow_id = getattr(run, "workflow_id", None)
    if workflow_id is None:
        return None
    return workflow_origin(workflow_id)


def stamp_run_origin(
    run: Any,
    origin: WorkflowExecutionOrigin,
    *,
    overwrite: bool = False,
) -> bool:
    """Persist ``origin`` into the run snapshot; returns True when changed.

    ``overwrite=False`` keeps an already-recorded origin (resume must not be
    able to change the surface), so this doubles as the "stamp only if absent"
    helper for legacy rows and background execution.
    """
    snapshot = _snapshot_dict(run)
    if snapshot is None:
        snapshot = {}
    if not overwrite and ORIGIN_SNAPSHOT_KEY in snapshot:
        return False
    snapshot[ORIGIN_SNAPSHOT_KEY] = origin_snapshot(origin)
    run.context_snapshot = snapshot
    return True


def inherited_origin(parent_run: Any) -> WorkflowExecutionOrigin | None:
    """Origin a nested (sub-workflow) run inherits from its parent.

    A child never gains a new surface: it uses the parent's entrypoint and id so
    grants stay bound to however the root run was invoked. A legacy parent
    without a workflow id yields ``None`` and the child fails closed.
    """
    origin = read_run_origin(parent_run)
    if origin is not None:
        return origin
    workflow_id = getattr(parent_run, "workflow_id", None)
    if workflow_id is None:
        return None
    return workflow_origin(workflow_id)


__all__ = [
    "MAX_ENTRYPOINT_ID_LENGTH",
    "ORIGIN_SNAPSHOT_KEY",
    "WORKFLOW_ORIGIN_ENTRYPOINTS",
    "WorkflowExecutionOrigin",
    "api_key_origin",
    "embed_origin",
    "inherited_origin",
    "origin_snapshot",
    "read_run_origin",
    "schedule_origin",
    "stamp_run_origin",
    "workflow_origin",
]
