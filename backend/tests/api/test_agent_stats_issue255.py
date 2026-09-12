from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncio
import pytest

from app.api.v1.endpoints import agent_stats
from app.schemas.response import BusinessError, ResponseCode


@pytest.mark.anyio
@pytest.mark.parametrize(
    "function",
    [
        agent_stats.get_agent_stats,
        agent_stats.get_agent_trends,
        agent_stats.get_agent_tool_usage,
    ],
)
async def test_agent_stats_endpoints_reject_missing_agent(monkeypatch, function):
    agent_id = uuid4()
    current_user = SimpleNamespace()
    denied = AsyncMock(
        side_effect=BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )
    )
    monkeypatch.setattr(agent_stats, "check_agent_access", denied)

    with pytest.raises(BusinessError) as exc:
        await function(agent_id, current_user=current_user)

    denied.assert_awaited_once_with(agent_id, current_user)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.AGENT_NOT_FOUND,
        404,
    )


@pytest.mark.anyio
async def test_agent_stats_assembles_overview_tokens_and_tools(monkeypatch):
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_conversation_overview",
        AsyncMock(return_value={"total_conversations": 2, "active_users": 3}),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_message_overview",
        AsyncMock(
            return_value={
                "user_messages": 3,
                "assistant_messages": 4,
                "tool_messages": 1,
                "prompt_tokens": 8,
                "completion_tokens": 5,
                "tool_call_count": 2,
                "avg_duration": 12.345,
            }
        ),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_run_health",
        AsyncMock(
            return_value={
                "completed": 9,
                "failed": 1,
                "stopped": 0,
                "in_flight": 0,
                "total": 10,
                "success_rate": 0.9,
            }
        ),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_latency_percentiles",
        AsyncMock(
            return_value={"p50": 1200.0, "p95": 9000.0, "avg": 2500.0, "samples": 7}
        ),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_intervention_counts",
        AsyncMock(return_value={"steer": 4, "stop": 1, "follow_up": 0, "total": 5}),
    )

    result = await agent_stats.get_agent_stats(
        uuid4(), period="all", current_user=SimpleNamespace()
    )

    assert result["data"]["overview"] == {
        "total_conversations": 2,
        "total_messages": 8,
        "user_messages": 3,
        "assistant_messages": 4,
        "tool_messages": 1,
        "active_users": 3,
    }
    assert result["data"]["tokens"] == {
        "prompt_tokens": 8,
        "completion_tokens": 5,
        "total_tokens": 13,
    }
    assert result["data"]["performance"] == {
        "avg_response_time_ms": 12.35,
        "first_token_ms": {"p50": 1200.0, "p95": 9000.0, "avg": 2500.0, "samples": 7},
    }
    assert result["data"]["tools"]["tool_call_count"] == 2
    assert result["data"]["health"]["success_rate"] == 0.9
    assert result["data"]["interventions"] == {
        "steer": 4,
        "stop": 1,
        "follow_up": 0,
        "total": 5,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("period", "granularity", "points"),
    [("24h", "hour", 24), ("7d", "day", 7), ("30d", "day", 30)],
)
async def test_agent_trends_emit_one_point_per_bucket(
    monkeypatch, period, granularity, points
):
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())

    # The most recent bucket carries data; every other point must be zero-filled
    # rather than dropped, so the chart keeps a fixed-width x-axis.
    if granularity == "hour":
        latest = fixed_now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    else:
        latest = datetime(2026, 7, 21)
    buckets = AsyncMock(
        return_value={
            latest: {
                "conversations": 1,
                "messages": 1,
                "tokens": 5,
                "avg_duration": 10.0,
            }
        }
    )
    monkeypatch.setattr(agent_stats.stats_sql, "agent_trend_buckets", buckets)

    result = await agent_stats.get_agent_trends(
        uuid4(), period=period, current_user=SimpleNamespace()
    )

    data = result["data"]["data"]
    assert result["data"]["granularity"] == granularity
    assert len(data) == points
    assert data[-1]["tokens"] == 5
    assert data[-1]["messages"] == 1
    assert data[-1]["avg_response_time_ms"] == 10.0
    assert data[0]["tokens"] == 0
    assert data[0]["conversations"] == 0
    # The requested granularity is what decides the SQL bucket width.
    assert buckets.await_args.args[2] == granularity


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("period", "first_point"),
    [
        # 12:37 must not be used as the window start: the first hourly point is
        # 13:00 the previous day, so the window must start there or the leading
        # partial bucket is fetched and then discarded.
        ("24h", datetime(2026, 7, 20, 13, 0, tzinfo=UTC)),
        ("7d", datetime(2026, 7, 15, 0, 0, tzinfo=UTC)),
        ("30d", datetime(2026, 6, 22, 0, 0, tzinfo=UTC)),
    ],
)
async def test_agent_trends_window_starts_at_the_first_rendered_bucket(
    monkeypatch, period, first_point
):
    fixed_now = datetime(2026, 7, 21, 12, 37, tzinfo=UTC)
    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    buckets = AsyncMock(return_value={})
    monkeypatch.setattr(agent_stats.stats_sql, "agent_trend_buckets", buckets)

    result = await agent_stats.get_agent_trends(
        uuid4(), period=period, current_user=SimpleNamespace()
    )

    # args[1] is the window start handed to the SQL; it must equal the first
    # point's timestamp, or rows bucket to a key the chart never renders.
    window_start = buckets.await_args.args[1]
    assert window_start == first_point
    assert result["data"]["data"][0]["timestamp"] == first_point.isoformat()


