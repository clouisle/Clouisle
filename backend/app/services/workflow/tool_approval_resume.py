"""Resume a workflow run parked on a unified tool approval.

The tool node never blocks on an approval. It returns ``waiting=True``, the
orchestrator persists the run as ``WAITING`` and the Celery task exits, so no
network session is treated as resumable state. A later approval decision (or
its rejection/expiry) wakes the run through the approval service:

    from app.services.workflow.tool_approval_resume import (
        schedule_workflow_run_approval_resume,
    )
    await schedule_workflow_run_approval_resume(execution)

Only a ``WAITING`` workflow run is resumed; a stopped/cancelled run is never
revived by a late decision. The resume task re-claims ``WAITING -> RUNNING``
atomically, so a duplicate or stale dispatch is a no-op.

The tool call is identified by the stable ``NodeExecution`` row of the parked
attempt. That lets the resumed node find (and only find) the execution created
before it parked, so the stored parameter snapshot is executed at most once and
already-completed sibling nodes are not replayed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from app.models.tool_approval import (
    ExecutionRunKind,
    ToolExecution,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)
from app.models.workflow import NodeExecution, RunStatus, WorkflowRun

logger = logging.getLogger(__name__)


def tool_call_token(node_execution_id: UUID) -> str:
    """Stable per-node-attempt call id used for deferred tool executions."""
    return f"workflow-node-execution:{node_execution_id}"


def fallback_tool_call_token(run_id: UUID, node_id: str) -> str:
    """Deterministic call id for the (unexpected) case without a node record."""
    return f"workflow-node:{run_id}:{node_id}"


async def token_for_attempt(run: WorkflowRun, node_id: str) -> str:
    """Call id of the node's latest attempt: stable across park/resume/retry."""
    node_execution = (
        await NodeExecution.filter(run_id=run.id, node_id=node_id)
        .order_by("-execution_order")
        .first()
    )
    if node_execution is None:
        return fallback_tool_call_token(run.id, node_id)
    return tool_call_token(node_execution.id)


async def find_execution_for_token(
    run: WorkflowRun, call_token: str
) -> ToolExecution | None:
    """The deferred execution already created for this node attempt, if any."""
    return (
        await ToolExecution.filter(
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=run.id,
            tool_call_id=call_token,
        )
        .order_by("-created_at")
        .first()
    )


#: Translation keys surfaced as the node failure for a terminal execution.
TERMINAL_EXECUTION_ERRORS: dict[ToolExecutionCancelReason, str] = {
    ToolExecutionCancelReason.REJECTED: "tool_approval_rejected",
    ToolExecutionCancelReason.EXPIRED: "tool_approval_expired",
    ToolExecutionCancelReason.REVOKED: "tool_approval_cancelled",
    ToolExecutionCancelReason.CANCELLED: "tool_approval_cancelled",
    ToolExecutionCancelReason.BINDING_CHANGED: "tool_approval_binding_changed",
    ToolExecutionCancelReason.RUN_STOPPED: "workflow_run_cancelled",
    ToolExecutionCancelReason.POLICY_DENIED: "tool_execution_access_denied",
}


def terminal_execution_error(execution: ToolExecution) -> str | None:
    """Return the node failure key for an execution that will never run."""
    if execution.status == ToolExecutionStatus.CANCELLED:
        return TERMINAL_EXECUTION_ERRORS.get(
            execution.cancel_reason, "tool_approval_cancelled"
        )
    if execution.status == ToolExecutionStatus.OUTCOME_UNKNOWN:
        return "tool_execution_outcome_unknown"
    if execution.status == ToolExecutionStatus.FAILED:
        return "tool_execution_failed"
    return None


def approval_deadline_passed(
    execution: ToolExecution, now: datetime | None = None
) -> bool:
    """Whether a still-pending execution is past its approval deadline."""
    deadline = execution.expires_at
    if deadline is None:
        return False
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline <= (now or datetime.now(timezone.utc))


async def queue_workflow_run_approval_resume(
    execution: ToolExecution | None,
) -> WorkflowRun | None:
    """Return the WAITING run this execution may resume, if it is resumable."""
    if execution is None or execution.run_kind != ExecutionRunKind.WORKFLOW:
        return None
    if execution.run_id is None:
        return None
    run = await WorkflowRun.filter(id=execution.run_id).first()
    if run is None or run.status != RunStatus.WAITING:
        return None
    return run


async def schedule_workflow_run_approval_resume(
    execution: ToolExecution | None,
) -> WorkflowRun | None:
    """Dispatch the resume task for a run parked on this execution's approval.

    Best effort: the approval decision stays committed if the broker is down and
    the failure is logged rather than turning a granted approval into a lie.
    """
    run = await queue_workflow_run_approval_resume(execution)
    if run is None:
        return None
    try:
        from app.tasks.workflow import resume_workflow_task

        resume_workflow_task.delay(str(run.id))
    except Exception:
        logger.warning(
            "Failed to schedule workflow resume for run %s after approval of %s",
            run.id,
            execution.id if execution else None,
            exc_info=True,
        )
    return run


async def schedule_workflow_resume_for_execution(execution_id: UUID) -> bool:
    """Approval-service entry point: resume by execution id."""
    execution = await ToolExecution.filter(id=execution_id).first()
    return await schedule_workflow_run_approval_resume(execution) is not None


async def ensure_resume_after_park(run: WorkflowRun, node_id: str) -> bool:
    """Close the decision-vs-park race for a run that just parked.

    An approval can commit while the node is still returning ``waiting`` (the
    run is not yet ``WAITING``, so the decision-time hook skips it). After the
    run is persisted as waiting we look at that node's execution: a terminal or
    approved execution would otherwise leave the run parked forever. Non-tool
    nodes (pause nodes) have no deferred execution and are skipped cheaply.
    """
    try:
        node_execution = (
            await NodeExecution.filter(run_id=run.id, node_id=node_id)
            .order_by("-execution_order")
            .first()
        )
        if node_execution is None or node_execution.node_type != "tool":
            return False
        execution = await find_execution_for_token(
            run, tool_call_token(node_execution.id)
        )
        if execution is None:
            return False
        if execution.status in {
            ToolExecutionStatus.AWAITING_APPROVAL,
            ToolExecutionStatus.EXECUTING,
        }:
            return False
        return await schedule_workflow_run_approval_resume(execution) is not None
    except Exception:
        logger.warning(
            "Failed to check approval resume state for run %s node %s",
            run.id,
            node_id,
            exc_info=True,
        )
        return False


__all__ = [
    "approval_deadline_passed",
    "ensure_resume_after_park",
    "fallback_tool_call_token",
    "find_execution_for_token",
    "queue_workflow_run_approval_resume",
    "schedule_workflow_resume_for_execution",
    "schedule_workflow_run_approval_resume",
    "terminal_execution_error",
    "token_for_attempt",
    "tool_call_token",
]
