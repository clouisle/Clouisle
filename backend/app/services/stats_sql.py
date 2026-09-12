"""Database-side aggregation for Agent and Workflow statistics.

Statistics endpoints previously loaded whole detail tables into Python and
aggregated there. These helpers push the aggregation into PostgreSQL so the
cost scales with the number of returned buckets instead of the number of rows.

Security invariants — every helper in this module MUST uphold them:

- **No interpolated values.** Every runtime value (ids, timestamps, timezone,
  limits) is an ``$N`` bind parameter, matching the convention in
  ``app/services/lexical_store.py``. Nothing user-supplied is formatted into
  SQL text.
- **Identifiers come from closed allowlists.** The only non-parameterisable
  fragments are the ``date_trunc`` granularity and the status names used in
  ``FILTER`` clauses; both are validated against module-level frozensets, so
  a caller cannot smuggle SQL through them.
- **Authorization stays upstream.** These helpers scope by the ids they are
  given and never widen them. Callers resolve access first (check_agent_access
  / check_workflow_access / workflow_read_visibility_filter) and pass only the
  already-authorised ids.

Semantics are preserved verbatim from the previous Python implementations,
including JSON coercion rules, NULL handling, and empty-set fallbacks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from tortoise import Tortoise

from app.models.agent_run import AgentRunInputKind, AgentRunStatus

# Closed allowlist: the granularity is a SQL keyword-position fragment and can
# never be a bind parameter, so it must be validated rather than passed through.
_GRANULARITIES = frozenset({"hour", "day"})

# Derived from the model enums so a newly added status cannot be silently
# classified as success or dropped from the denominator.
AGENT_RUN_STATUS_VALUES = frozenset(status.value for status in AgentRunStatus)
TERMINAL_AGENT_RUN_STATUSES = frozenset(
    status.value
    for status in AgentRunStatus
    if status
    in {AgentRunStatus.COMPLETED, AgentRunStatus.FAILED, AgentRunStatus.STOPPED}
)
IN_FLIGHT_AGENT_RUN_STATUSES = AGENT_RUN_STATUS_VALUES - TERMINAL_AGENT_RUN_STATUSES
AGENT_RUN_INPUT_KIND_VALUES = frozenset(kind.value for kind in AgentRunInputKind)


def _granularity(value: str) -> str:
    if value not in _GRANULARITIES:
        raise ValueError(f"Unsupported bucket granularity: {value!r}")
    return value


def _connection() -> Any:
    return Tortoise.get_connection("default")


# ``token_usage`` and ``tool_calls`` are JSONB columns holding model-supplied
# payloads. The Python implementations used ``.get(key, 0) or 0`` and
# ``isinstance(value, list)``, which silently ignore malformed entries. The
# jsonb_typeof guards below reproduce that tolerance: a non-numeric token value
# or a non-array tool_calls payload contributes zero instead of raising, so
# dirty rows cannot turn a statistics read into a 500.
#
# Two SQL constraints shape these fragments:
#
# 1. ``m.`` qualification is REQUIRED. Both callers join ``messages`` to
#    ``conversations``, and ``conversations`` also has a ``token_usage``
#    column (a denormalised integer total), so an unqualified reference
#    raises "column reference is ambiguous".
# 2. The role predicate lives INSIDE the ``CASE``, not in a trailing
#    ``FILTER`` clause. ``FILTER`` may only follow a bare aggregate, so
#    ``COALESCE(SUM(...)) FILTER (...)`` is a syntax error.
_TOKEN_SUM = """
    COALESCE(SUM(
        CASE WHEN m.role = 'assistant'
              AND jsonb_typeof(m.token_usage -> '{key}') = 'number'
             THEN (m.token_usage ->> '{key}')::bigint
             ELSE 0 END
    ), 0)
"""

_TOOL_CALL_COUNT = """
    COALESCE(SUM(
        CASE WHEN m.role = 'assistant' AND jsonb_typeof(m.tool_calls) = 'array'
             THEN jsonb_array_length(m.tool_calls)
             ELSE 0 END
    ), 0)
