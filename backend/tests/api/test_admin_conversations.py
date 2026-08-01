from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch
from uuid import uuid4

import pytest

from tortoise.expressions import Q

from app.api.v1.admin.endpoints import conversations
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(
        self,
        result=None,
        *,
        first=None,
        count=0,
        values=None,
        values_list=None,
        delete=0,
    ):
        self.result = result
        self.first_result = first
        self.count_result = count
        self.values_result = values or []
        self.values_list_result = values_list or []
        self.delete_result = delete
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

    def offset(self, _value):
        return self

    def limit(self, _value):
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
        return self.delete_result


def user(*, superuser=False, dashboard=False):
    permissions = [SimpleNamespace(code="admin:dashboard:access")] if dashboard else []
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=superuser,
        roles=[SimpleNamespace(permissions=permissions)],
    )


def conversation(**overrides):
    timestamp = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "agent_id": uuid4(),
        "user_id": uuid4(),
        "agent": SimpleNamespace(name="Agent", icon="bot"),
        "user": SimpleNamespace(username="owner"),
        "title": "Support",
        "variables": {},
        "message_count": 3,
        "token_usage": 12,
        "created_at": timestamp,
        "updated_at": timestamp,
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_check_team_access_handles_missing_membership_and_superuser():
    team = SimpleNamespace(id=uuid4())
    member = user()

    with patch.object(conversations.Team, "filter", return_value=Query(first=None)):
        with pytest.raises(BusinessError) as exc:
            await conversations.check_team_access(team.id, member)
    assert (exc.value.code, exc.value.status_code) == (ResponseCode.TEAM_NOT_FOUND, 404)

    with (
        patch.object(conversations.Team, "filter", return_value=Query(first=team)),
        patch.object(
            conversations.TeamMember, "filter", return_value=Query(first=None)
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.check_team_access(team.id, member)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.NOT_TEAM_MEMBER,
        403,
    )

    with patch.object(conversations.Team, "filter", return_value=Query(first=team)):
        assert (
            await conversations.check_team_access(team.id, user(superuser=True)) is team
        )


@pytest.mark.anyio
async def test_get_user_team_agent_ids_scopes_members_and_normalizes_rows():
    current_user = user()
    team_ids = [uuid4(), uuid4()]
    agent_ids = [uuid4(), uuid4()]
    membership_query = Query(values_list=[(team_ids[0],), team_ids[1]])
    agent_query = Query(values_list=agent_ids)

    with (
        patch.object(conversations.TeamMember, "filter", return_value=membership_query),
        patch.object(
            conversations.Agent, "filter", return_value=agent_query
        ) as agent_filter,
    ):
        result = await conversations.get_user_team_agent_ids(current_user)

    assert result == agent_ids
    agent_filter.assert_called_once_with(team_id__in=team_ids)


@pytest.mark.anyio
async def test_list_conversations_applies_member_scope_and_filters():
    current_user = user()
    accessible = [uuid4(), uuid4()]
    selected = [accessible[1], uuid4()]
    item = conversation(agent_id=accessible[1], user_id=current_user.id)
    query = Query(result=[item], count=1)

    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=accessible)
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        response = await conversations.list_all_conversations(
            team_id=None,
            agent_id=selected,
            user_id=[uuid4()],
            search="support",
            untitled_only=True,
            page=2,
            page_size=5,
            current_user=current_user,
        )

    assert response["data"] == {
        "items": [
            {
                "id": str(item.id),
                "agent_id": str(item.agent_id),
                "agent_name": "Agent",
                "agent_icon": "bot",
                "title": "Support",
                "message_count": 3,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "user_id": str(current_user.id),
                "user_name": "owner",
            }
        ],
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    assert any(kwargs == {"user_id": current_user.id} for _, kwargs in query.filters)
    assert any(
        kwargs == {"agent_id__in": [accessible[1]]} for _, kwargs in query.filters
    )

    def _q_has_filter(node: Q, field: str) -> bool:
        if field in node.filters:
            return True
        return any(_q_has_filter(child, field) for child in node.children)

    assert any(
        args
        and isinstance(args[0], Q)
        and _q_has_filter(args[0], "title__icontains")
        and _q_has_filter(args[0], "id__icontains")
        for args, _ in query.filters
    )


@pytest.mark.anyio
async def test_list_conversations_returns_empty_for_inaccessible_agent_filter():
    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(conversations.Conversation, "filter", return_value=Query()),
    ):
        response = await conversations.list_all_conversations(
            team_id=None,
            agent_id=[uuid4()],
            user_id=None,
            search=None,
            untitled_only=False,
            page=1,
            page_size=20,
            current_user=user(superuser=True),
        )

    assert response["data"]["items"] == []
    assert response["data"]["total"] == 0


