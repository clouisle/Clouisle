"""Access control for the /agents/{agent_id}/stats endpoints (YUN-153).

Agent statistics, activity trends, tool usage and recent conversation metadata
must not be readable across team or private-agent boundaries.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import agent_stats, agents
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError, ResponseCode

STATS_ENDPOINTS = [
    agent_stats.get_agent_stats,
    agent_stats.get_agent_trends,
    agent_stats.get_agent_tool_usage,
    agent_stats.get_recent_conversations,
]


class _AgentQuery:
    def __init__(self, agent):
        self.agent = agent

    def prefetch_related(self, *_relations):
        return self

    async def first(self):
        return self.agent


class _AgentModel:
    agent = None

    @classmethod
    def filter(cls, **_kwargs):
        return _AgentQuery(cls.agent)


class _ConversationQuery:
    def __init__(self, conversations):
        self.conversations = conversations

    def order_by(self, *_fields):
        return self

    def limit(self, _value):
        return self

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def resolve():
            return self.conversations

        return resolve().__await__()


def _agent(*, visibility: AgentVisibility, team_id, creator_id):
    return SimpleNamespace(
        id=uuid4(),
        visibility=visibility,
        created_by=SimpleNamespace(id=creator_id),
        team=SimpleNamespace(id=team_id),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", STATS_ENDPOINTS)
async def test_stats_endpoints_deny_foreign_private_agent_before_reading_data(
    monkeypatch, endpoint
):
    agent = _agent(
        visibility=AgentVisibility.PRIVATE, team_id=uuid4(), creator_id=uuid4()
    )
    _AgentModel.agent = agent
    conversation_filter = MagicMock()
    aggregates = {
        name: MagicMock()
        for name in (
            "agent_conversation_overview",
            "agent_message_overview",
            "agent_tool_usage",
            "agent_trend_buckets",
            "agent_run_health",
            "agent_latency_percentiles",
            "agent_intervention_counts",
        )
    }
    monkeypatch.setattr(agents, "Agent", _AgentModel)
    monkeypatch.setattr(agent_stats.Conversation, "filter", conversation_filter)
    display_names = MagicMock()
    monkeypatch.setattr(agent_stats, "get_tool_display_names", display_names)
    for name, stub in aggregates.items():
        monkeypatch.setattr(agent_stats.stats_sql, name, stub)

    with pytest.raises(BusinessError) as exc:
        await endpoint(
            agent.id, current_user=SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.AGENT_ACCESS_DENIED,
        403,
    )
    # Authorization must short-circuit before any statistics data is touched.
    conversation_filter.assert_not_called()
    display_names.assert_not_called()
    for stub in aggregates.values():
        stub.assert_not_called()


@pytest.mark.anyio
async def test_recent_conversations_allows_non_owner_team_member(monkeypatch):
    team_id = uuid4()
    agent = _agent(visibility=AgentVisibility.TEAM, team_id=team_id, creator_id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    timestamp = datetime(2026, 9, 12, tzinfo=UTC)
    member = SimpleNamespace(
        id=uuid4(),
        title="Shared",
        user=SimpleNamespace(id=uuid4(), username="member"),
        message_count=2,
        token_usage=5,
        created_at=timestamp,
        updated_at=timestamp,
    )
    _AgentModel.agent = agent
    check_team = AsyncMock()
    monkeypatch.setattr(agents, "Agent", _AgentModel)
    monkeypatch.setattr(agents, "check_team_access", check_team)
    monkeypatch.setattr(
        agent_stats.Conversation,
        "filter",
        lambda **_kwargs: _ConversationQuery([member]),
    )

    response = await agent_stats.get_recent_conversations(agent.id, current_user=user)

    check_team.assert_awaited_once_with(team_id, user)
    assert response["data"][0]["title"] == "Shared"
    assert response["data"][0]["user"]["username"] == "member"
