"""One-way cutover away from site/team/entrypoint approval policy layers.

The layers were removed as configuration and execution inputs: only the tool's
own :class:`~app.schemas.tool_approval.ToolApprovalPolicy` is evaluated now.
An execution created before the cutover froze the old layers in
``policy_snapshot`` (including the layers that could require approval or deny
the call). Removing those layers must not silently relax a pending decision:

* every unstarted execution (``awaiting_approval`` or ``ready``) whose stored
  snapshot contains any layer other than ``tool`` is cancelled atomically with
  its pending gates, using ``binding_changed`` so the runner reports the same
  terminal reason as a claim-time policy-hash mismatch;
* ``executing`` and terminal rows are never touched: a call that may already
  have produced a side effect must not be reported as cancelled;
* historical rows, decisions and policy snapshots are preserved as-is, and no
  marker is written (old processes must keep reading the rows);
* after the cancellation transaction commits, every AgentRun/WorkflowRun still
  ``waiting`` on a terminal cutover approval is woken through the existing
  resume path: an AgentRun is queued with the terminal tool error and a
  WorkflowRun is dispatched to fail the parked node. The wake-up is a
  reconciliation over waiting runs, so a process that restarts between the
  commit and the dispatch repairs the gap on the next startup instead of
  leaving the run parked forever.

The runtime recomputes the effective policy from the tool layer alone, so a
claim whose stored ``policy_hash`` bound the retired layers is cancelled at
claim time even if this migration did not run. This module makes the safe
outcome immediate and visible.

The retired ``tool_approval_policies`` table is deliberately left in place: it
is no longer read or written by the application, and preserving it keeps a
rollback and an audit of the previous configuration possible.

Running the migration twice is a no-op because every update is guarded by the
non-terminal state it transitions from.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core.tool_approval_caller_migration import existing_tables
from app.models.tool_approval import ToolApprovalRequest, ToolExecution
from app.schemas.tool_approval import (
    ApprovalRequestStatus,
    ExecutionRunKind,
    PolicySource,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
)

logger = logging.getLogger(__name__)

UNSTARTED_EXECUTION_STATUSES: tuple[ToolExecutionStatus, ...] = (
    ToolExecutionStatus.AWAITING_APPROVAL,
    ToolExecutionStatus.READY,
)
#: Cancel reasons produced by a cutover/abandoned approval path (as opposed to
#: an explicit reject/expiry, whose decision path already scheduled the run).
_WAKEABLE_CANCEL_REASONS: tuple[ToolExecutionCancelReason, ...] = (
    ToolExecutionCancelReason.BINDING_CHANGED,
    ToolExecutionCancelReason.CANCELLED,
)
_EXECUTION_TABLES = ("tool_executions", "tool_approval_requests")
_BATCH_SIZE = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_has_removed_layers(snapshot: Any) -> bool:
    """True when a stored execution snapshot bound a retired policy layer.

    Only a provable non-``tool`` layer counts. Unknown or malformed snapshots
    are left alone: the claim-time policy-hash check still protects them, and
    this migration must never cancel work on a guess.
    """
    if not isinstance(snapshot, dict):
        return False
    layers = snapshot.get("layers")
    if not isinstance(layers, list):
        return False
    tool_source = PolicySource.TOOL.value
    return any(
        isinstance(layer, dict)
        and layer.get("source") is not None
        and layer.get("source") != tool_source
        for layer in layers
    )


async def _resume_agent_runs_waiting_on_terminal_approval(
    summary: dict[str, int],
) -> None:
    """Queue WAITING AgentRuns whose pending approval is already terminal."""
    from app.models.agent_run import AgentRun, AgentRunStatus
    from app.services.agent_run_store import schedule_agent_run_approval_resume

    rows = await AgentRun.filter(
        status=AgentRunStatus.WAITING,
        pending_tool_call_id__not_isnull=True,
    ).values_list("id", "pending_tool_call_id")
    for run_id, tool_call_id in rows:
        execution = (
            await ToolExecution.filter(
                run_kind=ExecutionRunKind.AGENT,
                run_id=run_id,
                tool_call_id=tool_call_id,
                status=ToolExecutionStatus.CANCELLED,
                cancel_reason__in=list(_WAKEABLE_CANCEL_REASONS),
            )
            .order_by("-created_at")
            .first()
        )
        if execution is None:
            continue
        try:
            queued = await schedule_agent_run_approval_resume(execution)
        except Exception:
            # Reconciliation runs again on the next startup; never fail the
            # cutover because the broker/queue was temporarily unavailable.
            logger.warning(
                "Failed to wake AgentRun %s after its tool approval became terminal",
                run_id,
                exc_info=True,
            )
            continue
        if queued is not None:
            summary["agent_runs_resumed"] += 1


async def _resume_workflow_runs_waiting_on_terminal_approval(
    summary: dict[str, int],
) -> None:
    """Dispatch WAITING WorkflowRuns whose parked tool approval is terminal."""
    from app.models.workflow import NodeExecution, NodeStatus, RunStatus, WorkflowRun
    from app.services.workflow.tool_approval_resume import (
        fallback_tool_call_token,
        schedule_workflow_run_approval_resume,
        tool_call_token,
    )

    run_ids = await WorkflowRun.filter(status=RunStatus.WAITING).values_list(
        "id", flat=True
    )
    for run_id in run_ids:
        node = (
            await NodeExecution.filter(run_id=run_id, status=NodeStatus.WAITING)
            .order_by("-execution_order")
            .first()
        )
        if node is None:
            continue
        tokens = [
            tool_call_token(node.id),
            fallback_tool_call_token(run_id, node.node_id),
        ]
        execution = (
            await ToolExecution.filter(
                run_kind=ExecutionRunKind.WORKFLOW,
                run_id=run_id,
                tool_call_id__in=tokens,
                status=ToolExecutionStatus.CANCELLED,
                cancel_reason__in=list(_WAKEABLE_CANCEL_REASONS),
            )
            .order_by("-created_at")
            .first()
        )
        if execution is None:
            continue
        try:
            resumed = await schedule_workflow_run_approval_resume(execution)
        except Exception:
            logger.warning(
                "Failed to wake WorkflowRun %s after its tool approval became terminal",
                run_id,
                exc_info=True,
            )
            continue
        if resumed is not None:
            summary["workflow_runs_resumed"] += 1


async def resume_runs_waiting_on_terminal_approval() -> dict[str, int]:
    """Wake waiting runs whose cutover approval can no longer be decided.

    Reconciliation is driven by the ``waiting`` run rows instead of the
    cancellation batch, so it also repairs a process that crashed after the
    cancellation commit but before the dispatch, and it is a no-op once the
    run has left ``waiting``. Both schedulers are idempotent: an AgentRun is
    only queued when its pending call still matches the terminal execution, and
    a WorkflowRun resume re-claims ``WAITING -> RUNNING`` atomically.
    """
    summary = {"agent_runs_resumed": 0, "workflow_runs_resumed": 0}
    await _resume_agent_runs_waiting_on_terminal_approval(summary)
    await _resume_workflow_runs_waiting_on_terminal_approval(summary)
    return summary


async def cancel_unstarted_layer_bound_executions(
    *, now: datetime | None = None
) -> dict[str, int]:
    """Cancel unstarted executions whose snapshot bound a retired layer.

    The post-commit reconciliation also wakes any run still waiting on a
    terminal cutover/abandoned approval, which covers a restart between the
    cancellation and the dispatch.
    """
    summary = {
        "executions_cancelled": 0,
        "requests_cancelled": 0,
        "agent_runs_resumed": 0,
        "workflow_runs_resumed": 0,
    }
    connection = Tortoise.get_connection("default")
    tables = await existing_tables(connection, _EXECUTION_TABLES)
    if not set(_EXECUTION_TABLES).issubset(tables):
        logger.info(
            "Tool execution tables are not initialized; skipping removed-layer "
            "approval cutover"
        )
        return summary

    current = now or _utcnow()
    async with in_transaction() as conn:
        rows = await (
            ToolExecution.filter(status__in=list(UNSTARTED_EXECUTION_STATUSES))
            .using_db(conn)
            .values_list("id", "policy_snapshot")
        )
        candidate_ids = [
            execution_id
            for execution_id, snapshot in rows
            if isinstance(execution_id, UUID) and snapshot_has_removed_layers(snapshot)
        ]

        for offset in range(0, len(candidate_ids), _BATCH_SIZE):
            batch = candidate_ids[offset : offset + _BATCH_SIZE]
            for execution_id in sorted(batch, key=str):
                execution = (
                    await ToolExecution.filter(id=execution_id)
                    .using_db(conn)
                    .select_for_update()
                    .first()
                )
                if (
                    execution is None
                    or execution.status not in UNSTARTED_EXECUTION_STATUSES
                    or not snapshot_has_removed_layers(execution.policy_snapshot)
                ):
                    continue

                cancelled = (
                    await ToolExecution.filter(
                        id=execution_id,
                        status__in=list(UNSTARTED_EXECUTION_STATUSES),
                    )
                    .using_db(conn)
                    .update(
                        status=ToolExecutionStatus.CANCELLED,
                        cancel_reason=ToolExecutionCancelReason.BINDING_CHANGED,
                        finished_at=current,
                        updated_at=current,
                    )
                )
                if not cancelled:
                    continue
                summary["executions_cancelled"] += 1
                summary["requests_cancelled"] += (
                    await ToolApprovalRequest.filter(
                        execution_id=execution_id,
                        status=ApprovalRequestStatus.PENDING,
                    )
                    .using_db(conn)
                    .update(
                        status=ApprovalRequestStatus.CANCELLED,
                        resolved_at=current,
                        updated_at=current,
                    )
                )

    # The cancellation transaction has committed. Wake every run that is still
    # waiting on a terminal cutover approval instead of leaving it parked until
    # some unrelated event; the reconciliation also repairs crash gaps.
    try:
        wake = await resume_runs_waiting_on_terminal_approval()
    except Exception:
        logger.warning(
            "Could not wake runs waiting on terminal cutover approvals; the "
            "idempotent reconciliation will retry on the next startup",
            exc_info=True,
        )
    else:
        summary.update(wake)
    if summary["executions_cancelled"]:
        logger.warning(
            "Cancelled %s unstarted tool executions bound to removed "
            "site/team/entrypoint approval policy layers",
            summary["executions_cancelled"],
        )
    if summary["agent_runs_resumed"] or summary["workflow_runs_resumed"]:
        logger.warning(
            "Resumed %s AgentRun(s) and %s WorkflowRun(s) that were waiting on "
            "a terminal cutover approval",
            summary["agent_runs_resumed"],
            summary["workflow_runs_resumed"],
        )
    return summary


async def migrate_removed_approval_policy_layers(
    *, now: datetime | None = None
) -> dict[str, int]:
    """Run the removed-layer approval cutover and report what it observed."""
    return await cancel_unstarted_layer_bound_executions(now=now)


__all__ = [
    "UNSTARTED_EXECUTION_STATUSES",
    "cancel_unstarted_layer_bound_executions",
    "migrate_removed_approval_policy_layers",
    "resume_runs_waiting_on_terminal_approval",
    "snapshot_has_removed_layers",
]