@pytest.mark.anyio
async def test_stats_aggregate_conversations_messages_and_agents():
    current_user = user(dashboard=True)
    agent_id = uuid4()
    conv_query = Query(count=2, values_list=[uuid4(), uuid4()])
    message_query = Query(count=7)
    stats_query = Query(values=[{"agent_id": agent_id, "count": 2}])
    agent_query = Query(values=[{"id": agent_id, "name": "Helper", "icon": None}])

    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[conv_query, stats_query],
        ),
        patch.object(conversations.Message, "filter", return_value=message_query),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
    ):
        response = await conversations.get_conversation_stats(
            team_id=None, current_user=current_user
        )

    assert response["data"] == {
        "total_conversations": 2,
        "total_messages": 7,
        "conversations_by_agent": [
            {
                "agent_id": str(agent_id),
                "agent_name": "Helper",
                "agent_icon": None,
                "count": 2,
            }
        ],
    }


@pytest.mark.anyio
async def test_trends_group_messages_and_tokens_by_local_date():
    current = datetime(2026, 7, 21, 12, tzinfo=UTC)
    agent_id = uuid4()
    conv_id = uuid4()
    conv_query = Query(values=[{"id": conv_id, "created_at": current}])
    message_query = Query(
        values=[
            {
                "created_at": current,
                "token_usage": {"prompt": 2, "completion": 3},
            },
            {"created_at": current, "token_usage": None},
        ]
    )

    with (
        patch.object(conversations, "now", return_value=current),
        patch.object(conversations, "to_utc", side_effect=lambda value: value),
        patch.object(conversations, "to_local", side_effect=lambda value: value),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(conversations.Conversation, "filter", return_value=conv_query),
        patch.object(conversations.Message, "filter", return_value=message_query),
    ):
        response = await conversations.get_conversation_trends(
            team_id=None, period="7d", current_user=user(superuser=True)
        )

    assert response["data"]["data"][-1] == {
        "date": "07/21",
        "conversations": 1,
        "messages": 2,
        "tokens": 5,
    }


@pytest.mark.anyio
async def test_detail_rejects_missing_and_out_of_scope_conversations():
    current_user = user()
    missing_id = uuid4()
    with patch.object(
        conversations.Conversation, "filter", return_value=Query(first=None)
    ):
        with pytest.raises(BusinessError) as exc:
            await conversations.get_conversation_detail(missing_id, current_user)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.CONVERSATION_NOT_FOUND,
        404,
    )

    target = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.get_conversation_detail(target.id, current_user)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        404,
    )


@pytest.mark.anyio
async def test_detail_serializes_visible_messages_and_version_counts():
    current_user = user(superuser=True)
    target = conversation(user_id=current_user.id)
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
    child_counts = Query(values=[{"parent_id": root_id, "count": 1}])
    payloads = [{"id": root_id}, {"id": child_id}]

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(return_value=messages),
        ),
        patch.object(conversations.Message, "filter", return_value=child_counts),
        patch.object(
            conversations,
            "build_message_round_payloads",
            AsyncMock(return_value=payloads),
        ),
    ):
        response = await conversations.get_conversation_detail(target.id, current_user)

    assert [message["version_count"] for message in response["data"]["messages"]] == [
        2,
        2,
    ]
    assert response["data"]["user_name"] == "owner"
    assert response["data"]["agent_name"] == "Agent"


@pytest.mark.anyio
async def test_detail_propagates_message_provider_failure():
    target = conversation()
    failure = RuntimeError("message store unavailable")
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(side_effect=failure),
        ),
        pytest.raises(RuntimeError, match="message store unavailable"),
    ):
        await conversations.get_conversation_detail(target.id, user(superuser=True))