"""


def _token_sum(key: str) -> str:
    # ``key`` is never caller-supplied; it is one of the two literals below.
    if key not in {"prompt", "completion"}:
        raise ValueError(f"Unsupported token key: {key!r}")
    return _TOKEN_SUM.format(key=key)


async def agent_message_overview(
    agent_id: UUID, start_time: datetime | None
) -> dict[str, Any]:
    """Aggregate per-role counts, token sums, tool calls and average duration.

    Replaces six separate queries plus two full-table Python loops with one
    pass over the agent's messages.
    """
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND m.created_at >= $2"

    rows = await _connection().execute_query_dict(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE m.role = 'user')      AS user_messages,
            COUNT(*) FILTER (WHERE m.role = 'assistant') AS assistant_messages,
            COUNT(*) FILTER (WHERE m.role = 'tool')      AS tool_messages,
            {_token_sum("prompt")}     AS prompt_tokens,
            {_token_sum("completion")} AS completion_tokens,
            {_TOOL_CALL_COUNT}         AS tool_call_count,
            AVG(m.duration_ms) FILTER (
                WHERE m.role = 'assistant' AND m.duration_ms IS NOT NULL
            ) AS avg_duration
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.agent_id = $1::uuid{window}
        """,
        params,
    )
    row = rows[0] if rows else {}
    return {
        "user_messages": int(row.get("user_messages") or 0),
        "assistant_messages": int(row.get("assistant_messages") or 0),
        "tool_messages": int(row.get("tool_messages") or 0),
        "prompt_tokens": int(row.get("prompt_tokens") or 0),
        "completion_tokens": int(row.get("completion_tokens") or 0),
        "tool_call_count": int(row.get("tool_call_count") or 0),
        # AVG over an empty set is NULL; the previous code fell back to 0.
        "avg_duration": float(row["avg_duration"]) if row.get("avg_duration") else 0,
    }


async def agent_conversation_overview(
    agent_id: UUID, start_time: datetime | None
) -> dict[str, int]:
    """Count conversations and distinct users without loading user id lists."""
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND created_at >= $2"

    rows = await _connection().execute_query_dict(
        f"""
        SELECT COUNT(*) AS total_conversations,
               COUNT(DISTINCT user_id) AS active_users
        FROM conversations
        WHERE agent_id = $1::uuid{window}
        """,
        params,
    )
    row = rows[0] if rows else {}
    return {
        "total_conversations": int(row.get("total_conversations") or 0),
        "active_users": int(row.get("active_users") or 0),
    }


async def agent_tool_usage(
    agent_id: UUID, start_time: datetime | None
) -> list[dict[str, Any]]:
    """Aggregate tool-call counts by tool name, ordered by count descending.

    Mirrors the previous Python normalisation, which accepted both the standard
    ``{"function": {"name": ...}}`` shape and the flat ``{"name": ...}`` shape,
    and skipped entries without a usable name.
    """
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND m.created_at >= $2"

    return await _connection().execute_query_dict(
        f"""
        SELECT tool_name AS name, COUNT(*) AS count
        FROM (
            SELECT COALESCE(
                       call -> 'function' ->> 'name',
                       call ->> 'name'
                   ) AS tool_name
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(m.tool_calls) = 'array'
                    THEN m.tool_calls
                    ELSE '[]'::jsonb
                END
            ) AS call
            WHERE c.agent_id = $1::uuid
              AND m.role = 'assistant'
              AND jsonb_typeof(m.tool_calls) = 'array'{window}
        ) named
        WHERE tool_name IS NOT NULL AND tool_name <> ''
        GROUP BY tool_name
        ORDER BY count DESC, tool_name ASC
        """,
        params,
    )


