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
        self.update = AsyncMock(return_value=1)

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def values(self, *_args):
        return self.values_value

    async def values_list(self, *_args, **_kwargs):
        return self.result

    async def all(self):
        return self.result


def user(*, permissions=()):
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        roles=[
            SimpleNamespace(
                permissions=[SimpleNamespace(code=code) for code in permissions]
            )
        ],
    )


@pytest.mark.anyio
async def test_trends_member_counts_multiple_token_rows_without_admin_user_breakdown(
    monkeypatch,
):
    actor = user()
    conversation_id = uuid4()
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    conversation_query = Query(result=[conversation_id], count=1)

    def message_filter(**kwargs):
        if kwargs.get("token_usage__isnull") is False:
            return Query(
                values=[
                    {"token_usage": {"prompt": 2, "completion": None}},
                    {"token_usage": {"prompt": 3, "completion": 4}},
                ]
            )
        return Query(count=2)

    monkeypatch.setattr(conversations, "now", lambda: fixed_now)
    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        conversations,
        "get_user_team_agent_ids",
        AsyncMock(return_value=[uuid4()]),
    )
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(conversations.Message, "filter", message_filter)

    result = await conversations.get_conversation_trends(None, "7d", actor)

    assert {"user_id": actor.id} in conversation_query.filters
    assert result["data"]["data"][-1] == {
        "date": "07/21",
        "conversations": 1,
        "messages": 2,
        "tokens": 9,
        "users": {},
    }


@pytest.mark.anyio
async def test_trends_admin_skips_unknown_users_before_counting_known_user_tokens(
    monkeypatch,
):
    actor = user(permissions=("admin:dashboard:access",))
    team_id = uuid4()
    known_user_id = uuid4()
    unknown_user_id = uuid4()
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    day_conversations = [
        SimpleNamespace(user_id=unknown_user_id),
        SimpleNamespace(user_id=known_user_id),
    ]
    conversation_query = Query(result=day_conversations, count=2)
    membership = SimpleNamespace(
        user=SimpleNamespace(id=known_user_id, username="known")
    )

    def message_filter(**kwargs):
        if kwargs.get("token_usage__isnull") is False:
            return Query(
                result=[
                    SimpleNamespace(
                        conversation=SimpleNamespace(user_id=unknown_user_id),
                        token_usage={"prompt": 50, "completion": 50},
                    ),
                    SimpleNamespace(
                        conversation=SimpleNamespace(user_id=known_user_id),
                        token_usage={"prompt": 2, "completion": 3},
                    ),
                ],
                values=[{"token_usage": {"prompt": 2, "completion": 3}}],
            )
        return Query(count=2)

    monkeypatch.setattr(conversations, "now", lambda: fixed_now)
    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        conversations,
        "get_user_team_agent_ids",
        AsyncMock(return_value=[uuid4()]),
    )
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(
        conversations.TeamMember,
        "filter",
        lambda **_kwargs: Query(result=[membership]),
    )
    monkeypatch.setattr(conversations.Message, "filter", message_filter)

    result = await conversations.get_conversation_trends(team_id, "7d", actor)

    assert result["data"]["data"][-1]["users"][str(known_user_id)] == {
        "name": "known",
        "conversations": 1,
        "tokens": 5,
    }


@pytest.mark.anyio
async def test_trends_dashboard_without_team_uses_empty_id_fallback(monkeypatch):
    actor = user(permissions=("admin:dashboard:access",))
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    conversation_query = Query(result=[])
    message_filter = AsyncMock()

    monkeypatch.setattr(conversations, "now", lambda: fixed_now)
    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        conversations,
        "get_user_team_agent_ids",
        AsyncMock(return_value=[uuid4()]),
    )
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(conversations.Message, "filter", message_filter)

    result = await conversations.get_conversation_trends(None, "7d", actor)

    message_filter.assert_not_called()
    assert result["data"]["data"][-1]["messages"] == 0
    assert result["data"]["data"][-1]["tokens"] == 0


@pytest.mark.anyio
async def test_detail_admin_scans_permission_then_accepts_accessible_agent(monkeypatch):
    actor = user(permissions=("conversation:read", "admin:dashboard:access"))
    agent_id = uuid4()
    item = SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        user_id=uuid4(),
        agent=None,
        user=None,
    )
    access = AsyncMock(return_value=[agent_id])

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

    access.assert_awaited_once_with(actor)
    assert result["data"]["messages"] == []


@pytest.mark.anyio
async def test_delete_admin_scans_permission_then_accepts_accessible_agent_and_audits(
    monkeypatch,
):
    actor = user(permissions=("conversation:delete", "*"))
    agent_id = uuid4()
    item = SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id,
        user_id=uuid4(),
        message_count=4,
        title="Audited",
        delete=AsyncMock(),
    )
    agent_query = Query()
    access = AsyncMock(return_value=[agent_id])
    audit = AsyncMock()

    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(conversations, "get_user_team_agent_ids", access)
    monkeypatch.setattr(conversations.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(conversations.AuditLogService, "log", audit)

    result = await conversations.delete_conversation_admin(
        item.id, SimpleNamespace(), actor
    )

    access.assert_awaited_once_with(actor)
    agent_query.update.assert_awaited_once()
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert result["data"] == {"id": str(item.id)}