@pytest.mark.anyio
async def test_delete_updates_stats_then_deletes_conversation():
    current_user = user()
    target = conversation(user_id=current_user.id)
    agent_query = Query()

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
    ):
        response = await conversations.delete_conversation_admin(
            target.id, current_user
        )

    assert response["data"] == {"id": str(target.id)}
    target.delete.assert_awaited_once_with()


@pytest.mark.anyio
async def test_delete_does_not_remove_conversation_when_stats_update_fails():
    target = conversation()
    agent_query = Query()
    agent_query.update = AsyncMock(side_effect=RuntimeError("database unavailable"))

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await conversations.delete_conversation_admin(target.id, user(superuser=True))

    target.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_batch_delete_groups_agent_stats_and_returns_deleted_ids():
    current_user = user(superuser=True)
    shared_agent = uuid4()
    ids = [uuid4(), uuid4(), uuid4()]
    targets = [
        conversation(id=ids[0], agent_id=shared_agent, message_count=2),
        conversation(id=ids[1], agent_id=shared_agent, message_count=4),
        conversation(id=ids[2], agent_id=None, message_count=1),
    ]
    initial_query = Query(result=targets)
    delete_query = Query(delete=3)
    agent_query = Query()

    with (
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[initial_query, delete_query],
        ),
        patch.object(
            conversations.Agent, "filter", return_value=agent_query
        ) as agent_filter,
    ):
        response = await conversations.batch_delete_conversations(ids, current_user)

    assert response["data"] == {
        "deleted_count": 3,
        "ids": [str(value) for value in ids],
    }
    agent_filter.assert_called_once_with(id=shared_agent)


@pytest.mark.anyio
async def test_batch_delete_rejects_empty_and_foreign_conversations():
    current_user = user()
    with patch.object(
        conversations.Conversation, "filter", return_value=Query(result=[])
    ):
        with pytest.raises(BusinessError) as exc:
            await conversations.batch_delete_conversations([uuid4()], current_user)
    assert exc.value.status_code == 404

    target = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(result=[target])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.batch_delete_conversations([target.id], current_user)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        404,
    )


def test_router_declares_pagination_and_uuid_validation():
    list_route = next(
        route for route in conversations.router.routes if route.path == ""
    )
    page = next(
        field for field in list_route.dependant.query_params if field.name == "page"
    )
    page_size = next(
        field
        for field in list_route.dependant.query_params
        if field.name == "page_size"
    )
    batch_route = next(
        route
        for route in conversations.router.routes
        if route.path == "" and "DELETE" in route.methods
    )
    ids = next(
        field for field in batch_route.dependant.query_params if field.name == "ids"
    )

    assert page.field_info.metadata[0].ge == 1
    assert page_size.field_info.metadata[0].ge == 1
    assert page_size.field_info.metadata[1].le == 100
    assert ids.field_info.is_required()
    assert ids.field_info.annotation == list[conversations.UUID]


@pytest.mark.anyio
async def test_team_access_and_agent_ids_cover_authorized_paths():
    current_user = user()
    team = SimpleNamespace(id=uuid4())
    agent_ids = [uuid4(), uuid4()]

    with (
        patch.object(conversations.Team, "filter", return_value=Query(first=team)),
        patch.object(
            conversations.TeamMember,
            "filter",
            return_value=Query(first=SimpleNamespace()),
        ),
    ):
        assert await conversations.check_team_access(team.id, current_user) is team

    with (
        patch.object(
            conversations, "check_team_access", AsyncMock(return_value=team)
        ) as access,
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query(values_list=[(agent_ids[0],), agent_ids[1]]),
        ),
    ):
        assert (
            await conversations.get_user_team_agent_ids(current_user, team.id)
            == agent_ids
        )
    access.assert_awaited_once_with(team.id, current_user)

    with patch.object(
        conversations.Agent,
        "all",
        return_value=Query(values_list=[(agent_ids[0],), agent_ids[1]]),
    ):
        assert (
            await conversations.get_user_team_agent_ids(user(superuser=True))
            == agent_ids
        )


