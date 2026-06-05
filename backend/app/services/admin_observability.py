from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from tortoise import Tortoise

from app.core.celery import celery_app
from app.core.redis import get_redis
from app.core.timezone import now, to_utc
from app.models.agent import MessageRoundStatus
from app.models.workflow import RunStatus

try:  # pragma: no cover - exercised when dependency is installed
    import psutil
except ImportError:  # pragma: no cover - graceful runtime degradation
    psutil = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 30
CACHE_PREFIX = "admin:observability:v1"
HEALTH_SNAPSHOT_KEY = f"{CACHE_PREFIX}:system:health:snapshots"
VALID_TIME_RANGES = {"7d", "30d", "90d", "all"}
VALID_GRANULARITIES = {"hour", "day"}
WORKER_QUEUES = ("default", "workflow", "sandbox")


def normalize_time_range(time_range: str) -> tuple[datetime | None, datetime]:
    end_time = to_utc(now())
    if time_range not in VALID_TIME_RANGES:
        time_range = "30d"
    if time_range == "all":
        return None, end_time
    days = int(time_range.removesuffix("d"))
    return end_time - timedelta(days=days), end_time


def normalize_granularity(time_range: str, granularity: str | None = None) -> str:
    if granularity in VALID_GRANULARITIES:
        return granularity
    return "hour" if time_range == "7d" else "day"


def continuous_percentile(
    values: Sequence[float | int], percentile: float
) -> float | None:
    if not values:
        return None
    sorted_values = sorted(float(value) for value in values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def percentile_payload(values: Sequence[float | int]) -> dict[str, int | None]:
    return {
        "p50_ms": _round_nullable(continuous_percentile(values, 0.50)),
        "p90_ms": _round_nullable(continuous_percentile(values, 0.90)),
        "p95_ms": _round_nullable(continuous_percentile(values, 0.95)),
        "p99_ms": _round_nullable(continuous_percentile(values, 0.99)),
    }


def extract_token_total(token_usage: Any) -> int:
    if not isinstance(token_usage, dict):
        return 0
    for key in ("total", "total_tokens"):
        value = token_usage.get(key)
        if isinstance(value, int | float):
            return int(value)
    total = 0
    for key in ("prompt", "completion", "prompt_tokens", "completion_tokens"):
        value = token_usage.get(key)
        if isinstance(value, int | float):
            total += int(value)
    return total


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 2)


async def cached_payload(
    endpoint: str,
    params: dict[str, Any],
    producer: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    cache_key = _cache_key(endpoint, params)
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Observability cache read failed: %s", exc)

    data = await producer()

    try:
        redis = await get_redis()
        await redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(data, default=str))
    except Exception as exc:
        logger.warning("Observability cache write failed: %s", exc)

    return data


async def get_overview(time_range: str) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    agent_rows = await _agent_message_rows(start_time, end_time)
    workflow_rows = await _workflow_run_rows(start_time, end_time)

    agent_count = len(agent_rows)
    workflow_count = len(workflow_rows)
    total_requests = agent_count + workflow_count
    agent_success = sum(
        1
        for row in agent_rows
        if row.get("round_status") == MessageRoundStatus.COMPLETED.value
    )
    workflow_success = sum(
        1 for row in workflow_rows if row.get("status") == RunStatus.SUCCESS.value
    )
    workflow_timeout = sum(
        1 for row in workflow_rows if row.get("status") == RunStatus.TIMEOUT.value
    )
    agent_errors = sum(
        1
        for row in agent_rows
        if row.get("round_status") == MessageRoundStatus.ERROR.value
    )
    durations = [
        int(row["duration_ms"])
        for row in [*agent_rows, *workflow_rows]
        if row.get("duration_ms") is not None
    ]
    first_token_durations = [
        int(row["first_token_ms"])
        for row in agent_rows
        if row.get("first_token_ms") is not None
    ]
    total_tokens = sum(
        int(row.get("tokens") or 0) for row in [*agent_rows, *workflow_rows]
    )

    recent_start = end_time - timedelta(seconds=60)
    recent_count = sum(
        1
        for row in [*agent_rows, *workflow_rows]
        if _coerce_datetime(row.get("created_at")) >= recent_start
    )
    bucket_counts: dict[str, int] = {}
    for row in [*agent_rows, *workflow_rows]:
        created_at = _coerce_datetime(row.get("created_at"))
        bucket = created_at.replace(minute=0, second=0, microsecond=0).isoformat()
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    return {
        "time_range": time_range,
        "generated_at": end_time.isoformat(),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "totals": {
            "agent_requests": agent_count,
            "workflow_runs": workflow_count,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
        },
        "rates": {
            "agent_success_rate": safe_rate(agent_success, agent_count),
            "workflow_success_rate": safe_rate(workflow_success, workflow_count),
            "overall_success_rate": safe_rate(
                agent_success + workflow_success, total_requests
            ),
            "timeout_rate": safe_rate(workflow_timeout + agent_errors, total_requests),
        },
        "latency": percentile_payload(durations),
        "ttft": percentile_payload(first_token_durations),
        "throughput": {
            "current_qps": round(recent_count / 60, 3),
            "peak_hourly_requests": max(bucket_counts.values()) if bucket_counts else 0,
        },
    }


