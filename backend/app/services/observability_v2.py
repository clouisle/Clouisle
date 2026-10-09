"""Compact, bounded observability queries and durable alert lifecycle."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from time import monotonic

from tortoise.expressions import Q

from app.models.observability import (
    ObservabilityAlertEvent,
    ObservabilityAlertRule,
    ObservabilityRun,
)
from app.core.db_limits import run_bounded
from app.models.agent import Agent, Message
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.model import Model, PROVIDER_DEFAULTS

logger = logging.getLogger(__name__)
PERIODS = {"15m": 900, "1h": 3600, "24h": 86400, "7d": 604800}
RETENTION_DAYS = 30
RETENTION_BATCH_SIZE = 500
ACTIVE_RUN_STATUSES = (
    "queued",
    "pending",
    "running",
    "waiting",
    "stopping",
    "completing",
)
RETENTION_BATCHES_PER_CYCLE = 10
TERMINAL_SUMMARY_BATCH_SIZE = 100
TERMINAL_SUMMARY_GRACE_SECONDS = 60
DB_QUERY_LIMIT = 5000
MAX_DEPENDENCY_METRICS_PER_RUN = 128
DEPENDENCY_RUN_LIMIT = 1000
_CACHE_TTL_SECONDS = 10
_CACHE_MAX_ENTRIES = 128
_SNAPSHOT_CACHE: dict[tuple[Any, ...], tuple[float, Any]] = {}
_SNAPSHOT_INFLIGHT: dict[tuple[Any, ...], asyncio.Task[Any]] = {}
_SNAPSHOT_LOCK = asyncio.Lock()


def utcnow() -> datetime:
    return datetime.now(UTC)


def window(
    period: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[datetime, datetime]:
    if period == "custom":
        if start_time is None or end_time is None:
            raise ValueError("Custom period requires start_time and end_time")
        if start_time.utcoffset() is None or end_time.utcoffset() is None:
            raise ValueError("Custom timestamps must include a timezone")
        start, end = start_time.astimezone(UTC), end_time.astimezone(UTC)
        if start >= end:
            raise ValueError("start_time must be before end_time")
        return start, end
    if start_time is not None or end_time is not None:
        raise ValueError("Explicit timestamps require period=custom")
    if period not in PERIODS:
        raise ValueError("Invalid period")
    end = utcnow()
    return end - timedelta(seconds=PERIODS[period]), end


def meta(
    start: datetime, end: datetime, count: int, *, partial: bool = False
) -> dict[str, Any]:
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "sampled_at": utcnow().isoformat(),
        "period": "",
        "state": "partial" if partial else ("fresh" if count else "no_data"),
        "sample_count": count,
    }


async def _cached_snapshot(
    key: tuple[Any, ...], producer, ttl: int = _CACHE_TTL_SECONDS
):
    now = monotonic()
    async with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
        if cached:
            _SNAPSHOT_CACHE.pop(key, None)
        task = _SNAPSHOT_INFLIGHT.get(key)
        if task is None:
            task = asyncio.create_task(producer())
            _SNAPSHOT_INFLIGHT[key] = task
    try:
        result = await asyncio.shield(task)
    except BaseException:
        if task.done():
            async with _SNAPSHOT_LOCK:
                if _SNAPSHOT_INFLIGHT.get(key) is task:
                    _SNAPSHOT_INFLIGHT.pop(key, None)
        raise
    async with _SNAPSHOT_LOCK:
        if _SNAPSHOT_INFLIGHT.get(key) is task:
            _SNAPSHOT_INFLIGHT.pop(key, None)
            _SNAPSHOT_CACHE[key] = (monotonic() + ttl, result)
            now = monotonic()
            for expired_key, (expires_at, _) in list(_SNAPSHOT_CACHE.items()):
                if expires_at <= now:
                    _SNAPSHOT_CACHE.pop(expired_key, None)
            while len(_SNAPSHOT_CACHE) > _CACHE_MAX_ENTRIES:
                _SNAPSHOT_CACHE.pop(next(iter(_SNAPSHOT_CACHE)))
    return result


def _encode_cursor(timestamp: datetime, run_id: str) -> str:
    raw = f"{timestamp.isoformat()}|{run_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        timestamp, run_id = raw.split("|", 1)
        return datetime.fromisoformat(timestamp), run_id
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def _summary(row: ObservabilityRun) -> dict[str, Any]:
    bootstrap_ms = None
    if row.started_at and row.message_started_at:
        bootstrap_ms = max(
            0, int((row.message_started_at - row.started_at).total_seconds() * 1000)
        )
    return {
        "run_id": str(row.id),
        "source": row.source,
        "resource_id": row.resource_id,
        "resource_name": row.resource_name,
        "team_id": row.team_id,
        "team_name": row.team_name,
        "status": row.status,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "message_started_at": row.message_started_at.isoformat()
        if row.message_started_at
        else None,
        "worker_bootstrap_ms": bootstrap_ms,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "queue_duration_ms": row.queue_duration_ms,
        "execution_duration_ms": row.execution_duration_ms,
        "total_duration_ms": row.total_duration_ms,
        "first_token_ms": row.first_token_ms,
        "total_tokens": row.total_tokens,
        "error_category": row.error_category,
        "error_code": row.error_code,
        "trace_available": row.trace_available,
        "trace_complete": row.trace_complete,
    }


def agent_terminal_summary(
    run: AgentRun, details: dict[str, Any], message: dict[str, Any]
) -> dict[str, Any]:
    """Build the same terminal summary for the fast path and reconciliation."""
    usage = message.get("token_usage") or {}
    try:
        tokens = max(0, int(usage.get("total", usage.get("total_tokens", 0)) or 0))
        if not tokens:
            tokens = max(0, int(usage.get("prompt", 0) or 0)) + max(
                0, int(usage.get("completion", 0) or 0)
            )
    except (AttributeError, TypeError, ValueError):
        tokens = 0
    return {
        "run_id": run.id,
        "source": "agent",
        "resource_id": str(run.agent_id),
        "resource_name": details.get("name"),
        "team_id": str(details["team_id"]) if details.get("team_id") else None,
        "team_name": details.get("team__name"),
        "status": run.status.value,
        "model_name": str(message["model_used"])[:200]
        if message.get("model_used")
        else None,
        "total_tokens": tokens,
        "submitted_at": run.submitted_at,
        "started_at": run.started_at,
        "message_started_at": run.message_started_at,
        "finished_at": run.finished_at,
        "execution_duration_ms": int(
            (run.finished_at - run.message_started_at).total_seconds() * 1000
        )
        if run.message_started_at and run.finished_at
        else None,
        "first_token_ms": run.first_token_ms,
        "total_duration_ms": int(
            (run.finished_at - run.started_at).total_seconds() * 1000
        )
        if run.started_at and run.finished_at
        else None,
        "error_code": run.error_code,
    }


async def reconcile_agent_terminal_summaries(connection: Any) -> int:
    """Repair retained summaries without changing or replaying authoritative runs.

    Filter terminal AgentRuns before applying the batch limit so long-running
    or waiting runs cannot starve repair. The maintenance leader owns the
    transaction; failures roll back and remain eligible for the next cycle.
    """
    now = utcnow()
    _, candidates = await connection.execute_query(
        """
        SELECT o.id
        FROM observability_runs o
        JOIN agent_runs r ON r.id = o.id
        WHERE o.source = 'agent'
          AND (o.status = ANY($1::text[]) OR o.finished_at IS NULL)
          AND o.submitted_at >= $2
          AND r.status = ANY($3::text[])
          AND r.finished_at <= $4
        ORDER BY r.finished_at, o.id
        LIMIT $5
        """,
        [
            list(ACTIVE_RUN_STATUSES),
            now - timedelta(days=RETENTION_DAYS),
            [
                AgentRunStatus.COMPLETED.value,
                AgentRunStatus.STOPPED.value,
                AgentRunStatus.FAILED.value,
                AgentRunStatus.INTERRUPTED.value,
            ],
            now - timedelta(seconds=TERMINAL_SUMMARY_GRACE_SECONDS),
            TERMINAL_SUMMARY_BATCH_SIZE,
        ],
    )
    if not candidates:
        return 0
    runs = (
        await AgentRun.filter(id__in=[row["id"] for row in candidates])
        .using_db(connection)
        .only(
            "id",
            "agent_id",
            "canonical_message_id",
            "status",
            "submitted_at",
            "started_at",
            "message_started_at",
            "finished_at",
            "first_token_ms",
            "error_code",
        )
    )
    details = (
        await Agent.filter(id__in={run.agent_id for run in runs})
        .using_db(connection)
        .values(
            "id",
            "name",
            "team_id",
            "team__name",
        )
    )
    message_ids = {run.canonical_message_id for run in runs if run.canonical_message_id}
    messages = (
        await Message.filter(id__in=message_ids)
        .using_db(connection)
        .values(
            "id",
            "model_used",
            "token_usage",
        )
        if message_ids
        else []
    )
    details_by_id = {row["id"]: row for row in details}
    messages_by_id = {row["id"]: row for row in messages}
    repaired = 0
    for run in runs:
        saved = await record_run(
            **agent_terminal_summary(
                run,
                details_by_id.get(run.agent_id, {}),
                messages_by_id.get(run.canonical_message_id, {}),
            )
        )
        if not saved:
            raise RuntimeError(f"Terminal summary reconciliation failed for {run.id}")
        repaired += 1
    return repaired


async def record_run(
    *,
    run_id: UUID,
    source: str,
    resource_id: str | None,
    resource_name: str | None,
    team_id: str | None,
    team_name: str | None,
    status: str,
    submitted_at: datetime | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    total_duration_ms: int | None,
    execution_duration_ms: int | None = None,
    message_started_at: datetime | None = None,
    first_token_ms: int | None = None,
    total_tokens: int = 0,
    model_name: str | None = None,
    error_code: str | None = None,
) -> bool:
    """Best-effort summary upsert; never let telemetry failure affect execution."""
    try:
        total_ms = (
            max(0, int((finished_at - submitted_at).total_seconds() * 1000))
            if submitted_at and finished_at
            else total_duration_ms
        )
        values = {
            "resource_id": resource_id,
            "resource_name": resource_name,
            "model_name": model_name,
            "team_id": team_id,
            "team_name": team_name,
            "status": status,
            "submitted_at": submitted_at,
            "started_at": started_at,
            "message_started_at": message_started_at,
            "finished_at": finished_at,
            "queue_duration_ms": max(
                0, int((started_at - submitted_at).total_seconds() * 1000)
            )
            if started_at and submitted_at
            else None,
            "execution_duration_ms": execution_duration_ms
            if execution_duration_ms is not None
            else total_duration_ms,
            "total_duration_ms": total_ms,
            "first_token_ms": first_token_ms,
            "total_tokens": max(0, int(total_tokens or 0)),
            "error_code": error_code,
            "error_category": "timeout"
            if "timeout" in (error_code or "").lower()
            else ("execution" if status in {"failed", "interrupted"} else None),
            "trace_available": True,
            "trace_complete": False,
        }
        existing = await ObservabilityRun.filter(id=run_id, source=source).update(
            **{
                key: value
                for key, value in values.items()
                if value is not None and key != "trace_complete"
            }
        )
        if not existing:
            await ObservabilityRun.create(id=run_id, source=source, **values)
        return True
    except Exception:
        logger.warning(
            "Observability summary dropped for %s run %s", source, run_id, exc_info=True
        )
        return False


async def record_workflow_submission(run: Any, workflow: Any) -> None:
    """Create the bounded run summary before a workflow task enters its queue."""
    status = getattr(run.status, "value", run.status)
    await record_run(
        run_id=run.id,
        source="workflow",
        resource_id=str(run.workflow_id) if run.workflow_id else None,
        resource_name=workflow.name if workflow else None,
        team_id=str(workflow.team_id) if workflow and workflow.team_id else None,
        team_name=None,
        status=str(status),
        submitted_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_duration_ms=run.total_duration_ms,
        total_tokens=0,
    )


async def update_run_progress(
    run_id: UUID,
    *,
    source: str,
    status: str | None = None,
    expected_status: str | None = None,
    started_at: datetime | None = None,
    message_started_at: datetime | None = None,
    first_token_ms: int | None = None,
) -> None:
    """Persist at most one allowlisted stage update; never block execution."""
    values = {
        "started_at": started_at,
        "message_started_at": message_started_at,
        "first_token_ms": first_token_ms,
    }
    updates = {key: value for key, value in values.items() if value is not None}
    if status is not None:
        updates["status"] = status
    if not updates:
        return
    try:
        query = ObservabilityRun.filter(id=run_id, source=source)
        if expected_status is not None:
            query = query.filter(status=expected_status)
        elif status is not None:
            query = query.filter(status__in=ACTIVE_RUN_STATUSES)
        await asyncio.wait_for(query.update(**updates), timeout=0.05)
    except Exception:
        logger.debug(
            "Observability progress dropped for %s run %s",
            source,
            run_id,
            exc_info=True,
        )


async def record_dependency_metrics(
    run_id: UUID,
    metrics: list[dict[str, Any]],
    *,
    truncated: bool = False,
) -> None:
    """Append a bounded batch of Agent tool spans without affecting execution."""
    incoming = [metric for metric in metrics if isinstance(metric, dict)]
    if not incoming and not truncated:
        return

    async def persist() -> None:
        query = ObservabilityRun.filter(id=run_id, source="agent")
        rows = await query.limit(1).values(
            "dependency_metrics", "dependency_metrics_truncated"
        )
        row = rows[0] if rows else None
        if row is None:
            return
        existing = row.get("dependency_metrics") or []
        if not isinstance(existing, list):
            existing = []
        existing = existing[:MAX_DEPENDENCY_METRICS_PER_RUN]
        available = MAX_DEPENDENCY_METRICS_PER_RUN - len(existing)
        stored = existing + incoming[:available]
        now_truncated = bool(row.get("dependency_metrics_truncated")) or truncated
        now_truncated = now_truncated or len(incoming) > available
        await query.update(
            dependency_metrics=stored,
            dependency_metrics_truncated=now_truncated,
        )

    try:
        await asyncio.wait_for(persist(), timeout=0.05)
    except Exception:
        logger.debug(
            "Dependency telemetry dropped for AgentRun %s", run_id, exc_info=True
        )


async def list_runs(
    *,
    period: str,
    team_id: str | None,
    source: str,
    status: str | None,
    error_category: str | None,
    run_id: str | None,
    cursor: str | None,
    limit: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    start, end = window(period, start_time, end_time)
    query = ObservabilityRun.filter(submitted_at__gte=start, submitted_at__lte=end)
    if team_id:
        query = query.filter(team_id=team_id)
    if source != "all":
        query = query.filter(source=source)
    if status:
        query = query.filter(status=status)
    if error_category:
        query = query.filter(error_category=error_category)
    if run_id:
        query = query.filter(id=str(run_id))
    if cursor:
        at, ident = _decode_cursor(cursor)
        query = query.filter(Q(submitted_at__lt=at) | Q(submitted_at=at, id__lt=ident))
    rows = await run_bounded(query.order_by("-submitted_at", "-id").limit(limit + 1))
    next_cursor = (
        _encode_cursor(rows[limit - 1].submitted_at, str(rows[limit - 1].id))
        if len(rows) > limit
        else None
    )
    items = rows[:limit]
    page_meta = _meta_for(start, end, len(items), period=period)
    if items:
        page_meta["state"] = "partial"
    return {
        "items": [_summary(row) for row in items],
        "next_cursor": next_cursor,
        "meta": page_meta,
    }


def _meta_for(
    start: datetime, end: datetime, count: int, *, period: str | None = None
) -> dict[str, Any]:
    value = meta(start, end, count)
    value["period"] = period or next(
        (
            key
            for key, seconds in PERIODS.items()
            if end - start <= timedelta(seconds=seconds)
        ),
        "7d",
    )
    return value


async def _summary_snapshot(
    period: str,
    team_id: str | None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    start, end = window(period, start_time, end_time)
    query = ObservabilityRun.filter(submitted_at__gte=start, submitted_at__lte=end)
    if team_id:
        query = query.filter(team_id=team_id)
    # Data is the compact, indexed telemetry table, not historical messages/runs.
    records = await run_bounded(
        query.order_by("-submitted_at", "-id").limit(DB_QUERY_LIMIT + 1)
    )
    records = records[:DB_QUERY_LIMIT]
    agents = [r for r in records if r.source == "agent"]
    workflows = [r for r in records if r.source == "workflow"]

    def rollup(
        rows: list[ObservabilityRun], include_first: bool = False
    ) -> dict[str, Any]:
        done = [r for r in rows if r.status in {"completed", "success", "succeeded"}]
        failed = [r for r in rows if r.status in {"failed", "interrupted", "timeout"}]
        outcomes = done + failed
        durations = sorted(
            r.total_duration_ms for r in outcomes if r.total_duration_ms is not None
        )
        result = {
            "submitted": len(rows),
            "completed": len(done),
            "failed": len(failed),
            "success_rate": len(done) / len(outcomes) if outcomes else None,
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
            "tokens": sum(r.total_tokens for r in rows),
        }
        if include_first:
            result["first_token_p95_ms"] = _percentile(
                sorted(
                    r.first_token_ms for r in outcomes if r.first_token_ms is not None
                ),
                0.95,
            )
        return result

    trend_map: dict[str, list[ObservabilityRun]] = {}
    seconds = (end - start).total_seconds()
    bucket_s = 60 if seconds <= 3600 else (900 if seconds <= 86400 else 3600)
    for record in records:
        stamp = record.submitted_at.timestamp()
        key = datetime.fromtimestamp(int(stamp // bucket_s * bucket_s), UTC).isoformat()
        trend_map.setdefault(key, []).append(record)
    trend = []
    for bucket, items in sorted(trend_map.items()):
        all_values = rollup(items, True)
        trend.append(
            {
                "bucket": bucket,
                "submitted": all_values["submitted"],
                "completed": all_values["completed"],
                "failed": all_values["failed"],
                "tokens": all_values["tokens"],
                "p95_ms": all_values["p95_ms"],
                "first_token_p95_ms": all_values["first_token_p95_ms"],
            }
        )
    # Best-effort terminal collection and lack of legacy backfill make samples partial.
    state = "partial" if records else "no_data"
    metadata = _meta_for(start, end, len(records), period=period)
    metadata["state"] = state
    return {
        "meta": metadata,
        "agents": rollup(agents, True),
        "workflows": rollup(workflows),
        "trend": trend,
        "issues": [],
    }


async def summary(
    period: str,
    team_id: str | None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    start, end = window(period, start_time, end_time)
    bounds = (start, end) if period == "custom" else (None, None)
    return await _cached_snapshot(
        ("summary", period, team_id, *bounds)
        if period == "custom"
        else ("summary", period, team_id),
        lambda: (
            _summary_snapshot(period, team_id, *bounds)
            if period == "custom"
            else _summary_snapshot(period, team_id)
        ),
    )


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lower = int(index)
    upper = min(len(values) - 1, lower + 1)
    interpolated = values[lower] + (values[upper] - values[lower]) * (index - lower)
    return int(interpolated + 0.5)


async def run_detail(source: str, run_id: UUID) -> dict[str, Any] | None:
    row = await ObservabilityRun.get_or_none(id=run_id, source=source)
    if row is None:
        return None
    end = utcnow()
    start = row.submitted_at or end
    spans = [
        {
            "span_id": str(row.id),
            "parent_span_id": None,
            "kind": "run",
            "name": row.resource_name or f"{source} run",
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "duration_ms": row.execution_duration_ms,
            "attempt": None,
            "model": row.model_name,
            "tool": None,
            "error_category": row.error_category,
            "token_usage": {"total": row.total_tokens},
            "metadata": {},
        }
    ]
    trace_complete = False
    trace_expired = False
    trace_truncated = bool(row.dependency_metrics_truncated)
    if source == "agent":
        for metric in row.dependency_metrics or []:
            if not isinstance(metric, dict):
                continue
            span_id = metric.get("span_id")
            kind = metric.get("kind")
            name = metric.get("name")
            if not span_id or kind not in {"tool", "retrieval"} or not name:
                continue
            spans.append(
                {
                    "span_id": str(span_id),
                    "parent_span_id": str(run_id),
                    "kind": str(kind),
                    "name": str(name),
                    "status": str(metric.get("status") or "unknown"),
                    "started_at": metric.get("started_at"),
                    "finished_at": metric.get("finished_at"),
                    "duration_ms": metric.get("duration_ms"),
                    "attempt": None,
                    "model": None,
                    "tool": str(name) if kind == "tool" else None,
                    "error_category": metric.get("error_category"),
                    "token_usage": None,
                    "metadata": {},
                }
            )
    if source == "workflow":
        from app.models.workflow import NodeExecution, WorkflowRun

        workflow_run = await WorkflowRun.filter(id=run_id).values("total_nodes").first()
        if workflow_run is None:
            trace_expired = True
        else:
            node_rows = await run_bounded(
                NodeExecution.filter(run_id=run_id)
                .order_by("execution_order", "id")
                .limit(101)
                .values(
                    "id",
                    "node_type",
                    "node_name",
                    "execution_order",
                    "status",
                    "queued_at",
                    "started_at",
                    "finished_at",
                    "queue_duration_ms",
                    "execution_duration_ms",
                    "model_used",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "error_type",
                    "retry_count",
                )
            )
            truncated = len(node_rows) > 100
            trace_truncated = trace_truncated or truncated
            node_rows = node_rows[:100]
            expected_nodes = int(workflow_run.get("total_nodes") or 0)
            trace_complete = not truncated and len(node_rows) == expected_nodes
            for node in node_rows:
                token_usage = {
                    key: int(node[value])
                    for key, value in (
                        ("prompt", "prompt_tokens"),
                        ("completion", "completion_tokens"),
                        ("total", "total_tokens"),
                    )
                    if node.get(value) is not None
                }
                spans.append(
                    {
                        "span_id": str(node["id"]),
                        "parent_span_id": str(run_id),
                        "kind": "workflow_node",
                        "name": str(node["node_name"]),
                        "status": str(node["status"]),
                        "started_at": node["started_at"].isoformat()
                        if node["started_at"]
                        else None,
                        "finished_at": node["finished_at"].isoformat()
                        if node["finished_at"]
                        else None,
                        "duration_ms": node["execution_duration_ms"],
                        "attempt": int(node["retry_count"] or 0),
                        "model": node["model_used"],
                        "tool": str(node["node_name"])
                        if node["node_type"] == "tool"
                        else None,
                        "error_category": node["error_type"],
                        "token_usage": token_usage or None,
                        "metadata": {
                            "node_type": str(node["node_type"]),
                            "execution_order": int(node["execution_order"]),
                            "queue_duration_ms": node["queue_duration_ms"],
                        },
                    }
                )
    return {
        "run": _summary(row),
        "spans": spans,
        "trace": {
            "complete": trace_complete,
            "expired": trace_expired,
            "truncated": trace_truncated,
            "recorded_count": len(spans),
        },
        "meta": _meta_for(start, end, len(spans)),
    }


async def _dependencies_snapshot(
    period: str,
    team_id: str | None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    start, end = window(period, start_time, end_time)
    query = ObservabilityRun.filter(
        submitted_at__gte=start, submitted_at__lte=end
    ).exclude(model_name__isnull=True)
    if team_id:
        query = query.filter(team_id=team_id)
    rows = await run_bounded(
        query.order_by("-submitted_at", "-id")
        .limit(DB_QUERY_LIMIT + 1)
        .values(
            "model_name",
            "status",
            "execution_duration_ms",
            "first_token_ms",
            "total_tokens",
        )
    )
    dependency_query = ObservabilityRun.filter(
        source="agent", submitted_at__gte=start, submitted_at__lte=end
    )
    if team_id:
        dependency_query = dependency_query.filter(team_id=team_id)
    dependency_rows = await run_bounded(
        dependency_query.order_by("-submitted_at", "-id")
        .limit(DEPENDENCY_RUN_LIMIT + 1)
        .values("dependency_metrics")
    )
    dependency_capped = len(dependency_rows) > DEPENDENCY_RUN_LIMIT
    dependency_rows = dependency_rows[:DEPENDENCY_RUN_LIMIT]
    capped = len(rows) > DB_QUERY_LIMIT
    rows = rows[:DB_QUERY_LIMIT]
    tool_groups: dict[str, list[dict[str, Any]]] = {}
    retrieval_groups: dict[str, list[dict[str, Any]]] = {}
    for row in dependency_rows:
        metrics = row.get("dependency_metrics") or []
        if not isinstance(metrics, list):
            continue
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            kind = metric.get("kind")
            name = metric.get("name")
            if kind not in {"tool", "retrieval"} or not isinstance(name, str):
                continue
            target = retrieval_groups if kind == "retrieval" else tool_groups
            target.setdefault(name, []).append(metric)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["model_name"]), []).append(row)
    model_ids: dict[str, UUID] = {}
    for reference in groups:
        try:
            model_ids[reference] = UUID(reference)
        except ValueError:
            # Legacy samples may contain a provider model name, not a UUID.
            continue
    configured_models = (
        await run_bounded(
            Model.filter(id__in=list(model_ids.values())).values(
                "id",
                "name",
                "provider",
                "provider_display_name",
            )
        )
        if model_ids
        else []
    )
    model_metadata = {str(model["id"]): model for model in configured_models}
    models = []
    for name, values in sorted(groups.items()):
        configured = model_metadata.get(str(model_ids.get(name)), {})
        provider = configured.get("provider")
        provider_label = configured.get("provider_display_name") or (
            PROVIDER_DEFAULTS.get(provider, {}).get("name") or provider
        )
        outcomes = [
            row
            for row in values
            if row["status"]
            in {"completed", "success", "succeeded", "failed", "interrupted", "timeout"}
        ]
        done = [
            row
            for row in outcomes
            if row["status"] in {"completed", "success", "succeeded"}
        ]
        failures = [
            row
            for row in outcomes
            if row["status"] in {"failed", "interrupted", "timeout"}
        ]
        durations = sorted(
            int(row["execution_duration_ms"])
            for row in outcomes
            if row["execution_duration_ms"] is not None
        )
        first_tokens = sorted(
            int(row["first_token_ms"])
            for row in outcomes
            if row["first_token_ms"] is not None
        )
        models.append(
            {
                "id": name,
                "name": configured.get("name") or ("" if name in model_ids else name),
                "provider": provider,
                "provider_display_name": provider_label,
                "requests": len(values),
                "completed": len(done),
                "failed": len(failures),
                "success_rate": len(done) / len(outcomes) if outcomes else None,
                "p50_ms": _percentile(durations, 0.5),
                "p95_ms": _percentile(durations, 0.95),
                "first_token_p95_ms": _percentile(first_tokens, 0.95),
                "tokens": sum(int(row["total_tokens"] or 0) for row in values),
                "sample_count": len(outcomes),
            }
        )

    def summarize_dependencies(
        groups: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        result = []
        for name, values in sorted(groups.items()):
            outcomes = [
                item for item in values if item.get("status") in {"completed", "failed"}
            ]
            completed = sum(item.get("status") == "completed" for item in outcomes)
            failed = sum(item.get("status") == "failed" for item in outcomes)
            durations = sorted(
                max(0, int(item["duration_ms"]))
                for item in outcomes
                if isinstance(item.get("duration_ms"), (int, float))
            )
            result.append(
                {
                    "name": name,
                    "requests": len(values),
                    "completed": completed,
                    "failed": failed,
                    "success_rate": completed / len(outcomes) if outcomes else None,
                    "p50_ms": _percentile(durations, 0.5),
                    "p95_ms": _percentile(durations, 0.95),
                    "first_token_p95_ms": None,
                    "tokens": None,
                    "sample_count": len(outcomes),
                }
            )
        return result

    metadata = _meta_for(start, end, len(rows), period=period)
    tools = summarize_dependencies(tool_groups)
    retrieval = summarize_dependencies(retrieval_groups)
    metadata["state"] = (
        "partial"
        if capped or dependency_capped or models or tools or retrieval
        else "unavailable"
    )
    return {
        "meta": metadata,
        "models": models,
        "tools": tools,
        "retrieval": retrieval,
    }


async def dependencies(
    period: str,
    team_id: str | None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    start, end = window(period, start_time, end_time)
    bounds = (start, end) if period == "custom" else (None, None)
    return await _cached_snapshot(
        ("dependencies", period, team_id, *bounds)
        if period == "custom"
        else ("dependencies", period, team_id),
        lambda: (
            _dependencies_snapshot(period, team_id, *bounds)
            if period == "custom"
            else _dependencies_snapshot(period, team_id)
        ),
    )


async def _queues_snapshot() -> dict[str, Any]:
    now = utcnow()
    known = {"default", "knowledge", "workflow", "agent", "sandbox"}
    try:
        import asyncio
        from app.core.celery import celery_app
        from app.core.redis import get_redis

        def inspect_workers(command: str):
            # Keep each blocking inspection and its reply state in one thread.
            inspector = celery_app.control.inspect(timeout=0.5)
            return getattr(inspector, command)() or {}

        active, reserved, scheduled, active_queues = await asyncio.wait_for(
            asyncio.gather(
                *(
                    asyncio.to_thread(inspect_workers, command)
                    for command in ("active", "reserved", "scheduled", "active_queues")
                )
            ),
            timeout=2.2,
        )
        if active_queues:
            for entries in active_queues.values():
                if len(known) >= 64:
                    break
                for entry in entries:
                    name = entry.get("name")
                    if name and (name in known or name.startswith("sandbox.worker.")):
                        known.add(name)
                        if len(known) >= 64:
                            break
        redis = await get_redis()
        queue_names = sorted(known)
        lengths = await asyncio.wait_for(
            asyncio.gather(
                *(redis.llen(name) for name in queue_names), return_exceptions=True
            ),
            timeout=1.2,
        )
        consumers = {name: 0 for name in queue_names}
        workers = []
        worker_ids = sorted(
            set(active) | set(reserved) | set(scheduled) | set(active_queues)
        )[:128]
        for worker_id in worker_ids:
            worker_queues = [
                str(entry.get("name", ""))
                for entry in active_queues.get(worker_id, [])[:64]
            ]
            for queue_name in worker_queues:
                consumers[queue_name] = consumers.get(queue_name, 0) + 1
            workers.append(
                {
                    "worker_id": worker_id,
                    "status": "healthy" if worker_id in active_queues else "unknown",
                    "queues": worker_queues,
                    "last_heartbeat": None,
                    "active_tasks": len(active.get(worker_id, [])),
                    "reserved_tasks": len(reserved.get(worker_id, [])),
                    "scheduled_tasks": len(scheduled.get(worker_id, [])),
                }
            )
        queue_rows = []
        for name, value in zip(queue_names, lengths):
            if isinstance(value, Exception):
                pending, state = None, "unavailable"
            else:
                pending = int(value or 0)
                state = "warning" if pending and not consumers.get(name) else "healthy"
            queue_rows.append(
                {
                    "name": name,
                    "consumers": consumers.get(name, 0),
                    "pending": pending,
                    "oldest_wait_ms": None,
                    "observed_at": now.isoformat(),
                    "state": state,
                    "trend": [],
                }
            )
        state = "fresh" if workers else "partial"
        return {
            "meta": {
                "window_start": now.isoformat(),
                "window_end": now.isoformat(),
                "sampled_at": now.isoformat(),
                "period": "",
                "state": state,
                "sample_count": len(workers),
            },
            "workers": workers,
            "queues": queue_rows,
        }
    except Exception:
        logger.warning("Queue inspection unavailable", exc_info=True)
        return {
            "meta": {
                "window_start": now.isoformat(),
                "window_end": now.isoformat(),
                "sampled_at": now.isoformat(),
                "period": "",
                "state": "unavailable",
                "sample_count": 0,
            },
            "workers": [],
            "queues": [
                {
                    "name": name,
                    "consumers": 0,
                    "pending": None,
                    "oldest_wait_ms": None,
                    "observed_at": None,
                    "state": "unavailable",
                    "trend": [],
                }
                for name in sorted(known)
            ],
        }


async def queues() -> dict[str, Any]:
    return await _cached_snapshot(("queues",), _queues_snapshot, ttl=5)


async def _celery_dependency_probe() -> dict[str, Any]:
    from app.core.celery import celery_app

    started = monotonic()
    try:
        inspector = celery_app.control.inspect(timeout=0.5)
        stats = await asyncio.wait_for(asyncio.to_thread(inspector.stats), timeout=1.5)
    except Exception:
        logger.warning("Celery dependency health probe failed", exc_info=True)
        return {
            "status": "unhealthy",
            "latency_ms": max(0, round((monotonic() - started) * 1000)),
            "detail": "Celery worker health probe failed",
        }
    if stats:
        return {
            "status": "healthy",
            "latency_ms": max(0, round((monotonic() - started) * 1000)),
            "detail": None,
        }
    return {
        "status": "unhealthy",
        "latency_ms": max(0, round((monotonic() - started) * 1000)),
        "detail": "No Celery workers responded to inspection",
    }


async def _qdrant_dependency_probe() -> dict[str, Any]:
    from app.core.config import settings

    if settings.VECTOR_BACKEND.strip().lower() != "qdrant":
        return {
            "status": "unknown",
            "latency_ms": None,
            "detail": "Qdrant is not the configured vector backend",
        }

    started = monotonic()
    try:
        from app.services.memory import _get_qdrant_client

        client = await _get_qdrant_client()
        await asyncio.wait_for(client.get_collections(), timeout=2.0)
    except Exception:
        logger.warning("Qdrant dependency health probe failed", exc_info=True)
        return {
            "status": "unhealthy",
            "latency_ms": max(0, round((monotonic() - started) * 1000)),
            "detail": "Qdrant health probe failed",
        }
    return {
        "status": "healthy",
        "latency_ms": max(0, round((monotonic() - started) * 1000)),
        "detail": None,
    }


async def _infrastructure_snapshot() -> dict[str, Any]:
    import asyncio
    import hashlib
    import re

    now = utcnow()
    from app.services.observability_instances import list_api_instances

    async def measured_health_probe(probe: Any) -> dict[str, Any]:
        started = monotonic()
        result = await probe()
        return {
            **result,
            "latency_ms": max(0, round((monotonic() - started) * 1000)),
        }

    async def collect_health() -> dict[str, Any]:
        try:
            from app.services import admin_observability as legacy_health

            database, redis = await asyncio.wait_for(
                asyncio.gather(
                    measured_health_probe(legacy_health._database_health),
                    measured_health_probe(legacy_health._redis_health),
                ),
                timeout=2.0,
            )
            return {
                "database": database,
                "redis": redis,
            }
        except Exception:
            logger.warning("Infrastructure health probe unavailable", exc_info=True)
            return {}

    async def collect_slow_queries() -> dict[str, Any]:
        try:
            from app.services import admin_observability as legacy_health

            return await asyncio.wait_for(
                legacy_health.get_slow_queries(0, 1, 20), timeout=2.0
            )
        except Exception:
            logger.info("Slow query statistics unavailable", exc_info=True)
            return {"available": False, "items": []}

    health, celery, qdrant, slow_payload, registry = await asyncio.gather(
        collect_health(),
        _celery_dependency_probe(),
        _qdrant_dependency_probe(),
        collect_slow_queries(),
        list_api_instances(),
    )

    def status_of(value: Any) -> str:
        if not isinstance(value, dict):
            return "unknown"
        state = str(value.get("status", "unknown")).lower()
        return state if state in {"healthy", "degraded", "unhealthy"} else "unknown"

    db = health.get("database")
    redis = health.get("redis")
    deps = []
    for name, value in (
        ("postgresql", db),
        ("redis", redis),
        ("celery", celery),
        ("qdrant", qdrant),
    ):
        status = status_of(value)
        deps.append(
            {
                "name": name,
                "status": status,
                "observed_at": now.isoformat() if value else None,
                "latency_ms": value.get("latency_ms")
                if isinstance(value, dict)
                else None,
                "detail": value.get("detail")
                if isinstance(value, dict) and value.get("detail")
                else None
                if status != "unknown"
                else "Health probe unavailable",
            }
        )
    instances = registry["instances"]
    items = []
    for row in slow_payload.get("items", [])[:20]:
        raw = str(row.get("query") or "")
        safe = re.sub(r"'(?:''|[^'])*'", "'?'", raw)
        safe = re.sub(r"\b\d+(?:\.\d+)?\b", "?", safe)
        safe = re.sub(r"\s+", " ", safe).strip()[:300]
        items.append(
            {
                "query_id": hashlib.sha256(raw.encode()).hexdigest()[:16],
                "query": safe,
                "calls": int(row.get("calls") or 0),
                "mean_ms": row.get("avg_ms"),
                "max_ms": row.get("max_ms"),
                "total_ms": row.get("total_ms"),
            }
        )
    available = bool(slow_payload.get("available"))
    return {
        "meta": {
            "window_start": now.isoformat(),
            "window_end": now.isoformat(),
            "sampled_at": now.isoformat(),
            "period": "",
            "state": (
                "fresh"
                if health and registry["available"]
                else "partial"
                if health or instances
                else "unavailable"
            ),
            "sample_count": len(deps),
        },
        "instances": instances,
        "dependencies": deps,
        "slow_queries": {"available": available, "reset_at": None, "items": items},
    }


async def infrastructure() -> dict[str, Any]:
    return await _cached_snapshot(("infrastructure",), _infrastructure_snapshot, ttl=5)


async def evaluate_alert_rules() -> None:
    """Evaluate bounded recent samples on admin alert reads; no background-worker claim."""
    from tortoise.transactions import in_transaction

    now = utcnow()
    for rule in await ObservabilityAlertRule.filter(enabled=True).limit(64):
        source = "agent" if rule.id.startswith("agent-") else "workflow"
        rows = await run_bounded(
            ObservabilityRun.filter(
                source=source,
                submitted_at__gte=now
                - timedelta(
                    seconds=max(
                        rule.evaluation_window_seconds, rule.recovery_window_seconds
                    )
                ),
                submitted_at__lte=now,
            )
            .order_by("-submitted_at", "-id")
            .limit(1000)
        )
        current = [
            r
            for r in rows
            if r.submitted_at
            and r.submitted_at
            >= now - timedelta(seconds=rule.evaluation_window_seconds)
        ]
        outcomes = [
            r
            for r in current
            if r.status
            in {"completed", "success", "succeeded", "failed", "interrupted", "timeout"}
        ]
        if len(outcomes) < 10:
            continue
        failures = [
            r for r in outcomes if r.status in {"failed", "interrupted", "timeout"}
        ]
        rate = len(failures) / len(outcomes)
        async with in_transaction() as conn:
            locked_rule = (
                await ObservabilityAlertRule.filter(id=rule.id)
                .using_db(conn)
                .select_for_update()
                .first()
            )
            if locked_rule is None or not locked_rule.enabled:
                continue
            active = (
                await ObservabilityAlertEvent.filter(rule_id=rule.id, status="active")
                .using_db(conn)
                .first()
            )
            if rate >= locked_rule.threshold and active is None:
                await ObservabilityAlertEvent.create(
                    id=uuid4(),
                    rule_id=rule.id,
                    kind=rule.id,
                    severity="warning",
                    title=rule.name,
                    detail=f"Observed failure rate {rate:.0%} exceeded configured threshold.",
                    affected_count=len(failures),
                    status="active",
                    opened_at=now,
                    using_db=conn,
                )
            elif active is not None and rate < locked_rule.threshold:
                recovery = [
                    r
                    for r in rows
                    if r.source == source
                    and r.submitted_at
                    >= now - timedelta(seconds=locked_rule.recovery_window_seconds)
                    and r.status
                    in {
                        "completed",
                        "success",
                        "succeeded",
                        "failed",
                        "interrupted",
                        "timeout",
                    }
                ]
                if len(recovery) >= 10 and not any(
                    r.status in {"failed", "interrupted", "timeout"} for r in recovery
                ):
                    active.status = "resolved"
                    active.resolved_at = now
                    await active.save(
                        using_db=conn, update_fields=["status", "resolved_at"]
                    )


async def alert_rules() -> list[dict[str, Any]]:
    # Idempotent, bounded seed. Rules are inert until configured by an admin.
    seeds = (
        ("agent-failure-rate", "Agent failure rate", 0.2),
        ("workflow-failure-rate", "Workflow failure rate", 0.2),
    )
    for ident, name, threshold in seeds:
        await ObservabilityAlertRule.get_or_create(
            id=ident,
            defaults={
                "name": name,
                "threshold": threshold,
                "enabled": False,
                "evaluation_window_seconds": 300,
                "recovery_window_seconds": 600,
            },
        )
    rows = await ObservabilityAlertRule.all().order_by("id")
    return [
        {
            "id": r.id,
            "name": r.name,
            "threshold": r.threshold,
            "enabled": r.enabled,
            "evaluation_window_seconds": r.evaluation_window_seconds,
            "recovery_window_seconds": r.recovery_window_seconds,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


async def update_rule(rule_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    row = await ObservabilityAlertRule.get_or_none(id=rule_id)
    if row is None:
        return None
    for key in (
        "threshold",
        "enabled",
        "evaluation_window_seconds",
        "recovery_window_seconds",
    ):
        if key in values:
            setattr(row, key, values[key])
    await row.save(
        update_fields=[
            k
            for k in values
            if k
            in {
                "threshold",
                "enabled",
                "evaluation_window_seconds",
                "recovery_window_seconds",
            }
        ]
        + ["updated_at"]
    )
    return {
        "id": row.id,
        "name": row.name,
        "threshold": row.threshold,
        "enabled": row.enabled,
        "evaluation_window_seconds": row.evaluation_window_seconds,
        "recovery_window_seconds": row.recovery_window_seconds,
        "updated_at": row.updated_at.isoformat(),
    }


def _alert_event(row: ObservabilityAlertEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "rule_id": row.rule_id,
        "kind": row.kind,
        "severity": row.severity,
        "title": row.title,
        "detail": row.detail,
        "affected_count": row.affected_count,
        "status": row.status,
        "opened_at": row.opened_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "acknowledged_at": row.acknowledged_at.isoformat()
        if row.acknowledged_at
        else None,
        "silenced_until": row.silenced_until.isoformat()
        if row.silenced_until
        else None,
    }


async def list_alerts(status: str, cursor: str | None, limit: int) -> dict[str, Any]:
    query = ObservabilityAlertEvent.all()
    if status != "all":
        query = query.filter(status=status)
    if cursor:
        try:
            stamp, ident = _decode_cursor(cursor)
        except ValueError:
            raise
        query = query.filter(Q(opened_at__lt=stamp) | Q(opened_at=stamp, id__lt=ident))
    rows = await query.order_by("-opened_at", "-id").limit(limit + 1)
    next_cursor = (
        _encode_cursor(rows[limit - 1].opened_at, str(rows[limit - 1].id))
        if len(rows) > limit
        else None
    )
    items = [_alert_event(row) for row in rows[:limit]]
    now = utcnow()
    metadata = _meta_for(now - timedelta(days=RETENTION_DAYS), now, len(items))
    metadata["period"] = "30d"
    if next_cursor:
        metadata["state"] = "partial"
    return {"items": items, "next_cursor": next_cursor, "meta": metadata}


async def acknowledge_alert(alert_id: UUID, user_id: str) -> dict[str, Any] | None:
    now = utcnow()
    changed = await ObservabilityAlertEvent.filter(id=alert_id, status="active").update(
        acknowledged_at=now, acknowledged_by_id=user_id
    )
    row = await ObservabilityAlertEvent.get_or_none(id=alert_id) if changed else None
    return _alert_event(row) if row else None


async def silence_alert(alert_id: UUID, duration_seconds: int) -> dict[str, Any] | None:
    changed = await ObservabilityAlertEvent.filter(id=alert_id, status="active").update(
        silenced_until=utcnow() + timedelta(seconds=duration_seconds)
    )
    row = await ObservabilityAlertEvent.get_or_none(id=alert_id) if changed else None
    return _alert_event(row) if row else None


async def retain() -> int:
    """Delete expired rows in bounded batches; safe for periodic controller invocation."""
    cutoff = utcnow() - timedelta(days=RETENTION_DAYS)
    deleted_runs = 0
    for _ in range(RETENTION_BATCHES_PER_CYCLE):
        run_ids = (
            await ObservabilityRun.filter(submitted_at__lt=cutoff)
            .order_by("submitted_at")
            .limit(RETENTION_BATCH_SIZE)
            .values_list("id", flat=True)
        )
        if not run_ids:
            break
        deleted = int(await ObservabilityRun.filter(id__in=list(run_ids)).delete())
        deleted_runs += deleted
        if deleted < 1 or len(run_ids) < RETENTION_BATCH_SIZE:
            break

    deleted_alerts = 0
    for _ in range(RETENTION_BATCHES_PER_CYCLE):
        alert_ids = (
            await ObservabilityAlertEvent.filter(
                opened_at__lt=cutoff, status="resolved"
            )
            .order_by("opened_at")
            .limit(RETENTION_BATCH_SIZE)
            .values_list("id", flat=True)
        )
        if not alert_ids:
            break
        deleted = int(
            await ObservabilityAlertEvent.filter(id__in=list(alert_ids)).delete()
        )
        deleted_alerts += deleted
        if deleted < 1 or len(alert_ids) < RETENTION_BATCH_SIZE:
            break
    return deleted_runs + deleted_alerts