@pytest.mark.anyio
async def test_agent_stats_fan_out_is_bounded_by_the_aggregate_budget(monkeypatch):
    """One request must not hold the whole connection pool open.

    The five aggregates used to be issued as five simultaneous pool checkouts
    against a pool of five. They are now gated so at most
    ``DB_AGGREGATE_CONCURRENCY`` are in flight at once.
    """
    from app.core import db_limits

    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    # The limiter is shared process-wide, so patch it where it is defined.
    monkeypatch.setattr(db_limits, "_AGGREGATE_SEMAPHORE", asyncio.Semaphore(2))

    in_flight = 0
    peak = 0

    def _stub(result):
        async def _run(*_args, **_kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return result

        return _run

    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_conversation_overview",
        _stub({"total_conversations": 0, "active_users": 0}),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_message_overview",
        _stub(
            {
                "user_messages": 0,
                "assistant_messages": 0,
                "tool_messages": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "tool_call_count": 0,
                "avg_duration": 0,
            }
        ),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_run_health",
        _stub(
            {
                "completed": 0,
                "failed": 0,
                "stopped": 0,
                "interrupted": 0,
                "unrecognised": 0,
                "in_flight": 0,
                "total": 0,
                "success_rate": 0.0,
            }
        ),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_latency_percentiles",
        _stub({"p50": 0.0, "p95": 0.0, "avg": 0.0, "samples": 0}),
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_intervention_counts",
        _stub({"steer": 0, "stop": 0, "follow_up": 0, "total": 0}),
    )

    await agent_stats.get_agent_stats(uuid4(), period="all", current_user=None)

    assert peak == 2, "fan-out must respect DB_AGGREGATE_CONCURRENCY"


@pytest.mark.anyio
async def test_tool_usage_preserves_database_ordering(monkeypatch):
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        agent_stats.stats_sql,
        "agent_tool_usage",
        AsyncMock(
            return_value=[
                {"name": "search", "count": 2},
                {"name": "fetch", "count": 1},
            ]
        ),
    )
    monkeypatch.setattr(
        agent_stats,
        "get_tool_display_names",
        AsyncMock(return_value={"search": "Search", "fetch": "Fetch"}),
    )

    result = await agent_stats.get_agent_tool_usage(
        uuid4(), period="30d", current_user=SimpleNamespace()
    )

    assert result["data"]["tools"] == [
        {"name": "search", "display_name": "Search", "count": 2},
        {"name": "fetch", "display_name": "Fetch", "count": 1},
    ]
    assert result["data"]["total_calls"] == 3
