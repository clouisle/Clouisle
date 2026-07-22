from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import conversations


class Query:
    def __init__(self, result=None, *, first=None, count=0, values=None):
        self.result = [] if result is None else result
        self.first_value = first
        self.count_value = count
        self.values_value = [] if values is None else values
        self.filters = []

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def select_related(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def values(self, *_args):
        return self.values_value

    async def values_list(self, *_args, **_kwargs):
        return self.values_value

    async def all(self):
        return self.result

    async def update(self, **_kwargs):
        return 1

    async def delete(self):
        return len(self.result)


def user(*, user_id=None, superuser=False, permissions=()):
    role = SimpleNamespace(
        permissions=[SimpleNamespace(code=code) for code in permissions]
    )
    return SimpleNamespace(id=user_id or uuid4(), is_superuser=superuser, roles=[role])


def conversation(*, owner_id=None, agent_id=None, title="Conversation"):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        agent=None,
        user_id=owner_id or uuid4(),
        user=None,
        title=title,
        variables={},
        message_count=2,
        token_usage=5,
        created_at=timestamp,
        updated_at=timestamp,
        delete=AsyncMock(),
    )


@pytest.mark.anyio
async def test_detail_admin_skips_agent_scope_when_agent_is_deleted(monkeypatch):
    actor = user(permissions=("admin:dashboard:access",))
    item = conversation(owner_id=uuid4(), agent_id=None)
    access = AsyncMock()

    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(conversations, "get_user_team_agent_ids", access)
    monkeypatch.setattr(
        conversations, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        conversations, "build_message_round_payloads", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        conversations.ConversationOut,
        "model_validate",
        lambda _item: SimpleNamespace(model_dump=lambda: {"id": str(item.id)}),
    )

    result = await conversations.get_conversation_detail(item.id, actor)

    access.assert_not_awaited()
    assert result["data"] | {"messages": []} == {
        "id": str(item.id),
        "agent_name": None,
        "agent_icon": None,
        "messages": [],
        "user_id": str(item.user_id),
        "user_name": None,
    }


@pytest.mark.anyio
async def test_delete_admin_skips_agent_scope_for_deleted_agent_and_audits_title(
    monkeypatch,
):
    actor = user(permissions=("admin:dashboard:access",))
    item = conversation(owner_id=uuid4(), agent_id=None, title="Kept title")
    access = AsyncMock()
    audit = AsyncMock()

    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(conversations, "get_user_team_agent_ids", access)
    monkeypatch.setattr(conversations.Agent, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(conversations.AuditLogService, "log", audit)

    result = await conversations.delete_conversation_admin(
        item.id, SimpleNamespace(), actor
    )

    assert result["data"] == {"id": str(item.id)}
    access.assert_not_awaited()
    item.delete.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == "Kept title"


@pytest.mark.anyio
async def test_batch_delete_permission_loop_and_deleted_agent_branch(monkeypatch):
    actor = user(permissions=("unused", "*"))
    request = SimpleNamespace()
    owned = conversation(owner_id=actor.id, agent_id=None)
    scoped_agent_id = uuid4()
    scoped = conversation(owner_id=uuid4(), agent_id=scoped_agent_id)
    audit = AsyncMock()

    monkeypatch.setattr(
        conversations.Conversation,
        "filter",
        lambda **_kwargs: Query(result=[owned, scoped]),
    )
    monkeypatch.setattr(
        conversations,
        "get_user_team_agent_ids",
        AsyncMock(return_value=[scoped_agent_id]),
    )
    monkeypatch.setattr(conversations.Agent, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(conversations.AuditLogService, "log", audit)

    result = await conversations.batch_delete_conversations(
        ids=[owned.id, scoped.id], request=request, current_user=actor
    )

    assert result["data"]["deleted_count"] == 2
    assert result["data"]["ids"] == [str(owned.id), str(scoped.id)]
    assert audit.await_args.kwargs["metadata"]["ids"] == [
        str(owned.id),
        str(scoped.id),
    ]


@pytest.mark.anyio
async def test_list_conversations_member_without_optional_filters(monkeypatch):
    actor = user()
    agent_id = uuid4()
    item = conversation(owner_id=actor.id, agent_id=agent_id)
    item.agent = SimpleNamespace(name="Agent", icon="bot")
    item.user = SimpleNamespace(username="owner")
    query = Query(result=[item], count=1)

    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
    )
    monkeypatch.setattr(conversations.Conversation, "filter", lambda **_kwargs: query)

    result = await conversations.list_all_conversations(
        team_id=None,
        agent_id=None,
        user_id=uuid4(),
        search=None,
        untitled_only=False,
        page=1,
        page_size=20,
        current_user=actor,
    )

    assert result["data"]["total"] == 1
    assert {"user_id": actor.id} in query.filters


@pytest.mark.anyio
async def test_stats_admin_path_uses_agent_aggregation_and_unknown_name(monkeypatch):
    actor = user(permissions=("admin:dashboard:access",))
    agent_id = uuid4()
    conversation_id = uuid4()

    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
    )

    conversation_queries = [
        Query(count=2, values=[conversation_id]),
        Query(values=[{"agent_id": agent_id, "count": 2}]),
    ]
    monkeypatch.setattr(
        conversations.Conversation,
        "filter",
        lambda **_kwargs: conversation_queries.pop(0),
    )
    monkeypatch.setattr(
        conversations.Message, "filter", lambda **_kwargs: Query(count=5)
    )
    monkeypatch.setattr(
        conversations.Agent, "filter", lambda **_kwargs: Query(values=[])
    )

    result = await conversations.get_conversation_stats(
        team_id=None, current_user=actor
    )

    assert result["data"] == {
        "total_conversations": 2,
        "total_messages": 5,
        "conversations_by_agent": [
            {
                "agent_id": str(agent_id),
                "agent_name": "Unknown",
                "agent_icon": None,
                "count": 2,
            }
        ],
    }


@pytest.mark.anyio
async def test_trends_uses_30_day_empty_access_shape(monkeypatch):
    actor = user(superuser=True)
    fixed_now = datetime(2026, 1, 31, 12, tzinfo=UTC)

    monkeypatch.setattr(conversations, "now", lambda: fixed_now)
    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )

    result = await conversations.get_conversation_trends(
        team_id=None, period="30d", current_user=actor
    )

    assert result["data"]["period"] == "30d"
    assert len(result["data"]["data"]) == 30
    assert result["data"]["data"][0] == {
        "date": "01/02",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
    }


def test_global_dashboard_access_superuser_branch():
    assert conversations._has_global_dashboard_access(user(superuser=True)) is True
    assert (
        conversations._has_global_dashboard_access(user(permissions=("unused",)))
        is False
    )
