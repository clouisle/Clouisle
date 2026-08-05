from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import conversations
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result=None, *, first=None, count=0, values=None):
        self.result = result
        self.first_value = first
        self.count_value = count
        self.values_value = [] if values is None else values

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    def filter(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_args):
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
        return len(self.result or [])


def user(*, user_id=None, superuser=False, permissions=()):
    role = SimpleNamespace(
        permissions=[SimpleNamespace(code=code) for code in permissions]
    )
    return SimpleNamespace(id=user_id or uuid4(), is_superuser=superuser, roles=[role])


def conversation(*, owner_id=None, agent_id=None, title="Conversation"):
    return SimpleNamespace(
        id=uuid4(),
        user_id=owner_id or uuid4(),
        agent_id=agent_id or uuid4(),
        message_count=3,
        title=title,
        delete=AsyncMock(),
    )


@pytest.mark.anyio
async def test_team_access_and_admin_access_validation(monkeypatch):
    actor = user()
    team = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        conversations.Team, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as error:
        await conversations.check_team_access(team.id, actor)
    assert error.value.status_code == 404

    monkeypatch.setattr(
        conversations.Team, "filter", lambda **_kwargs: Query(first=team)
    )
    monkeypatch.setattr(
        conversations.TeamMember, "filter", lambda **_kwargs: Query(first=None)
    )
    with pytest.raises(BusinessError) as error:
        await conversations.check_team_access(team.id, actor)
    assert error.value.status_code == 403

    assert not await conversations.has_conversation_team_admin_access(actor, None)
    assert await conversations.has_conversation_team_admin_access(
        user(permissions=("*",)), None
    )


@pytest.mark.anyio
async def test_agent_ids_cover_team_superuser_and_membership_rows(monkeypatch):
    actor = user()
    team_id = uuid4()
    first_id, second_id = uuid4(), uuid4()
    check_access = AsyncMock()
    monkeypatch.setattr(conversations, "check_team_access", check_access)
    monkeypatch.setattr(
        conversations.Agent,
        "filter",
        lambda **kwargs: Query(
            values=[(first_id,)] if "team_id" in kwargs else [second_id]
        ),
    )

    assert await conversations.get_user_team_agent_ids(actor, team_id) == [first_id]
    check_access.assert_awaited_once_with(team_id, actor)

    monkeypatch.setattr(
        conversations.Agent, "all", lambda: Query(values=[(first_id,), second_id])
    )
    assert await conversations.get_user_team_agent_ids(user(superuser=True)) == [
        first_id,
        second_id,
    ]

    monkeypatch.setattr(
        conversations.TeamMember,
        "filter",
        lambda **_kwargs: Query(values=[(team_id,)]),
    )
    assert await conversations.get_user_team_agent_ids(actor) == [second_id]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "expected_status"),
    [
        (conversations.get_conversation_detail, 404),
        (conversations.delete_conversation_admin, 404),
    ],
)
async def test_single_conversation_not_found(monkeypatch, endpoint, expected_status):
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=None)
    )
    args = [uuid4()]
    if endpoint is conversations.delete_conversation_admin:
        args.append(SimpleNamespace())
    args.append(user())

    with pytest.raises(BusinessError) as error:
        await endpoint(*args)
    assert error.value.status_code == expected_status


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("permissions", "owner", "expected_status"),
    [
        ((), False, 404),
        (("admin:dashboard:access",), True, 403),
    ],
)
async def test_detail_rejects_owner_and_team_scope_violations(
    monkeypatch, permissions, owner, expected_status
):
    actor = user(permissions=permissions)
    item = conversation(owner_id=actor.id if owner else uuid4())
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )

    with pytest.raises(BusinessError) as error:
        await conversations.get_conversation_detail(item.id, actor)
    assert error.value.status_code == expected_status