@pytest.mark.anyio
async def test_list_conversations_handles_empty_access_and_team_admin_filters():
    current_user = user(dashboard=True)
    with patch.object(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    ):
        empty = await conversations.list_all_conversations(
            team_id=None,
            agent_id=None,
            user_id=None,
            search=None,
            untitled_only=False,
            page=3,
            page_size=8,
            current_user=current_user,
        )
    assert empty["data"] == {"items": [], "total": 0, "page": 3, "page_size": 8}

    team_ids = [uuid4(), uuid4()]
    accessible = [uuid4(), uuid4()]
    owner_id = uuid4()
    item = conversation(
        agent_id=accessible[0],
        user_id=None,
        agent=None,
        user=None,
        title=None,
    )
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
            agent_id=None,
            user_id=[owner_id],
            search=None,
            untitled_only=False,
            page=1,
            page_size=20,
            current_user=current_user,
        )

    assert access.await_args_list == [call(value, current_user) for value in team_ids]
    assert any(kwargs == {"user_id__in": [owner_id]} for _, kwargs in query.filters)
    assert response["data"]["items"][0] | {
        "created_at": None,
        "updated_at": None,
    } == {
        "id": str(item.id),
        "agent_id": str(item.agent_id),
        "agent_name": None,
        "agent_icon": None,
        "title": None,
        "message_count": 3,
        "created_at": None,
        "updated_at": None,
        "user_id": None,
        "user_name": None,
    }


@pytest.mark.anyio
async def test_list_conversations_recognizes_wildcard_permission():
    current_user = user()
    current_user.roles = [
        SimpleNamespace(permissions=[SimpleNamespace(code="ignored")]),
        SimpleNamespace(permissions=[SimpleNamespace(code="*")]),
    ]
    query = Query(result=[], count=0)
    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[uuid4()])
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        await conversations.list_all_conversations(
            team_id=None,
            agent_id=None,
            user_id=None,
            search=None,
            untitled_only=False,
            page=1,
            page_size=20,
            current_user=current_user,
        )
    assert not any("user_id" in kwargs for _, kwargs in query.filters)


@pytest.mark.anyio
async def test_stats_handles_empty_access_and_member_unknown_agent():
    with patch.object(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    ):
        response = await conversations.get_conversation_stats(
            team_id=None, current_user=user()
        )
    assert response["data"] == {
        "total_conversations": 0,
        "total_messages": 0,
        "conversations_by_agent": [],
    }

    current_user = user()
    agent_id = uuid4()
    conv_query = Query(count=1, values_list=[uuid4()])
    stats_query = Query(values=[{"agent_id": agent_id, "count": 1}])
    with (
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[conv_query, stats_query],
        ) as conversation_filter,
        patch.object(conversations.Message, "filter", return_value=Query(count=2)),
        patch.object(conversations.Agent, "filter", return_value=Query(values=[])),
        patch.object(conversations, "t", return_value="Unknown"),
    ):
        response = await conversations.get_conversation_stats(
            team_id=None, current_user=current_user
        )

    assert any(
        kwargs.get("user_id") == current_user.id
        for call in conversation_filter.call_args_list
        for kwargs in [call.kwargs]
    )
    assert response["data"]["conversations_by_agent"] == [
        {
            "agent_id": str(agent_id),
            "agent_name": "Unknown",
            "agent_icon": None,
            "count": 1,
        }
    ]


@pytest.mark.anyio
async def test_trends_returns_30_empty_points_without_agents():
    current = datetime(2026, 7, 21, 12, tzinfo=UTC)
    with (
        patch.object(conversations, "now", return_value=current),
        patch.object(conversations, "to_utc", side_effect=lambda value: value),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
    ):
        response = await conversations.get_conversation_trends(
            team_id=None, period="30d", current_user=user()
        )

    assert response["data"]["period"] == "30d"
    assert len(response["data"]["data"]) == 30
    assert response["data"]["data"][0] == {
        "date": "06/22",
        "conversations": 0,
        "messages": 0,
        "tokens": 0,
    }
    assert response["data"]["data"][-1]["date"] == "07/21"


@pytest.mark.anyio
async def test_trends_scopes_member_and_skips_message_query_without_conversations():
    current = datetime(2026, 7, 21, 12, tzinfo=UTC)
    current_user = user()
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
            team_id=None, period="unexpected", current_user=current_user
        )

    assert any(
        kwargs == {"user_id": current_user.id} for _, kwargs in conv_query.filters
    )
    message_filter.assert_not_called()
    assert response["data"]["period"] == "unexpected"
    assert len(response["data"]["data"]) == 7


