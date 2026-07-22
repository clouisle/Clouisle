from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agent_stats
from app.schemas.response import BusinessError


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

    async def first(self):
        return self.result

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
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query())

    with pytest.raises(BusinessError) as exc:
        await function(uuid4(), current_user=SimpleNamespace())

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_agent_stats_aggregates_messages_tokens_users_and_tools(monkeypatch):
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query(object()))
    monkeypatch.setattr(
        agent_stats.Conversation,
        "filter",
        lambda **kwargs: Query(counts=[2], values=[uuid4(), uuid4(), uuid4()]),
    )
    message_query = Query(
        counts=[3, 4, 1],
        value_batches=[
            [{"token_usage": {"prompt": 8, "completion": 5}}, {"token_usage": None}],
            [{"avg_duration": 12.345}],
            [{"tool_calls": [{"function": {"name": "search"}}, {"name": "fetch"}]}],
        ],
    )
    monkeypatch.setattr(agent_stats.Message, "filter", lambda **kwargs: message_query)

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
    assert result["data"]["tokens"]["total_tokens"] == 13
    assert result["data"]["performance"]["avg_response_time_ms"] == 12.35
    assert result["data"]["tools"]["tool_call_count"] == 2


@pytest.mark.anyio
async def test_agent_trends_groups_hourly_and_daily_data(monkeypatch):
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    conversation = {"id": uuid4(), "created_at": fixed_now - timedelta(minutes=30)}
    message = {
        "created_at": fixed_now - timedelta(minutes=20),
        "token_usage": {"prompt": 2, "completion": 3},
        "duration_ms": 10,
    }
    monkeypatch.setattr(agent_stats, "now", lambda: fixed_now)
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query(object()))
    monkeypatch.setattr(
        agent_stats.Conversation,
        "filter",
        lambda **kwargs: Query(values=[conversation]),
    )
    monkeypatch.setattr(
        agent_stats.Message, "filter", lambda **kwargs: Query(values=[message])
    )

    hourly = await agent_stats.get_agent_trends(
        uuid4(), period="24h", current_user=SimpleNamespace()
    )
    daily = await agent_stats.get_agent_trends(
        uuid4(), period="7d", current_user=SimpleNamespace()
    )

    assert hourly["data"]["granularity"] == "hour"
    assert len(hourly["data"]["data"]) == 24
    assert hourly["data"]["data"][-1]["tokens"] == 5
    assert daily["data"]["granularity"] == "day"
    assert len(daily["data"]["data"]) == 7
    assert daily["data"]["data"][-1]["messages"] == 1


@pytest.mark.anyio
async def test_tool_usage_normalizes_formats_and_sorts(monkeypatch):
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query(object()))
    monkeypatch.setattr(
        agent_stats.Message,
        "filter",
        lambda **kwargs: Query(
            values=[
                {"tool_calls": [{"function": {"name": "search"}}, {"name": "fetch"}]},
                {"tool_calls": [{"name": "search"}, "invalid", {}]},
                {"tool_calls": None},
            ]
        ),
    )

    result = await agent_stats.get_agent_tool_usage(
        uuid4(), period="30d", current_user=SimpleNamespace()
    )

    assert result["data"]["tools"] == [
        {"name": "search", "count": 2},
        {"name": "fetch", "count": 1},
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
    monkeypatch.setattr(agent_stats.Agent, "filter", lambda **kwargs: Query(object()))
    monkeypatch.setattr(
        agent_stats.Conversation, "filter", lambda **kwargs: Query(conversations)
    )

    result = await agent_stats.get_recent_conversations(
        uuid4(), limit=2, current_user=SimpleNamespace()
    )

    assert result["data"][0]["user"]["username"] == "alice"
    assert result["data"][1]["user"] is None