async def get_agents(
    time_range: str,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    rows = await _agent_performance_rows(start_time, end_time)
    rows = sorted(
        rows,
        key=lambda row: row.get(_agent_sort_key(sort_by)) or 0,
        reverse=sort_order != "asc",
    )
    return _paginate(rows, page, page_size, {"time_range": time_range})


async def get_agent_detail(agent_id: UUID, time_range: str) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    rows = [
        row
        for row in await _agent_performance_rows(start_time, end_time)
        if str(row.get("agent_id")) == str(agent_id)
    ]
    trend = await _agent_trend_rows(
        agent_id, start_time, end_time, normalize_granularity(time_range)
    )
    return {
        "time_range": time_range,
        "agent": rows[0] if rows else None,
        "trend": trend,
    }


async def get_workflows(
    time_range: str,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    rows = await _workflow_performance_rows(start_time, end_time)
    rows = sorted(
        rows,
        key=lambda row: row.get(_workflow_sort_key(sort_by)) or 0,
        reverse=sort_order != "asc",
    )
    return _paginate(rows, page, page_size, {"time_range": time_range})


async def get_workflow_detail(workflow_id: UUID, time_range: str) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    rows = [
        row
        for row in await _workflow_performance_rows(start_time, end_time)
        if str(row.get("workflow_id")) == str(workflow_id)
    ]
    trend = await _workflow_trend_rows(
        workflow_id, start_time, end_time, normalize_granularity(time_range)
    )
    nodes = await _workflow_node_rows(workflow_id, start_time, end_time)
    return {
        "time_range": time_range,
        "workflow": rows[0] if rows else None,
        "trend": trend,
        "nodes": nodes,
    }


async def get_timeouts(
    time_range: str, source: str, page: int, page_size: int
) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    events: list[dict[str, Any]] = []
    if source in {"all", "workflow"}:
        for row in await _workflow_timeout_rows(start_time, end_time):
            events.append(
                {
                    "source": "workflow",
                    "entity_id": row.get("workflow_id"),
                    "entity_name": row.get("workflow_name") or "Unknown",
                    "model": None,
                    "timeout_type": "workflow",
                    "created_at": _serialize_datetime(row.get("created_at")),
                    "duration_ms": row.get("duration_ms"),
                    "status": row.get("status"),
                }
            )
    if source in {"all", "agent"}:
        for row in await _agent_timeout_like_rows(start_time, end_time):
            events.append(
                {
                    "source": "agent",
                    "entity_id": row.get("agent_id"),
                    "entity_name": row.get("agent_name") or "Unknown",
                    "model": row.get("model_used"),
                    "timeout_type": "unknown",
                    "created_at": _serialize_datetime(row.get("created_at")),
                    "duration_ms": row.get("duration_ms"),
                    "status": row.get("round_status"),
                }
            )
    events.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    distribution: dict[str, int] = {}
    for event in events:
        key = str(event["source"])
        distribution[key] = distribution.get(key, 0) + 1
    payload = _paginate(events, page, page_size, {"time_range": time_range})
    payload.update(
        {
            "distribution": distribution,
            "agent_timeout_type_available": False,
            "note": "Agent timeout subtype is unavailable for historical messages.",
        }
    )
    return payload


async def get_throughput(time_range: str, granularity: str | None) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    bucket = normalize_granularity(time_range, granularity)
    agent_rows = await _bucket_count_rows(
        "messages",
        "created_at",
        start_time,
        end_time,
        bucket,
        "round_role = 'assistant_final' AND is_round_canonical = true",
    )
    workflow_rows = await _bucket_count_rows(
        "workflow_runs", "created_at", start_time, end_time, bucket
    )
    buckets = _merge_count_buckets(agent_rows, workflow_rows)
    running_workflows = await _scalar_count(
        "workflow_runs", "status = $1", [RunStatus.RUNNING.value]
    )
    current_qps = await _current_qps(end_time)
    return {
        "time_range": time_range,
        "granularity": bucket,
        "current": {
            "qps": current_qps,
            "tps": current_qps,
            "running_workflows": running_workflows,
        },
        "buckets": buckets,
    }


async def get_tokens(time_range: str) -> dict[str, Any]:
    start_time, end_time = normalize_time_range(time_range)
    agent_rows = await _agent_message_rows(start_time, end_time)
    workflow_rows = await _workflow_run_rows(start_time, end_time)
    by_model: dict[str, int] = {}
    for row in agent_rows:
        model = str(row.get("model_used") or "unknown")
        by_model[model] = by_model.get(model, 0) + int(row.get("tokens") or 0)
    agent_tokens = sum(int(row.get("tokens") or 0) for row in agent_rows)
    workflow_tokens = sum(int(row.get("tokens") or 0) for row in workflow_rows)
    return {
        "time_range": time_range,
        "total_tokens": agent_tokens + workflow_tokens,
        "by_source": [
            {"source": "agent", "tokens": agent_tokens},
            {"source": "workflow", "tokens": workflow_tokens},
        ],
        "by_model": [
            {"model": model, "tokens": tokens}
            for model, tokens in sorted(
                by_model.items(), key=lambda item: item[1], reverse=True
            )
        ],
    }


async def get_system_health() -> dict[str, Any]:
    generated_at = to_utc(now())
    health = {
        "generated_at": generated_at.isoformat(),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cpu": _cpu_health(),
        "memory": _memory_health(),
        "disk": _disk_health(),
        "database": await _database_health(),
        "redis": await _redis_health(),
        "workers": await get_workers(),
    }
    await _store_health_snapshot(health)
    return health


async def get_system_trend() -> dict[str, Any]:
    try:
        redis: Any = await get_redis()
        raw_items = await redis.lrange(HEALTH_SNAPSHOT_KEY, 0, 120)
    except Exception as exc:
        logger.warning("System health trend unavailable: %s", exc)
        raw_items = []
    items = []
    for raw in raw_items:
        try:
            items.append(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            continue
    items.reverse()
    return {"items": items}


async def get_slow_queries(
    threshold_ms: int, page: int, page_size: int
) -> dict[str, Any]:
    conn = Tortoise.get_connection("default")
    try:
        _, extension_rows = await conn.execute_query(
            "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"
        )
        if not extension_rows:
            return {
                "available": False,
                "reason": "pg_stat_statements extension is not created in the database",
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }

        _, rows = await conn.execute_query(
            """
            SELECT
                query,
                mean_exec_time AS avg_ms,
                max_exec_time AS max_ms,
                calls,
                rows,
                total_exec_time AS total_ms
            FROM pg_stat_statements
            WHERE mean_exec_time >= $1
            ORDER BY mean_exec_time DESC
            LIMIT $2 OFFSET $3
            """,
            [threshold_ms, min(page_size, 100), max(page - 1, 0) * page_size],
        )
    except Exception as exc:
        logger.info("pg_stat_statements unavailable: %s", exc)
        reason = str(exc)
        if "must be loaded via shared_preload_libraries" in reason:
            reason = "pg_stat_statements must be added to shared_preload_libraries and PostgreSQL must be restarted"
        elif "permission denied" in reason.lower():
            reason = "database user cannot create or read pg_stat_statements"
        else:
            reason = "pg_stat_statements is not available"
        return {
            "available": False,
            "reason": reason,
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }
    return {
        "available": True,
        "reason": None,
        "items": [_normalize_row(row) for row in rows],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }


async def get_workers() -> dict[str, Any]:
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active, reserved, scheduled, stats = await asyncio.to_thread(
            lambda: (
                inspect.active() or {},
                inspect.reserved() or {},
                inspect.scheduled() or {},
                inspect.stats() or {},
            )
        )
        active_count = sum(len(tasks) for tasks in active.values())
        reserved_count = sum(len(tasks) for tasks in reserved.values())
        scheduled_count = sum(len(tasks) for tasks in scheduled.values())
        queue_lengths = await _queue_lengths()
        return {
            "status": "healthy" if stats else "unknown",
            "worker_count": len(stats),
            "active_tasks": active_count,
            "reserved_tasks": reserved_count,
            "scheduled_tasks": scheduled_count,
            "queues": queue_lengths,
        }
    except Exception as exc:
        logger.warning("Celery worker inspection failed: %s", exc)
        return {
            "status": "unknown",
            "worker_count": 0,
            "active_tasks": 0,
            "reserved_tasks": 0,
            "scheduled_tasks": 0,
            "queues": [],
            "error": str(exc),
        }


async def _agent_message_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("m.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT
            m.created_at,
            m.duration_ms,
            m.first_token_ms,
            m.round_status,
            m.model_used,
            COALESCE(
                (m.token_usage->>'total')::bigint,
                (m.token_usage->>'total_tokens')::bigint,
                COALESCE((m.token_usage->>'prompt')::bigint, (m.token_usage->>'prompt_tokens')::bigint, 0)
                  + COALESCE((m.token_usage->>'completion')::bigint, (m.token_usage->>'completion_tokens')::bigint, 0),
                0
            ) AS tokens
        FROM messages m
        WHERE {where}
          AND m.round_role = 'assistant_final'
          AND m.is_round_canonical = true
        """,
        params,
    )
    return [_normalize_row(row) for row in rows]


async def _workflow_run_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("wr.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT
            wr.created_at,
            wr.total_duration_ms AS duration_ms,
            wr.status,
            COALESCE(
                (wr.total_token_usage->>'total')::bigint,
                (wr.total_token_usage->>'total_tokens')::bigint,
                COALESCE((wr.total_token_usage->>'prompt')::bigint, (wr.total_token_usage->>'prompt_tokens')::bigint, 0)
                  + COALESCE((wr.total_token_usage->>'completion')::bigint, (wr.total_token_usage->>'completion_tokens')::bigint, 0),
                0
            ) AS tokens
        FROM workflow_runs wr
        WHERE {where}
        """,
        params,
    )
    return [_normalize_row(row) for row in rows]


async def _agent_performance_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("m.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT
            a.id AS agent_id,
            a.name AS agent_name,
            t.name AS team_name,
            COUNT(m.id)::int AS request_count,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p50_ms,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p90_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p95_ms,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p99_ms,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.first_token_ms) FILTER (WHERE m.first_token_ms IS NOT NULL) AS ttft_p50_ms,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.first_token_ms) FILTER (WHERE m.first_token_ms IS NOT NULL) AS ttft_p90_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY m.first_token_ms) FILTER (WHERE m.first_token_ms IS NOT NULL) AS ttft_p95_ms,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY m.first_token_ms) FILTER (WHERE m.first_token_ms IS NOT NULL) AS ttft_p99_ms,
            SUM(CASE WHEN m.round_status = 'completed' THEN 1 ELSE 0 END)::int AS success_count,
            SUM(CASE WHEN m.round_status = 'error' THEN 1 ELSE 0 END)::int AS error_count,
            0::int AS timeout_count,
            SUM(
                COALESCE(
                    (m.token_usage->>'total')::bigint,
                    (m.token_usage->>'total_tokens')::bigint,
                    COALESCE((m.token_usage->>'prompt')::bigint, (m.token_usage->>'prompt_tokens')::bigint, 0)
                    + COALESCE((m.token_usage->>'completion')::bigint, (m.token_usage->>'completion_tokens')::bigint, 0),
                    0
                )
            )::bigint AS total_tokens
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        LEFT JOIN agents a ON a.id = c.agent_id
        LEFT JOIN teams t ON t.id = a.team_id
        WHERE {where}
          AND m.round_role = 'assistant_final'
          AND m.is_round_canonical = true
          AND c.agent_id IS NOT NULL
        GROUP BY a.id, a.name, t.name
        """,
        params,
    )
    return [_decorate_performance_row(row, "request_count") for row in rows]


async def _workflow_performance_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("wr.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT
            w.id AS workflow_id,
            w.name AS workflow_name,
            t.name AS team_name,
            COUNT(wr.id)::int AS run_count,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p50_ms,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p90_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p95_ms,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p99_ms,
            SUM(CASE WHEN wr.status = 'success' THEN 1 ELSE 0 END)::int AS success_count,
            SUM(CASE WHEN wr.status = 'failed' THEN 1 ELSE 0 END)::int AS error_count,
            SUM(CASE WHEN wr.status = 'timeout' THEN 1 ELSE 0 END)::int AS timeout_count,
            SUM(wr.failed_nodes)::int AS failed_nodes,
            AVG(wr.total_nodes) AS avg_nodes,
            SUM(
                COALESCE(
                    (wr.total_token_usage->>'total')::bigint,
                    (wr.total_token_usage->>'total_tokens')::bigint,
                    COALESCE((wr.total_token_usage->>'prompt')::bigint, (wr.total_token_usage->>'prompt_tokens')::bigint, 0)
                    + COALESCE((wr.total_token_usage->>'completion')::bigint, (wr.total_token_usage->>'completion_tokens')::bigint, 0),
                    0
                )
            )::bigint AS total_tokens
        FROM workflow_runs wr
        LEFT JOIN workflows w ON w.id = wr.workflow_id
        LEFT JOIN teams t ON t.id = w.team_id
        WHERE {where}
        GROUP BY w.id, w.name, t.name
        """,
        params,
    )
    return [_decorate_performance_row(row, "run_count") for row in rows]


