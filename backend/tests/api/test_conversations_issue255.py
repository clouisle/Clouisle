from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import conversations
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result=None, *, count=0, values=None, values_list=None):
        self.result = [] if result is None else result
        self.count_result = count
        self.values_result = [] if values is None else values
        self.values_list_result = [] if values_list is None else values_list
        self.calls = []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._chain("filter", *args, **kwargs)

    def select_related(self, *args):
        return self._chain("select_related", *args)

    def prefetch_related(self, *args):
        return self._chain("prefetch_related", *args)

    def order_by(self, *args):
        return self._chain("order_by", *args)

    def offset(self, value):
        return self._chain("offset", value)

    def limit(self, value):
        return self._chain("limit", value)

    def annotate(self, **kwargs):
        return self._chain("annotate", **kwargs)

    def group_by(self, *args):
        return self._chain("group_by", *args)

    async def first(self):
        return self.result

    async def count(self):
        return self.count_result

    async def all(self):
        return self.result

    async def values(self, *args):
        self._chain("values", *args)
        return self.values_result

    async def values_list(self, *args, **kwargs):
        self._chain("values_list", *args, **kwargs)
        return self.values_list_result

    async def update(self, **kwargs):
        self._chain("update", **kwargs)
        return 1

    async def delete(self):
        self._chain("delete")
        return len(self.result)

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def user(*, superuser=False, permissions=()):
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=superuser,
        roles=[
            SimpleNamespace(
                permissions=[SimpleNamespace(code=code) for code in permissions]
            )
        ],
    )


def conversation(**overrides):
    timestamp = datetime.now(UTC)
    owner_id = uuid4()
    values = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "user_id": owner_id,
        "agent": SimpleNamespace(name="Helper", icon="bot"),
        "user": SimpleNamespace(id=owner_id, username="owner"),
        "title": "Support",
        "variables": {"locale": "en"},
        "message_count": 2,
        "token_usage": 11,
        "created_at": timestamp,
        "updated_at": timestamp,
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_team_access_and_admin_access_boundaries():
    member = user()
    team = SimpleNamespace(id=uuid4())
    membership = SimpleNamespace(role="admin")

    with patch.object(conversations.Team, "filter", return_value=Query(False)):
        with pytest.raises(BusinessError) as exc:
            await conversations.check_team_access(team.id, member)
    assert exc.value.status_code == 404

    with (
        patch.object(conversations.Team, "filter", return_value=Query(team)),
        patch.object(conversations.TeamMember, "filter", return_value=Query(False)),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.check_team_access(team.id, member)
    assert exc.value.status_code == 403

    with patch.object(
        conversations.TeamMember, "filter", return_value=Query(membership)
    ):
        assert await conversations.has_conversation_team_admin_access(member, team.id)
    assert not await conversations.has_conversation_team_admin_access(member, None)
    with patch.object(conversations.Team, "filter", return_value=Query(team)):
        assert (
            await conversations.check_team_access(team.id, user(superuser=True)) is team
        )


@pytest.mark.anyio
async def test_get_user_team_agent_ids_covers_scopes_and_tuple_rows():
    member = user()
    team_id = uuid4()
    agent_ids = [uuid4(), uuid4()]
    check_access = AsyncMock()

    with (
        patch.object(conversations, "check_team_access", check_access),
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query(values_list=[(agent_ids[0],), agent_ids[1]]),
        ),
    ):
        assert await conversations.get_user_team_agent_ids(member, team_id) == agent_ids
    check_access.assert_awaited_once_with(team_id, member)

    with patch.object(
        conversations.Agent,
        "all",
        return_value=Query(values_list=[(agent_ids[0],), agent_ids[1]]),
    ):
        assert (
            await conversations.get_user_team_agent_ids(user(superuser=True))
            == agent_ids
        )

    team_ids = [uuid4(), uuid4()]
    with (
        patch.object(
            conversations.TeamMember,
            "filter",
            return_value=Query(values_list=[(team_ids[0],), team_ids[1]]),
        ),
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query(values_list=agent_ids),
        ) as agent_filter,
    ):
        assert await conversations.get_user_team_agent_ids(member) == agent_ids
    assert agent_filter.call_args.kwargs == {"team_id__in": team_ids}


@pytest.mark.anyio
async def test_list_conversations_member_filters_and_serializes():
    current_user = user()
    item = conversation(user_id=current_user.id)
    query = Query([item], count=1)

    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            AsyncMock(return_value=[item.agent_id]),
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        result = await conversations.list_all_conversations(
            team_id=None,
            agent_id=item.agent_id,
            user_id=uuid4(),
            search="support",
            untitled_only=False,
            page=2,
            page_size=5,
            current_user=current_user,
        )

    assert result["data"]["total"] == 1
    assert result["data"]["items"][0]["agent_name"] == "Helper"
    assert ("filter", (), {"user_id": current_user.id}) in query.calls
    assert ("filter", (), {"agent_id": item.agent_id}) in query.calls
    assert ("filter", (), {"title__icontains": "support"}) in query.calls
    assert ("offset", (5,), {}) in query.calls


