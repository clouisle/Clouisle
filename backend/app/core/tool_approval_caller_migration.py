"""One-way cutover from multi-audience approval gates to caller confirmation.

Legacy policies could require designated users or team roles. Those audiences
must never be reinterpreted as caller confirmation or as an implicit allow:
the runtime fails closed on them and an administrator has to reconfigure the
tool. This module only removes the possibility that already-created work
completes under the retired contract.

The cutover is intentionally narrow and idempotent:

* Every execution that has not started yet (``awaiting_approval`` or
  ``ready``) and is associated with at least one ``user``/``team_role`` gate
  is cancelled atomically together with all of its pending gates. This covers
  partially resolved gates (an external gate already approved, a caller gate
  still pending) and fully approved ``ready`` rows that would otherwise start
  executing after the release.
* ``executing`` and terminal rows are never touched: a call that may already
  have produced a side effect must not be reported as cancelled. Those rows
  are covered by the runtime fail-closed enforcement and an operator audit.
* Historical rows, decisions and policy JSON are preserved byte-for-byte. No
  marker is added (the schema is unchanged and old processes must keep
  working), and nothing is rewritten to ``caller`` or ``allow``.
* No run resume is scheduled. A cancelled execution is terminal; resuming the
  owning run would be exactly the silent continuation this cutover prevents.

Running the migration twice is a no-op because every update is guarded by the
non-terminal state it transitions from.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.models.tool import Tool
from app.models.tool_approval import ToolApprovalRequest, ToolExecution
from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.schemas.tool_approval import (
    EXTERNAL_APPROVAL_GATE_KINDS,
    ApprovalRequestStatus,
    ToolExecutionCancelReason,
    ToolExecutionStatus,
    external_approval_gate_kinds,
)

logger = logging.getLogger(__name__)

#: Gate audiences retired by the caller-only confirmation contract.
LEGACY_EXTERNAL_GATE_KINDS: tuple[str, ...] = tuple(
    sorted(kind.value for kind in EXTERNAL_APPROVAL_GATE_KINDS)
)

#: Executions that have not started; both may still be cancelled safely.
UNSTARTED_EXECUTION_STATUSES: tuple[ToolExecutionStatus, ...] = (
    ToolExecutionStatus.AWAITING_APPROVAL,
    ToolExecutionStatus.READY,
)

_EXECUTION_TABLES = ("tool_executions", "tool_approval_requests")
_POLICY_TABLES = ("tools", "tool_approval_policies")
_BATCH_SIZE = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        pass
    try:
        return row[index]
    except (KeyError, TypeError, IndexError):
        return None


async def _existing_tables(connection: Any, names: Sequence[str]) -> frozenset[str]:
    """Return the requested table names that exist, without ORM reads.

    The migration normally runs right after ``generate_schemas()``, but it can
    also be invoked from a deployment command against a database that has not
    been initialized yet. In that case it must be a no-op instead of raising.
    """
    dialect = getattr(getattr(connection, "capabilities", None), "dialect", "")
    if dialect == "sqlite":
        _, rows = await connection.execute_query(
            "SELECT name AS table_name FROM sqlite_master WHERE type = 'table'"
        )
    else:
        _, rows = await connection.execute_query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
    present = {
        value
        for row in rows
        if isinstance(value := _row_value(row, "table_name", 0), str)
    }
    return frozenset(present.intersection(names))


def _load_policy(value: Any) -> Any:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def policy_has_external_gate(value: Any) -> bool:
    """True when a stored policy nests a ``user``/``team_role`` gate.

    Delegates to the canonical schema walker so persisted history, the write
    path and the execution boundary agree on what counts as a legacy
    audience. Malformed JSON is not reported here: the runtime already fails
    closed on unparsable policies.
    """
    return bool(external_approval_gate_kinds(_load_policy(value)))


async def cancel_unstarted_legacy_approvals(
    *, now: datetime | None = None
) -> dict[str, int]:
    """Cancel unstarted executions that involve an external audience.

    All updates happen in one transaction. The execution row is locked before
    re-checking its still-unstarted state, so a concurrent decision can only
    win or lose the race atomically; it can never leave a cancelled execution
    with an approved gate or a resumable run.
    """
    summary = {"executions_cancelled": 0, "requests_cancelled": 0}
    connection = Tortoise.get_connection("default")
    tables = await _existing_tables(connection, _EXECUTION_TABLES)
    if not set(_EXECUTION_TABLES).issubset(tables):
        logger.info(
            "Tool approval tables are not initialized; skipping caller-only "
            "approval cutover"
        )
        return summary

    current = _as_utc(now) or _utcnow()

    async with in_transaction() as conn:
        # Tortoise only exposes the related primary key for reverse-FK filters,
        # so resolve unstarted executions first and then their legacy gates.
        # Unstarted rows are transient, unlike the append-only history.
        unstarted_ids = [
            execution_id
            for execution_id in await ToolExecution.filter(
                status__in=list(UNSTARTED_EXECUTION_STATUSES)
            )
            .using_db(conn)
            .values_list("id", flat=True)
            if isinstance(execution_id, UUID)
        ]

        for offset in range(0, len(unstarted_ids), _BATCH_SIZE):
            batch = unstarted_ids[offset : offset + _BATCH_SIZE]
            legacy_execution_ids = {
                execution_id
                for execution_id in await ToolApprovalRequest.filter(
                    execution_id__in=batch,
                    gate_kind__in=list(LEGACY_EXTERNAL_GATE_KINDS),
                )
                .using_db(conn)
                .values_list("execution_id", flat=True)
                if isinstance(execution_id, UUID)
            }
            for execution_id in sorted(legacy_execution_ids, key=str):
                execution = (
                    await ToolExecution.filter(id=execution_id)
                    .using_db(conn)
                    .select_for_update()
                    .first()
                )
                if (
                    execution is None
                    or execution.status not in UNSTARTED_EXECUTION_STATUSES
                ):
                    continue

                has_legacy_gate = (
                    await ToolApprovalRequest.filter(
                        execution_id=execution_id,
                        gate_kind__in=list(LEGACY_EXTERNAL_GATE_KINDS),
                    )
                    .using_db(conn)
                    .exists()
                )
                if not has_legacy_gate:
                    continue

                cancelled = (
                    await ToolExecution.filter(
                        id=execution_id,
                        status__in=list(UNSTARTED_EXECUTION_STATUSES),
                    )
                    .using_db(conn)
                    .update(
                        status=ToolExecutionStatus.CANCELLED,
                        cancel_reason=ToolExecutionCancelReason.CANCELLED,
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

    if summary["executions_cancelled"]:
        logger.warning(
            "Cancelled %s unstarted tool executions that required retired "
            "user/team-role approval; no run resume was scheduled",
            summary["executions_cancelled"],
        )
    return summary


async def scan_legacy_external_policies() -> dict[str, int]:
    """Count stored policies with external gates, without modifying them."""
    summary = {"tools_with_legacy_gates": 0, "policy_layers_with_legacy_gates": 0}
    connection = Tortoise.get_connection("default")
    tables = await _existing_tables(connection, _POLICY_TABLES)

    if "tools" in tables:
        async for raw in Tool.all().values_list("approval_policy", flat=True):
            if policy_has_external_gate(raw):
                summary["tools_with_legacy_gates"] += 1

    if "tool_approval_policies" in tables:
        async for raw in ToolApprovalPolicyDefinition.all().values_list(
            "policy", flat=True
        ):
            if policy_has_external_gate(raw):
                summary["policy_layers_with_legacy_gates"] += 1

    return summary


async def migrate_caller_only_tool_confirmation(
    *, now: datetime | None = None
) -> dict[str, int]:
    """Run the caller-only approval cutover and report what it observed.

    Cancellation happens first so an unstarted execution cannot become ready
    while policies are being counted. The policy scan is read-only: legacy
    configuration stays on record for administrators to replace explicitly.
    """
    summary = await cancel_unstarted_legacy_approvals(now=now)
    summary.update(await scan_legacy_external_policies())
    return summary


__all__ = [
    "LEGACY_EXTERNAL_GATE_KINDS",
    "UNSTARTED_EXECUTION_STATUSES",
    "cancel_unstarted_legacy_approvals",
    "migrate_caller_only_tool_confirmation",
    "policy_has_external_gate",
    "scan_legacy_external_policies",
]
