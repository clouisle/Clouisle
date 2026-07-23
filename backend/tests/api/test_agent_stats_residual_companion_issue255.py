from datetime import datetime, UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agent_stats
from app.models.agent import MessageRole


class StatsQuery:
    def __init__(self, *, first=None, values=None):
        self.first_result = first
        self.values_result = values or {}
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def annotate(self, **_kwargs):
        return self

    async def first(self):
        return self.first_result

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
async def test_agent_stats_issue255_selects_each_period_and_optional_filters(
    monkeypatch, period
):
    agent_query = StatsQuery(first=SimpleNamespace(id=uuid4()))
    conversation_queries = []
    message_query = StatsQuery(
        values={
            ("token_usage",): [
                {"token_usage": {"prompt": 3, "completion": 2}},
                {"token_usage": None},
            ],
            ("avg_duration",): [{"avg_duration": 12.5}],
            ("tool_calls",): [
                {"tool_calls": [{"name": "one"}]},
                {"tool_calls": [{"name": "two"}, {"name": "three"}]},
            ],
        }
    )

    def conversation_filter(**kwargs):
        query = StatsQuery()
        query.filters.append(kwargs)
        conversation_queries.append(query)
        return query

    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(agent_stats.Conversation, "filter", conversation_filter)
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **_kwargs: message_query)

    result = await agent_stats.get_agent_stats(
        uuid4(), period=period, current_user=None
    )

    assert result["data"]["tokens"]["total_tokens"] == 5
    assert result["data"]["tools"]["tool_call_count"] == 3
    expected_time_filters = 0 if period == "all" else 2
    assert (
        sum(
            "created_at__gte" in item
            for query in conversation_queries
            for item in query.filters
        )
        == expected_time_filters
    )


@pytest.mark.anyio
@pytest.mark.parametrize(("period", "expected_points"), [("7d", 7), ("30d", 30)])
async def test_agent_stats_issue255_trends_selects_day_ranges(
    monkeypatch, period, expected_points
):
    fixed_now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    agent_query = StatsQuery(first=SimpleNamespace(id=uuid4()))
    data_query = StatsQuery()

    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(
        agent_stats.Conversation, "filter", lambda **_kwargs: data_query
    )
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **_kwargs: data_query)

    result = await agent_stats.get_agent_trends(
        uuid4(), period=period, current_user=None
    )

    assert result["data"]["granularity"] == "day"
    assert len(result["data"]["data"]) == expected_points


@pytest.mark.anyio
async def test_agent_stats_issue255_tool_usage_applies_seven_day_filter(monkeypatch):
    agent_query = StatsQuery(first=SimpleNamespace(id=uuid4()))
    message_query = StatsQuery(
        values={
            ("tool_calls",): [
                {
                    "tool_calls": [
                        {"function": {"name": "search"}},
                        {"name": "search"},
                    ]
                }
            ]
        }
    )
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **_kwargs: message_query)

    result = await agent_stats.get_agent_tool_usage(
        uuid4(), period="7d", current_user=None
    )

    assert result["data"]["tools"] == [{"name": "search", "count": 2}]
    assert any("created_at__gte" in item for item in message_query.filters)