@pytest.mark.anyio
async def test_list_conversations_empty_and_inaccessible_agent_short_circuits():
    current_user = user()
    common = {
        "team_id": None,
        "user_id": None,
        "search": None,
        "untitled_only": False,
        "page": 3,
        "page_size": 10,
        "current_user": current_user,
    }
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
    ):
        empty = await conversations.list_all_conversations(agent_id=None, **common)

    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=True),
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            AsyncMock(return_value=[uuid4()]),
        ),
        patch.object(conversations.Conversation, "filter", return_value=Query()),
    ):
        inaccessible = await conversations.list_all_conversations(
            agent_id=uuid4(), **common
        )

    assert (
        empty["data"]
        == inaccessible["data"]
        == {
            "items": [],
            "total": 0,
            "page": 3,
            "page_size": 10,
        }
    )


@pytest.mark.anyio
async def test_list_admin_filters_user_and_untitled():
    current_user = user(permissions=("admin:dashboard:access",))
    query = Query([], count=0)
    owner_id = uuid4()
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=True),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        await conversations.list_all_conversations(
            team_id=None,
            agent_id=None,
            user_id=owner_id,
            search="ignored",
            untitled_only=True,
            page=1,
            page_size=20,
            current_user=current_user,
        )
    assert ("filter", (), {"user_id": owner_id}) in query.calls
    assert any(name == "filter" and args for name, args, _ in query.calls)


@pytest.mark.anyio
async def test_stats_empty_and_member_aggregation():
    current_user = user()
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
    ):
        empty = await conversations.get_conversation_stats(None, current_user)
    assert empty["data"]["total_conversations"] == 0

    agent_id = uuid4()
    conv_query = Query(count=3, values_list=[uuid4(), uuid4()])
    stats_query = Query(values=[{"agent_id": agent_id, "count": 3}])
    agent_query = Query(values=[{"id": agent_id, "name": "Helper", "icon": "bot"}])
    conversation_filters = [conv_query, stats_query]
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=conversation_filters,
        ),
        patch.object(conversations.Message, "filter", return_value=Query(count=7)),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
    ):
        result = await conversations.get_conversation_stats(None, current_user)

    assert result["data"] == {
        "total_conversations": 3,
        "total_messages": 7,
        "conversations_by_agent": [
            {
                "agent_id": str(agent_id),
                "agent_name": "Helper",
                "agent_icon": "bot",
                "count": 3,
            }
        ],
    }
    assert ("filter", (), {"user_id": current_user.id}) in conv_query.calls


@pytest.mark.anyio
async def test_trends_empty_defaults_invalid_period_to_seven_days():
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    with (
        patch.object(conversations, "now", return_value=fixed_now),
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
    ):
        result = await conversations.get_conversation_trends(None, "unexpected", user())

    assert result["data"]["period"] == "unexpected"
    assert len(result["data"]["data"]) == 7
    assert result["data"]["data"][-1] == {
        "date": "07/21",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
    }


@pytest.mark.anyio
async def test_trends_counts_messages_tokens_and_team_users():
    current_user = user(permissions=("admin:dashboard:access",))
    team_id = uuid4()
    agent_id = uuid4()
    owner_id = uuid4()
    fixed_now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    conv = conversation(agent_id=agent_id, user_id=owner_id)
    conv_query = Query([conv], count=1, values_list=[conv.id])
    membership = SimpleNamespace(user=SimpleNamespace(id=owner_id, username="owner"))
    message_queries = []

    def message_filter(**kwargs):
        if kwargs.get("token_usage__isnull") is False:
            query = Query(
                [
                    SimpleNamespace(
                        conversation=conv, token_usage={"prompt": 2, "completion": 3}
                    )
                ],
                values=[{"token_usage": {"prompt": 2, "completion": 3}}],
            )
        else:
            query = Query(count=4)
        message_queries.append(query)
        return query

    with (
        patch.object(conversations, "now", return_value=fixed_now),
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=True),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(conversations.Conversation, "filter", return_value=conv_query),
        patch.object(
            conversations.TeamMember,
            "filter",
            return_value=Query([membership]),
        ),
        patch.object(conversations.Message, "filter", side_effect=message_filter),
    ):
        result = await conversations.get_conversation_trends(
            team_id, "7d", current_user
        )

    last = result["data"]["data"][-1]
    assert last["conversations"] == 1
    assert last["messages"] == 4
    assert last["tokens"] == 5
    assert last["users"][str(owner_id)] == {
        "name": "owner",
        "conversations": 1,
        "tokens": 5,
    }