@pytest.mark.anyio
async def test_detail_builds_edit_version_counts(monkeypatch):
    actor = user(superuser=True)
    item = conversation(owner_id=actor.id)
    item.agent = SimpleNamespace(name="Agent", icon="icon")
    item.user = SimpleNamespace(username="owner")
    root_id, edited_id, standalone_id = uuid4(), uuid4(), uuid4()
    messages = [
        SimpleNamespace(
            id=root_id, parent_id=None, round_id=None, is_round_canonical=True
        ),
        SimpleNamespace(
            id=edited_id,
            parent_id=root_id,
            round_id=uuid4(),
            is_round_canonical=False,
        ),
        SimpleNamespace(
            id=standalone_id,
            parent_id=None,
            round_id=uuid4(),
            is_round_canonical=True,
        ),
    ]
    outputs = [{"id": str(root_id)}, {"id": str(standalone_id)}]

    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(
        conversations,
        "get_visible_conversation_messages",
        AsyncMock(return_value=messages),
    )
    monkeypatch.setattr(
        conversations,
        "build_message_round_payloads",
        AsyncMock(return_value=outputs),
    )
    monkeypatch.setattr(
        conversations.Message,
        "filter",
        lambda **_kwargs: Query(values=[{"parent_id": root_id, "count": 2}]),
    )
    validated = SimpleNamespace(model_dump=lambda: {"id": str(item.id)})
    monkeypatch.setattr(
        conversations.ConversationOut,
        "model_validate",
        lambda _item: validated,
    )

    result = await conversations.get_conversation_detail(item.id, actor)

    assert result["data"]["messages"][0]["version_count"] == 3
    assert result["data"]["messages"][1]["version_count"] == 1
    assert result["data"]["agent_name"] == "Agent"
    assert result["data"]["user_name"] == "owner"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("permissions", "same_owner", "expected_status"),
    [
        ((), False, 404),
        (("admin:dashboard:access",), True, 403),
    ],
)
async def test_delete_rejects_owner_and_team_scope_violations(
    monkeypatch, permissions, same_owner, expected_status
):
    actor = user(permissions=permissions)
    item = conversation(owner_id=actor.id if same_owner else uuid4())
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )

    with pytest.raises(BusinessError) as error:
        await conversations.delete_conversation_admin(item.id, SimpleNamespace(), actor)
    assert error.value.status_code == expected_status
    item.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_updates_stats_deletes_and_audits(monkeypatch):
    actor = user(superuser=True)
    item = conversation(owner_id=actor.id, title=None)
    agent_query = Query()
    audit = AsyncMock()
    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(first=item)
    )
    monkeypatch.setattr(conversations.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(conversations.AuditLogService, "log", audit)

    result = await conversations.delete_conversation_admin(
        item.id, SimpleNamespace(), actor
    )

    assert result["data"] == {"id": str(item.id)}
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == str(item.id)


@pytest.mark.anyio
async def test_batch_delete_validation_authorization_and_success(monkeypatch):
    actor = user()
    request = SimpleNamespace()
    first, second = conversation(owner_id=actor.id), conversation(owner_id=uuid4())

    monkeypatch.setattr(
        conversations.Conversation, "filter", lambda **_kwargs: Query(result=[])
    )
    with pytest.raises(BusinessError) as error:
        await conversations.batch_delete_conversations(
            ids=[first.id], request=request, current_user=actor
        )
    assert error.value.status_code == 404

    monkeypatch.setattr(
        conversations.Conversation,
        "filter",
        lambda **_kwargs: Query(result=[first, second]),
    )
    with pytest.raises(BusinessError) as error:
        await conversations.batch_delete_conversations(
            ids=[first.id, second.id], request=request, current_user=actor
        )
    assert error.value.status_code == 404

    admin = user(permissions=("*",))
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )
    with pytest.raises(BusinessError) as error:
        await conversations.batch_delete_conversations(
            ids=[first.id], request=request, current_user=admin
        )
    assert error.value.status_code == 403

    superuser = user(superuser=True)
    agent_query = Query()
    audit = AsyncMock()
    monkeypatch.setattr(conversations.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(conversations.AuditLogService, "log", audit)
    result = await conversations.batch_delete_conversations(
        ids=[first.id, second.id], request=request, current_user=superuser
    )

    assert result["data"] == {
        "deleted_count": 2,
        "ids": [str(first.id), str(second.id)],
    }
    assert audit.await_args.kwargs["metadata"]["deleted_count"] == 2
