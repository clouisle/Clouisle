from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agent_stats
from app.models.agent import MessageRole


class StatsQuery:
    def __init__(self, *, values=None):
        self.values_result = values or {}
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def annotate(self, **_kwargs):
        return self

    async def count(self):
        role = next(
            (item["role"] for item in reversed(self.filters) if "role" in item), None
        )
        return {
            None: 2,
            MessageRole.USER: 1,
            MessageRole.ASSISTANT: 2,
            MessageRole.TOOL: 1,
        }[role]

    async def values(self, *fields):
        return self.values_result.get(fields, [])

    async def values_list(self, *_fields, **_kwargs):
        return [uuid4(), uuid4(), uuid4()]


@pytest.mark.anyio
@pytest.mark.parametrize("period", ["24h", "7d", "30d", "all"])
async def test_agent_stats_bounds_every_period_except_all(monkeypatch, period):
    conversations = AsyncMock(
        return_value={"total_conversations": 1, "active_users": 1}
    )
    messages = AsyncMock(
        return_value={
            "user_messages": 1,
            "assistant_messages": 1,
            "tool_messages": 0,
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "tool_call_count": 3,
            "avg_duration": 12.5,
        }
    )
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    monkeypatch.setattr(
        agent_stats.stats_sql, "agent_conversation_overview", conversations
    )
    monkeypatch.setattr(agent_stats.stats_sql, "agent_message_overview", messages)
    for name, stub in (
        (
            "agent_run_health",
            {
                "completed": 0,
                "failed": 0,
                "stopped": 0,
                "in_flight": 0,
                "total": 0,
                "success_rate": 0.0,
            },
        ),
        (
            "agent_latency_percentiles",
            {"p50": 0.0, "p95": 0.0, "avg": 0.0, "samples": 0},
        ),
        (
            "agent_intervention_counts",
            {"steer": 0, "stop": 0, "follow_up": 0, "total": 0},
        ),
    ):
        monkeypatch.setattr(agent_stats.stats_sql, name, AsyncMock(return_value=stub))

    result = await agent_stats.get_agent_stats(
        uuid4(), period=period, current_user=None
    )

    assert result["data"]["tokens"]["total_tokens"] == 5
    assert result["data"]["tools"]["tool_call_count"] == 3
    # "all" must scan without a lower bound; every other period must pass one,
    # and both aggregates must agree on the window or the numbers disagree.
    expected_bound = None if period == "all" else "bounded"
    for call in (conversations, messages):
        start_time = call.await_args.args[1]
        assert (None if start_time is None else "bounded") == expected_bound
    assert conversations.await_args.args[1] == messages.await_args.args[1]


@pytest.mark.anyio
@pytest.mark.parametrize(("period", "expected_points"), [("7d", 7), ("30d", 30)])
async def test_agent_trends_day_ranges_fill_every_point(
    monkeypatch, period, expected_points
):
    fixed_now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(agent_stats, "check_agent_access", AsyncMock())
    monkeypatch.setattr(
        agent_stats.stats_sql, "agent_trend_buckets", AsyncMock(return_value={})
    )

    result = await agent_stats.get_agent_trends(
        uuid4(), period=period, current_user=None
    )

    assert result["data"]["granularity"] == "day"
    # An empty result set still yields a full-width series of zeroed points.
    assert len(result["data"]["data"]) == expected_points
    assert all(point["messages"] == 0 for point in result["data"]["data"])


@pytest.mark.anyio
async def test_tool_usage_bounds_seven_day_window(monkeypatch):
    usage = AsyncMock(return_value=[{"name": "search", "count": 2}])
    monkeypatch.setattr(
        agent_stats, "check_agent_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(agent_stats.stats_sql, "agent_tool_usage", usage)
    monkeypatch.setattr(
        agent_stats,
        "get_tool_display_names",
        AsyncMock(return_value={"search": "Search"}),
    )

    result = await agent_stats.get_agent_tool_usage(
        uuid4(), period="7d", current_user=None
    )

    assert result["data"]["tools"] == [
        {"name": "search", "display_name": "Search", "count": 2}
    ]
    assert usage.await_args.args[1] is not None