@pytest.mark.anyio
async def test_detail_not_found_and_owner_authorization():
    current_user = user()
    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(False)),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.get_conversation_detail(uuid4(), current_user)
    assert exc.value.status_code == 404

    foreign = conversation()
    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(foreign)),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.get_conversation_detail(foreign.id, current_user)
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_detail_admin_scope_denied_and_owner_serializes_versions():
    admin = user(permissions=("admin:dashboard:access",))
    foreign = conversation()
    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(foreign)),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.get_conversation_detail(foreign.id, admin)
    assert exc.value.status_code == 403

    owner = user()
    root_id = uuid4()
    child_id = uuid4()
    messages = [
        SimpleNamespace(
            id=root_id, parent_id=None, round_id=None, is_round_canonical=True
        ),
        SimpleNamespace(
            id=child_id, parent_id=root_id, round_id=None, is_round_canonical=True
        ),
    ]
    item = conversation(user_id=owner.id)
    payloads = [{"id": str(root_id)}, {"id": str(child_id)}]
    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(item)),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(return_value=messages),
        ),
        patch.object(
            conversations.Message,
            "filter",
            return_value=Query(values=[{"parent_id": root_id, "count": 1}]),
        ),
        patch.object(
            conversations,
            "build_message_round_payloads",
            AsyncMock(return_value=payloads),
        ),
    ):
        result = await conversations.get_conversation_detail(item.id, owner)

    assert [message["version_count"] for message in result["data"]["messages"]] == [
        2,
        2,
    ]
    assert result["data"]["user_name"] == "owner"


@pytest.mark.anyio
async def test_delete_updates_stats_deletes_and_audits():
    current_user = user()
    item = conversation(user_id=current_user.id, title=None)
    update_query = Query()
    request = MagicMock()
    audit = AsyncMock()

    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(item)),
        patch.object(conversations.Agent, "filter", return_value=update_query),
        patch.object(conversations.AuditLogService, "log", audit),
    ):
        result = await conversations.delete_conversation_admin(
            item.id, request, current_user
        )

    assert result["data"] == {"id": str(item.id)}
    assert any(name == "update" for name, _, _ in update_query.calls)
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == str(item.id)


@pytest.mark.anyio
async def test_delete_persistence_error_stops_delete_and_audit():
    current_user = user()
    item = conversation(user_id=current_user.id)
    update_query = Query()
    update_query.update = AsyncMock(side_effect=RuntimeError("database unavailable"))
    audit = AsyncMock()

    with (
        patch.object(conversations.Conversation, "filter", return_value=Query(item)),
        patch.object(conversations.Agent, "filter", return_value=update_query),
        patch.object(conversations.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await conversations.delete_conversation_admin(
            item.id, MagicMock(), current_user
        )

    item.delete.assert_not_awaited()
    audit.assert_not_awaited()


@pytest.mark.anyio
async def test_batch_delete_authorization_empty_and_success():
    current_user = user()
    with (
        patch.object(conversations.Conversation, "filter", return_value=Query([])),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.batch_delete_conversations(
            ids=[uuid4()], request=MagicMock(), current_user=current_user
        )
    assert exc.value.status_code == 404

    foreign = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query([foreign])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.batch_delete_conversations(
            ids=[foreign.id], request=MagicMock(), current_user=current_user
        )
    assert exc.value.status_code == 404

    owned = [
        conversation(user_id=current_user.id),
        conversation(user_id=current_user.id),
    ]
    ids = [item.id for item in owned]
    update_queries = [Query(), Query()]
    conversation_queries = [Query(owned), Query(owned)]
    audit = AsyncMock()
    with (
        patch.object(
            conversations.Conversation, "filter", side_effect=conversation_queries
        ),
        patch.object(conversations.Agent, "filter", side_effect=update_queries),
        patch.object(conversations.AuditLogService, "log", audit),
    ):
        result = await conversations.batch_delete_conversations(
            ids=ids, request=MagicMock(), current_user=current_user
        )

    assert result["data"] == {"deleted_count": 2, "ids": [str(value) for value in ids]}
    assert all(
        any(name == "update" for name, _, _ in query.calls) for query in update_queries
    )
    assert audit.await_args.kwargs["metadata"]["deleted_count"] == 2


@pytest.mark.anyio
async def test_batch_delete_error_stops_delete_and_audit():
    current_user = user(superuser=True)
    item = conversation()
    update_query = Query()
    update_query.update = AsyncMock(side_effect=RuntimeError("write failed"))
    delete_query = Query([item])
    audit = AsyncMock()

    with (
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[Query([item]), delete_query],
        ),
        patch.object(conversations.Agent, "filter", return_value=update_query),
        patch.object(conversations.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="write failed"),
    ):
        await conversations.batch_delete_conversations(
            ids=[item.id], request=MagicMock(), current_user=current_user
        )

    assert not delete_query.calls
    audit.assert_not_awaited()
