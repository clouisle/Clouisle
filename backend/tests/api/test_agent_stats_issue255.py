from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agent_stats
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, *, counts=None, values=None, value_batches=None):
        self.result = result
        self.counts = iter(counts or [0])
        self.value = values if values is not None else []
        self.value_batches = iter(value_batches) if value_batches is not None else None

    def filter(self, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def limit(self, value):
        return self

    def prefetch_related(self, *args):
        return self

    def annotate(self, **kwargs):
        return self

    async def count(self):
        return next(self.counts)

    async def values(self, *args):
        return (
            next(self.value_batches) if self.value_batches is not None else self.value
        )

    async def values_list(self, *args, **kwargs):
        return self.value

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "function",
    [
        agent_stats.get_agent_stats,
        agent_stats.get_agent_trends,
        agent_stats.get_agent_tool_usage,
        agent_stats.get_recent_conversations,
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


@pytest.mark.anyio
async def test_recent_conversations_serializes_optional_user(monkeypatch):
    timestamp = datetime(2026, 7, 21, tzinfo=UTC)
    conversations = [
        SimpleNamespace(
            id=uuid4(),
            title="With user",
            user=SimpleNamespace(id=uuid4(), username="alice"),
            message_count=2,
            token_usage=3,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        SimpleNamespace(
            id=uuid4(),
            title="Anonymous",
            user=None,
            message_count=0,
            token_usage=0,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    monkeypatch.setattr(
        agent_stats.Conversation, "filter", lambda **kwargs: Query(conversations)
    )

    result = await agent_stats.get_recent_conversations(
        uuid4(), limit=2, current_user=SimpleNamespace()
    )

    assert result["data"][0]["user"]["username"] == "alice"
    assert result["data"][1]["user"] is None