@pytest.mark.anyio
async def test_detail_admin_scope_empty_messages_and_nullable_relations():
    current_user = user(dashboard=True)
    accessible_agent = uuid4()
    target = conversation(
        agent_id=accessible_agent,
        user_id=current_user.id,
        agent=None,
        user=None,
    )
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            AsyncMock(return_value=[accessible_agent]),
        ),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(return_value=[]),
        ),
        patch.object(
            conversations,
            "build_message_round_payloads",
            AsyncMock(return_value=[]),
        ),
        patch.object(conversations.Message, "filter") as message_filter,
    ):
        response = await conversations.get_conversation_detail(target.id, current_user)

    message_filter.assert_not_called()
    assert response["data"]["messages"] == []
    assert response["data"]["agent_name"] is None
    assert response["data"]["agent_icon"] is None
    assert response["data"]["user_name"] is None


@pytest.mark.anyio
async def test_detail_admin_rejects_foreign_agent_and_defaults_version_count():
    current_user = user(dashboard=True)
    target = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.get_conversation_detail(target.id, current_user)
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        403,
    )

    root = SimpleNamespace(
        id=uuid4(), parent_id=None, round_id=None, is_round_canonical=True
    )
    noncanonical = SimpleNamespace(
        id=uuid4(), parent_id=None, round_id=uuid4(), is_round_canonical=False
    )
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            AsyncMock(return_value=[root, noncanonical]),
        ),
        patch.object(conversations.Message, "filter", return_value=Query(values=[])),
        patch.object(
            conversations,
            "build_message_round_payloads",
            AsyncMock(return_value=[{"id": root.id}]),
        ),
    ):
        response = await conversations.get_conversation_detail(
            target.id, user(superuser=True)
        )
    assert response["data"]["messages"][0]["version_count"] == 1


@pytest.mark.anyio
async def test_single_delete_rejects_missing_foreign_member_and_foreign_admin():
    target_id = uuid4()
    with patch.object(
        conversations.Conversation, "filter", return_value=Query(first=None)
    ):
        with pytest.raises(BusinessError) as exc:
            await conversations.delete_conversation_admin(
                target_id, user(superuser=True)
            )
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.CONVERSATION_NOT_FOUND,
        404,
    )

    target = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.delete_conversation_admin(target.id, user())
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        404,
    )
    target.delete.assert_not_awaited()

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.delete_conversation_admin(target.id, user(dashboard=True))
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        403,
    )
    target.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_single_delete_allows_in_scope_admin():
    current_user = user(dashboard=True)
    target = conversation()
    agent_query = Query()
    agent_query.update = AsyncMock(return_value=1)
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(first=target)
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            AsyncMock(return_value=[target.agent_id]),
        ),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
    ):
        response = await conversations.delete_conversation_admin(
            target.id, current_user
        )

    agent_query.update.assert_awaited_once()
    target.delete.assert_awaited_once()
    assert response["data"]["id"] == str(target.id)


@pytest.mark.anyio
async def test_batch_delete_authorization_and_persistence_boundaries():
    foreign = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=Query(result=[foreign])
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc,
    ):
        await conversations.batch_delete_conversations(
            [foreign.id], user(dashboard=True)
        )
    assert (exc.value.code, exc.value.status_code) == (
        ResponseCode.PERMISSION_DENIED,
        403,
    )

    current_user = user()
    owned = conversation(user_id=current_user.id)
    delete_query = Query(delete=1)
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[Query(result=[owned]), delete_query],
        ),
        patch.object(conversations.Agent, "filter", return_value=Query()),
    ):
        response = await conversations.batch_delete_conversations(
            [owned.id], current_user
        )
    assert response["data"]["deleted_count"] == 1

    target = conversation()
    agent_query = Query()
    agent_query.update = AsyncMock(side_effect=RuntimeError("database unavailable"))
    delete_query = Query(delete=1)
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            side_effect=[Query(result=[target]), delete_query],
        ) as conversation_filter,
        patch.object(conversations.Agent, "filter", return_value=agent_query),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await conversations.batch_delete_conversations(
            [target.id], user(superuser=True)
        )
    assert conversation_filter.call_count == 1