async def agent_trend_buckets(
    agent_id: UUID, start_time: datetime, granularity: str, timezone_name: str
) -> dict[datetime, dict[str, Any]]:
    """Bucket conversations and assistant messages in the configured timezone.

    Buckets are cut on local-time boundaries (``settings.TIMEZONE``) so daily
    points align with the previous Python implementation rather than UTC.

    First-token percentiles are bucketed alongside, turning latency into a time
    series rather than a single snapshot. A snapshot cannot show a regression:
    in production one day sat at a 6.4s median with a 45s p95, which only the
    per-bucket series reveals.
    """
    unit = _granularity(granularity)
    conn = _connection()

    conversation_rows = await conn.execute_query_dict(
        f"""
        SELECT date_trunc('{unit}', created_at AT TIME ZONE $3) AS bucket,
               COUNT(*) AS conversations
        FROM conversations
        WHERE agent_id = $1::uuid AND created_at >= $2
        GROUP BY bucket
        """,
        [str(agent_id), start_time, timezone_name],
    )

    # ``percentile_cont`` skips NULL inputs, so a bucket with no measured
    # first-token samples yields NULL rather than a misleading zero.
    message_rows = await conn.execute_query_dict(
        f"""
        SELECT date_trunc('{unit}', m.created_at AT TIME ZONE $3) AS bucket,
               COUNT(*) AS messages,
               {_token_sum("prompt")} + {_token_sum("completion")} AS tokens,
               AVG(m.duration_ms) FILTER (WHERE m.duration_ms IS NOT NULL)
                   AS avg_duration,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY m.first_token_ms)
                   AS ttft_p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY m.first_token_ms)
                   AS ttft_p95
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.agent_id = $1::uuid
          AND m.created_at >= $2
          AND m.role = 'assistant'
        GROUP BY bucket
        """,
        [str(agent_id), start_time, timezone_name],
    )

    buckets: dict[datetime, dict[str, Any]] = {}
    for row in conversation_rows:
        buckets.setdefault(row["bucket"], {})["conversations"] = int(
            row["conversations"] or 0
        )
    for row in message_rows:
        bucket = buckets.setdefault(row["bucket"], {})
        bucket["messages"] = int(row["messages"] or 0)
        bucket["tokens"] = int(row["tokens"] or 0)
        bucket["avg_duration"] = (
            float(row["avg_duration"]) if row["avg_duration"] else 0
        )
        # Kept as None (not 0) so the chart breaks the line instead of
        # drawing a fake drop to zero on an unmeasured bucket.
        bucket["ttft_p50"] = (
            float(row["ttft_p50"]) if row["ttft_p50"] is not None else None
        )
        bucket["ttft_p95"] = (
            float(row["ttft_p95"]) if row["ttft_p95"] is not None else None
        )
    return buckets


async def workflow_run_overview(workflow_id: UUID) -> dict[str, Any]:
    """Aggregate one workflow's run counts, average duration and last run."""
    rows = await _connection().execute_query_dict(
        """
        SELECT
            COUNT(*)                                       AS total_runs,
            COUNT(*) FILTER (WHERE status = 'success')     AS success_count,
            COUNT(*) FILTER (WHERE status = 'failed')      AS failed_count,
            COUNT(*) FILTER (WHERE status = 'timeout')     AS timeout_count,
            AVG(total_duration_ms) FILTER (
                WHERE total_duration_ms IS NOT NULL
            )                                              AS avg_duration_ms,
            MAX(created_at)                                AS last_run_at
        FROM workflow_runs
        WHERE workflow_id = $1::uuid
        """,
        [str(workflow_id)],
    )
    row = rows[0] if rows else {}
    return {
        "total_runs": int(row.get("total_runs") or 0),
        "success_count": int(row.get("success_count") or 0),
        "failed_count": int(row.get("failed_count") or 0),
        "timeout_count": int(row.get("timeout_count") or 0),
        "avg_duration_ms": float(row["avg_duration_ms"])
        if row.get("avg_duration_ms")
        else 0,
        "last_run_at": row.get("last_run_at"),
    }


