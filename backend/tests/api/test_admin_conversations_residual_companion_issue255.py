from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import conversations
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(
        self, result=None, *, first=None, count=0, values=None, values_list=None
    ):
        self.result = result
        self.first_result = first
        self.count_result = count
        self.values_result = values or []
        self.values_list_result = values_list or []
        self.filters = []

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def select_related(self, *_args):
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    async def first(self):
        return self.first_result

    async def count(self):
        return self.count_result

    async def values(self, *_args):
        return self.values_result

    async def values_list(self, *_args, **_kwargs):
        return self.values_list_result

    async def update(self, **_kwargs):
        return 1

    async def delete(self):
        return len(self.result or [])


class Permission:
    def __init__(self, code):
        self.code = code


class Role:
    def __init__(self, *codes):
        self.permissions = [Permission(code) for code in codes]


def user(*, superuser=False, roles=()):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser, roles=list(roles))


def conversation(**overrides):
    now = datetime.now(UTC)
    values = dict(
        id=uuid4(),
        agent_id=uuid4(),
        user_id=uuid4(),
        agent=SimpleNamespace(name="Agent", icon="bot"),
        user=SimpleNamespace(username="owner"),
        title="Support",
        variables={},
        message_count=3,
        token_usage=12,
        created_at=now,
        updated_at=now,
        delete=AsyncMock(),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_list_conversations_combines_team_agent_title_and_search_filters():
    team_ids = [uuid4(), uuid4()]
    accessible = [uuid4(), uuid4()]
    selected = [accessible[1], uuid4()]
    item = conversation(agent_id=accessible[1], title="")
    query = Query(result=[item], count=1)

    with (
        patch.object(conversations, "check_team_access", AsyncMock()) as access,
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query(values_list=[(accessible[0],), accessible[1]]),
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        response = await conversations.list_all_conversations(
            team_id=team_ids,
            agent_id=selected,
            user_id=[item.user_id],
            search="support",
            untitled_only=True,
            page=1,
            page_size=20,
            current_user=user(roles=[Role("admin:dashboard:access")]),
        )

    assert access.await_count == 2
    assert response["data"]["items"][0]["title"] == ""
    assert any(
        kwargs == {"agent_id__in": [accessible[1]]} for _, kwargs in query.filters
    )
    assert any(kwargs == {"user_id__in": [item.user_id]} for _, kwargs in query.filters)
    assert any(kwargs == {"title__icontains": "support"} for _, kwargs in query.filters)
    assert any(args for args, _kwargs in query.filters)


@pytest.mark.anyio
async def test_stats_uses_wildcard_dashboard_access_without_member_scope():
    agent_id = uuid4()
    conv_query = Query(count=1, values_list=[uuid4()])
    stats_query = Query(values=[{"agent_id": agent_id, "count": 1}])

    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(
            conversations.Conversation, "filter", side_effect=[conv_query, stats_query]
        ),
        patch.object(conversations.Message, "filter", return_value=Query(count=2)),
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query(
                values=[{"id": agent_id, "name": "Helper", "icon": "H"}]
            ),
        ),
    ):
        response = await conversations.get_conversation_stats(
            team_id=None,
            current_user=user(roles=[Role("ignored"), Role("*")]),
        )

    assert not any("user_id" in kwargs for _, kwargs in conv_query.filters)
    assert response["data"]["conversations_by_agent"][0]["agent_name"] == "Helper"


@pytest.mark.anyio
async def test_trends_skips_message_lookup_without_conversation_ids():
    current = datetime(2026, 7, 21, 12, tzinfo=UTC)
    conv_query = Query(values=[])

    with (
        patch.object(conversations, "now", return_value=current),
        patch.object(conversations, "to_utc", side_effect=lambda value: value),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(conversations.Conversation, "filter", return_value=conv_query),
        patch.object(conversations.Message, "filter") as message_filter,
    ):
        response = await conversations.get_conversation_trends(
            team_id=None,
            period="7d",
            current_user=user(superuser=True),
        )

    message_filter.assert_not_called()
    assert response["data"]["data"][-1] == {
        "date": "07/21",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
    }


@pytest.mark.anyio
async def test_detail_and_deletes_skip_agent_scope_when_conversation_has_no_agent():
    current_user = user(roles=[Role("admin:dashboard:access")])
    target = conversation(agent_id=None, agent=None, user=None)

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock()
        ) as agent_ids,
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            conversations, "build_message_round_payloads", AsyncMock(return_value=[])
        ),
        patch.object(
            conversations.ConversationOut,
            "model_validate",
            return_value=SimpleNamespace(model_dump=lambda: {"id": str(target.id)}),
        ),
        patch.object(conversations.Message, "filter") as message_filter,
    ):
        detail = await conversations.get_conversation_detail(target.id, current_user)

    agent_ids.assert_not_awaited()
    message_filter.assert_not_called()
    assert detail["data"]["agent_name"] is None
    assert detail["data"]["user_name"] is None

    agent_query = Query()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock()
        ) as agent_ids,
        patch.object(conversations.Agent, "filter", return_value=agent_query),
    ):
        deleted = await conversations.delete_conversation_admin(target.id, current_user)

    agent_ids.assert_not_awaited()
    target.delete.assert_awaited_once()
    assert deleted["data"] == {"id": str(target.id)}


@pytest.mark.anyio
async def test_batch_delete_dashboard_skips_agentless_conversations_and_rejects_foreign():
    current_user = user(roles=[Role("admin:dashboard:access")])
    agent_id = uuid4()
    agentless = conversation(agent_id=None)
    foreign = conversation(agent_id=agent_id)

    with (
        patch.object(
            conversations.Conversation,
            "filter",
            return_value=Query(result=[agentless, foreign]),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.batch_delete_conversations(
            [agentless.id, foreign.id], current_user
        )

    assert (exc_info.value.code, exc_info.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        403,
    )

    delete_query = Query(result=[agentless])
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[Query(result=[agentless]), delete_query],
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        patch.object(conversations.Agent, "filter") as agent_filter,
    ):
        response = await conversations.batch_delete_conversations(
            [agentless.id], current_user
        )

    agent_filter.assert_not_called()
    assert response["data"] == {
        "deleted_count": 1,
        "ids": [str(agentless.id)],
    }