async def _agent_trend_rows(
    agent_id: UUID, start_time: datetime | None, end_time: datetime, granularity: str
) -> list[dict[str, Any]]:
    where, params = _time_where("m.created_at", start_time, end_time, start_index=3)
    _, rows = await _execute(
        f"""
        SELECT
            date_trunc($1, m.created_at) AS bucket,
            COUNT(m.id)::int AS request_count,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p50_ms,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p90_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL) AS p95_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY m.first_token_ms) FILTER (WHERE m.first_token_ms IS NOT NULL) AS ttft_p95_ms,
            SUM(CASE WHEN m.round_status = 'completed' THEN 1 ELSE 0 END)::int AS success_count,
            SUM(CASE WHEN m.round_status = 'error' THEN 1 ELSE 0 END)::int AS error_count
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.agent_id = $2
          AND {where}
          AND m.round_role = 'assistant_final'
          AND m.is_round_canonical = true
        GROUP BY bucket
        ORDER BY bucket
        """,
        [granularity, str(agent_id), *params],
    )
    return [_decorate_bucket_row(row, "request_count") for row in rows]


async def _workflow_trend_rows(
    workflow_id: UUID, start_time: datetime | None, end_time: datetime, granularity: str
) -> list[dict[str, Any]]:
    where, params = _time_where("wr.created_at", start_time, end_time, start_index=3)
    _, rows = await _execute(
        f"""
        SELECT
            date_trunc($1, wr.created_at) AS bucket,
            COUNT(wr.id)::int AS run_count,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p50_ms,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p90_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY wr.total_duration_ms) FILTER (WHERE wr.total_duration_ms IS NOT NULL) AS p95_ms,
            SUM(CASE WHEN wr.status = 'success' THEN 1 ELSE 0 END)::int AS success_count,
            SUM(CASE WHEN wr.status = 'timeout' THEN 1 ELSE 0 END)::int AS timeout_count,
            SUM(wr.failed_nodes)::int AS failed_nodes
        FROM workflow_runs wr
        WHERE wr.workflow_id = $2
          AND {where}
        GROUP BY bucket
        ORDER BY bucket
        """,
        [granularity, str(workflow_id), *params],
    )
    return [_decorate_bucket_row(row, "run_count") for row in rows]