async def workflow_trend_buckets(
    workflow_id: UUID, start_time: datetime, timezone_name: str
) -> dict[datetime, dict[str, Any]]:
    """Bucket one workflow's runs by local day."""
    rows = await _connection().execute_query_dict(
        """
        SELECT date_trunc('day', created_at AT TIME ZONE $3) AS bucket,
               COUNT(*)                                   AS runs,
               COUNT(*) FILTER (WHERE status = 'success') AS success,
               COUNT(*) FILTER (WHERE status = 'failed')  AS failed,
               AVG(total_duration_ms) FILTER (
                   WHERE total_duration_ms IS NOT NULL
               )                                          AS avg_duration
        FROM workflow_runs
        WHERE workflow_id = $1::uuid AND created_at >= $2
        GROUP BY bucket
        """,
        [str(workflow_id), start_time, timezone_name],
    )
    return {
        row["bucket"]: {
            "runs": int(row["runs"] or 0),
            "success": int(row["success"] or 0),
            "failed": int(row["failed"] or 0),
            "avg_duration": float(row["avg_duration"]) if row["avg_duration"] else 0,
        }
        for row in rows
    }


async def workflow_global_run_stats(
    workflow_ids: list[UUID], top_limit: int = 10
) -> dict[str, Any]:
    """Aggregate run stats across the caller's already-authorised workflows.

    ``workflow_ids`` MUST already be visibility-filtered; this helper scopes
    strictly to them and never widens the set.
    """
    conn = _connection()
    ids = [str(workflow_id) for workflow_id in workflow_ids]

    status_rows = await conn.execute_query_dict(
        """
        SELECT status, COUNT(*) AS count
        FROM workflow_runs
        WHERE workflow_id = ANY($1::uuid[])
        GROUP BY status
        """,
        [ids],
    )

    top_rows = await conn.execute_query_dict(
        """
        SELECT workflow_id, COUNT(*) AS count
        FROM workflow_runs
        WHERE workflow_id = ANY($1::uuid[]) AND workflow_id IS NOT NULL
        GROUP BY workflow_id
        ORDER BY count DESC
        LIMIT $2
        """,
        [ids, top_limit],
    )

    # Distinct from the per-workflow endpoint: this average is measured from
    # the started/finished wall clock and only over SUCCESS runs. The integer
    # truncation matches the previous ``//`` division.
    duration_rows = await conn.execute_query_dict(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (finished_at - started_at)) * 1000)
                   AS avg_duration_ms
        FROM workflow_runs
        WHERE workflow_id = ANY($1::uuid[])
          AND status = 'success'
          AND started_at IS NOT NULL
          AND finished_at IS NOT NULL
        """,
        [ids],
    )

    avg_raw = duration_rows[0]["avg_duration_ms"] if duration_rows else None
    return {
        "runs_by_status": {row["status"]: int(row["count"]) for row in status_rows},
        "total_runs": sum(int(row["count"]) for row in status_rows),
        "top_workflows": [(row["workflow_id"], int(row["count"])) for row in top_rows],
        "avg_duration_ms": int(avg_raw) if avg_raw else 0,
    }


async def agent_run_health(
    agent_id: UUID, start_time: datetime | None
) -> dict[str, Any]:
    """Count one agent's runs by terminal outcome and derive a success rate.

    Reads ``agent_runs.status`` rather than ``Message.round_status``. The two
    disagree in both directions and ``agent_runs`` is the complete source:

    - a run that exhausts ``max_iterations`` is still recorded COMPLETED, so
      run status alone would overstate success;
    - a crashed run leaves a canonical message whose ``round_status`` was never
      finalised (NULL), so counting round status would silently omit every
      crash from the denominator.

    Terminal states are compared against the ``AgentRunStatus`` enum so a new
    status cannot be silently classified as success.

    The period filter uses ``updated_at`` because ``agent_runs`` has no
    ``created_at`` column, and it is the only timestamp that is NOT NULL for
    every row: filtering on ``started_at`` would drop the one recorded run
    whose start was never stamped, silently removing a failure from the
    denominator. For a terminal run ``updated_at`` is its final transition,
    which is also the more meaningful "when did this conclude" bound.
    """
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND updated_at >= $2"

    rows = await _connection().execute_query_dict(
        f"""
        SELECT status, COUNT(*) AS count
        FROM agent_runs
        WHERE agent_id = $1::uuid{window}
        GROUP BY status
        """,
        params,
    )

    counts: dict[str, int] = {}
    for row in rows:
        status = row["status"]
        if status not in AGENT_RUN_STATUS_VALUES:
            # An unrecognised status is surfaced instead of being folded into
            # a bucket, so enum drift cannot masquerade as a clean run.
            raise ValueError(f"Unknown agent run status in database: {status!r}")
        counts[status] = int(row["count"])

    terminal = sum(counts.get(status, 0) for status in TERMINAL_AGENT_RUN_STATUSES)
    completed = counts.get("completed", 0)
    return {
        "completed": completed,
        "failed": counts.get("failed", 0),
        "stopped": counts.get("stopped", 0),
        "in_flight": sum(
            counts.get(status, 0) for status in IN_FLIGHT_AGENT_RUN_STATUSES
        ),
        "total": terminal,
        "success_rate": (completed / terminal) if terminal else 0.0,
    }


async def agent_latency_percentiles(
    agent_id: UUID, start_time: datetime | None
) -> dict[str, Any]:
    """First-token latency distribution, which the average alone cannot show.

    ``avg_response_time_ms`` mixes model time with tool-loop time. Time to
    first token isolates the model/streaming half, and the percentiles expose
    the tail that an average hides.
    """
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND m.created_at >= $2"

    rows = await _connection().execute_query_dict(
        f"""
        SELECT
            percentile_cont(0.5) WITHIN GROUP (ORDER BY m.first_token_ms)  AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY m.first_token_ms) AS p95,
            AVG(m.first_token_ms) AS avg_first_token,
            COUNT(*)              AS samples
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.agent_id = $1::uuid
          AND m.role = 'assistant'
          AND m.first_token_ms IS NOT NULL{window}
        """,
        params,
    )
    row = rows[0] if rows else {}
    # Percentiles over an empty set are NULL, unlike the previous 0 fallbacks.
    return {
        "p50": float(row["p50"]) if row.get("p50") is not None else 0.0,
        "p95": float(row["p95"]) if row.get("p95") is not None else 0.0,
        "avg": float(row["avg_first_token"])
        if row.get("avg_first_token") is not None
        else 0.0,
        "samples": int(row.get("samples") or 0),
    }


async def agent_intervention_counts(
    agent_id: UUID, start_time: datetime | None
) -> dict[str, int]:
    """Count how often users steered or stopped this agent's runs.

    A friction signal: high counts mean the agent needs correction mid-flight.
    Only durable runs enqueue inputs, so older chat traffic has no record.
    """
    params: list[Any] = [str(agent_id)]
    window = ""
    if start_time is not None:
        params.append(start_time)
        window = " AND i.created_at >= $2"

    rows = await _connection().execute_query_dict(
        f"""
        SELECT i.kind, COUNT(*) AS count
        FROM agent_run_inputs i
        JOIN agent_runs r ON r.id = i.run_id
        WHERE r.agent_id = $1::uuid{window}
        GROUP BY i.kind
        """,
        params,
    )

    counts: dict[str, int] = {}
    for row in rows:
        kind = row["kind"]
        if kind not in AGENT_RUN_INPUT_KIND_VALUES:
            raise ValueError(f"Unknown agent run input kind in database: {kind!r}")
        counts[kind] = int(row["count"])

    return {
        "steer": counts.get("steer", 0),
        "stop": counts.get("stop", 0),
        "follow_up": counts.get("follow_up", 0),
        "total": sum(counts.values()),
    }