async def _workflow_node_rows(
    workflow_id: UUID, start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("wr.created_at", start_time, end_time, start_index=2)
    _, rows = await _execute(
        f"""
        SELECT
            ne.node_type,
            COUNT(ne.id)::int AS execution_count,
            SUM(CASE WHEN ne.status = 'failed' THEN 1 ELSE 0 END)::int AS failed_count,
            AVG(ne.execution_duration_ms) AS avg_duration_ms
        FROM workflow_node_executions ne
        JOIN workflow_runs wr ON wr.id = ne.run_id
        WHERE wr.workflow_id = $1
          AND {where}
        GROUP BY ne.node_type
        ORDER BY execution_count DESC
        LIMIT 20
        """,
        [str(workflow_id), *params],
    )
    return [_normalize_row(row) for row in rows]


async def _workflow_timeout_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("wr.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT wr.created_at, wr.status, wr.total_duration_ms AS duration_ms, w.id AS workflow_id, w.name AS workflow_name
        FROM workflow_runs wr
        LEFT JOIN workflows w ON w.id = wr.workflow_id
        WHERE {where} AND wr.status = 'timeout'
        ORDER BY wr.created_at DESC
        LIMIT 1000
        """,
        params,
    )
    return [_normalize_row(row) for row in rows]


async def _agent_timeout_like_rows(
    start_time: datetime | None, end_time: datetime
) -> list[dict[str, Any]]:
    where, params = _time_where("m.created_at", start_time, end_time)
    _, rows = await _execute(
        f"""
        SELECT m.created_at, m.duration_ms, m.round_status, m.model_used, a.id AS agent_id, a.name AS agent_name
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        LEFT JOIN agents a ON a.id = c.agent_id
        WHERE {where}
          AND m.round_role = 'assistant_final'
          AND m.is_round_canonical = true
          AND m.round_status = 'error'
        ORDER BY m.created_at DESC
        LIMIT 1000
        """,
        params,
    )
    return [_normalize_row(row) for row in rows]


async def _bucket_count_rows(
    table: str,
    created_column: str,
    start_time: datetime | None,
    end_time: datetime,
    granularity: str,
    extra_where: str | None = None,
) -> list[dict[str, Any]]:
    where, params = _time_where(created_column, start_time, end_time, start_index=2)
    if extra_where:
        where = f"{where} AND {extra_where}"
    _, rows = await _execute(
        f"""
        SELECT date_trunc($1, {created_column}) AS bucket, COUNT(*)::int AS count
        FROM {table}
        WHERE {where}
        GROUP BY bucket
        ORDER BY bucket
        """,
        [granularity, *params],
    )
    return [_normalize_row(row) for row in rows]


async def _current_qps(end_time: datetime) -> float:
    start_time = end_time - timedelta(seconds=60)
    agent_count = await _scalar_count(
        "messages",
        "created_at >= $1 AND created_at < $2 AND round_role = 'assistant_final' AND is_round_canonical = true",
        [start_time, end_time],
    )
    workflow_count = await _scalar_count(
        "workflow_runs", "created_at >= $1 AND created_at < $2", [start_time, end_time]
    )
    return round((agent_count + workflow_count) / 60, 3)


async def _scalar_count(table: str, where: str, params: list[Any]) -> int:
    _, rows = await _execute(
        f"SELECT COUNT(*)::int AS count FROM {table} WHERE {where}", params
    )
    return int(rows[0].get("count") or 0) if rows else 0


async def _execute(query: str, params: list[Any]) -> tuple[int, list[dict[str, Any]]]:
    conn = Tortoise.get_connection("default")
    row_count, rows = await conn.execute_query(query, params)
    return row_count, list(rows)


def _time_where(
    column: str,
    start_time: datetime | None,
    end_time: datetime,
    start_index: int = 1,
) -> tuple[str, list[Any]]:
    if start_time is None:
        return f"{column} < ${start_index}", [end_time]
    return f"{column} >= ${start_index} AND {column} < ${start_index + 1}", [
        start_time,
        end_time,
    ]


def _decorate_performance_row(row: dict[str, Any], count_key: str) -> dict[str, Any]:
    normalized = _normalize_row(row)
    count = int(normalized.get(count_key) or 0)
    success_count = int(normalized.get("success_count") or 0)
    timeout_count = int(normalized.get("timeout_count") or 0)
    total_tokens = int(normalized.get("total_tokens") or 0)
    for key in (
        "p50_ms",
        "p90_ms",
        "p95_ms",
        "p99_ms",
        "ttft_p50_ms",
        "ttft_p90_ms",
        "ttft_p95_ms",
        "ttft_p99_ms",
    ):
        if key in normalized:
            normalized[key] = _round_nullable(normalized.get(key))
    normalized["success_rate"] = safe_rate(success_count, count)
    normalized["timeout_rate"] = safe_rate(timeout_count, count)
    normalized["avg_tokens"] = round(total_tokens / count, 2) if count else 0
    return normalized


def _decorate_bucket_row(row: dict[str, Any], count_key: str) -> dict[str, Any]:
    normalized = _normalize_row(row)
    count = int(normalized.get(count_key) or 0)
    success_count = int(normalized.get("success_count") or 0)
    for key in ("p50_ms", "p90_ms", "p95_ms", "ttft_p95_ms"):
        normalized[key] = _round_nullable(normalized.get(key))
    normalized["success_rate"] = safe_rate(success_count, count)
    normalized["bucket"] = _serialize_datetime(normalized.get("bucket"))
    return normalized


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialize_value(value) for key, value in row.items()}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float):
        return round(value, 2)
    return value


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return to_utc(now())


def _round_nullable(value: Any) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def _paginate(
    rows: list[dict[str, Any]],
    page: int,
    page_size: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    start = (page - 1) * page_size
    payload = {
        "items": rows[start : start + page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }
    if extra:
        payload.update(extra)
    return payload


def _cache_key(endpoint: str, params: dict[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}:{endpoint}:{digest}"


def _agent_sort_key(sort_by: str) -> str:
    return {
        "requests": "request_count",
        "p50": "p50_ms",
        "p90": "p90_ms",
        "p95": "p95_ms",
        "p99": "p99_ms",
        "timeout_rate": "timeout_rate",
        "success_rate": "success_rate",
        "tokens": "total_tokens",
    }.get(sort_by, "request_count")


def _workflow_sort_key(sort_by: str) -> str:
    return {
        "runs": "run_count",
        "p50": "p50_ms",
        "p90": "p90_ms",
        "p95": "p95_ms",
        "p99": "p99_ms",
        "timeout_rate": "timeout_rate",
        "success_rate": "success_rate",
        "tokens": "total_tokens",
        "failed_nodes": "failed_nodes",
    }.get(sort_by, "run_count")


def _merge_count_buckets(
    agent_rows: list[dict[str, Any]], workflow_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in agent_rows:
        bucket = _serialize_datetime(row.get("bucket")) or ""
        merged.setdefault(
            bucket, {"bucket": bucket, "agent_requests": 0, "workflow_runs": 0}
        )["agent_requests"] = int(row.get("count") or 0)
    for row in workflow_rows:
        bucket = _serialize_datetime(row.get("bucket")) or ""
        merged.setdefault(
            bucket, {"bucket": bucket, "agent_requests": 0, "workflow_runs": 0}
        )["workflow_runs"] = int(row.get("count") or 0)
    for item in merged.values():
        item["total_requests"] = item["agent_requests"] + item["workflow_runs"]
    return [merged[key] for key in sorted(merged)]


def _cpu_health() -> dict[str, Any]:
    if psutil is None:
        return {"status": "unknown", "error": "psutil is not installed"}
    percent = psutil.cpu_percent(interval=None)
    return {
        "status": _status_for_percent(percent, 70, 90),
        "usage_percent": percent,
        "cores": psutil.cpu_count(),
        "architecture": platform.machine(),
    }


def _memory_health() -> dict[str, Any]:
    if psutil is None:
        return {"status": "unknown", "error": "psutil is not installed"}
    memory = psutil.virtual_memory()
    return {
        "status": _status_for_percent(memory.percent, 80, 90),
        "usage_percent": memory.percent,
        "used_bytes": memory.used,
        "total_bytes": memory.total,
    }


def _disk_health() -> dict[str, Any]:
    if psutil is None:
        return {"status": "unknown", "error": "psutil is not installed"}
    disk = psutil.disk_usage(os.getcwd())
    return {
        "status": _status_for_percent(disk.percent, 80, 90),
        "usage_percent": disk.percent,
        "used_bytes": disk.used,
        "total_bytes": disk.total,
    }


async def _database_health() -> dict[str, Any]:
    conn = Tortoise.get_connection("default")
    try:
        await conn.execute_query("SELECT 1")
        dialect = getattr(getattr(conn, "capabilities", None), "dialect", "")
        if dialect != "postgres":
            return {
                "status": "healthy",
                "active_connections": 1,
                "max_connections": None,
            }

        _, rows = await conn.execute_query(
            """
            SELECT
                COUNT(*)::int AS active_connections,
                current_setting('max_connections')::int AS max_connections
            FROM pg_stat_activity
            """
        )
        row = rows[0] if rows else {}
        return {
            "status": "healthy",
            "active_connections": int(row.get("active_connections") or 0),
            "max_connections": int(row.get("max_connections") or 0),
        }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def _redis_health() -> dict[str, Any]:
    try:
        redis = await get_redis()
        info = await redis.info()
        hits = int(info.get("keyspace_hits") or 0)
        misses = int(info.get("keyspace_misses") or 0)
        return {
            "status": "healthy",
            "used_memory": int(info.get("used_memory") or 0),
            "connected_clients": int(info.get("connected_clients") or 0),
            "ops_per_sec": int(info.get("instantaneous_ops_per_sec") or 0),
            "hit_rate": safe_rate(hits, hits + misses),
        }
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


async def _queue_lengths() -> list[dict[str, Any]]:
    try:
        redis: Any = await get_redis()
        lengths = []
        for queue in WORKER_QUEUES:
            length = await redis.llen(queue)
            lengths.append({"queue": queue, "pending": int(length or 0)})
        return lengths
    except Exception as exc:
        logger.warning("Worker queue length check failed: %s", exc)
        return [{"queue": queue, "pending": 0} for queue in WORKER_QUEUES]


async def _store_health_snapshot(health: dict[str, Any]) -> None:
    try:
        redis: Any = await get_redis()
        snapshot = {
            "generated_at": health.get("generated_at"),
            "cpu_percent": health.get("cpu", {}).get("usage_percent"),
            "memory_percent": health.get("memory", {}).get("usage_percent"),
            "disk_percent": health.get("disk", {}).get("usage_percent"),
            "db_connections": health.get("database", {}).get("active_connections"),
            "redis_ops_per_sec": health.get("redis", {}).get("ops_per_sec"),
        }
        await redis.lpush(HEALTH_SNAPSHOT_KEY, json.dumps(snapshot, default=str))
        await redis.ltrim(HEALTH_SNAPSHOT_KEY, 0, 120)
        await redis.expire(HEALTH_SNAPSHOT_KEY, 86400)
    except Exception as exc:
        logger.warning("Storing system health snapshot failed: %s", exc)


def _status_for_percent(value: float, warning: float, danger: float) -> str:
    if value >= danger:
        return "danger"
    if value >= warning:
        return "warning"
    return "healthy"
