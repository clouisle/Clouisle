from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import conversations
from app.schemas.response import BusinessError


class QueryMock:
    def __init__(self, *, rows=None, count=0, first=None, deleted=0):
        self.rows = rows or []
        self.count = AsyncMock(return_value=count)
        self.first = AsyncMock(return_value=first)
        self.limit = AsyncMock(return_value=self.rows)
        self.values = AsyncMock(return_value=self.rows)
        self.values_list = AsyncMock(return_value=self.rows)
        self.update = AsyncMock()
        self.delete = AsyncMock(return_value=deleted)

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()

    def filter(self, *args, **kwargs):
        return self

    def select_related(self, *args, **kwargs):
        return self

    def prefetch_related(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, *args, **kwargs):
        return self

    def annotate(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self


class Permission:
    def __init__(self, code):
        self.code = code


def user(*, superuser=False, permissions=()):
    roles = [SimpleNamespace(permissions=[Permission(code) for code in permissions])]
    return SimpleNamespace(id=uuid4(), is_superuser=superuser, roles=roles)


def conversation(*, owner_id=None, agent_id=None, title="Conversation"):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        agent_id=agent_id or uuid4(),
        agent=SimpleNamespace(name="Agent", icon="bot"),
        user_id=owner_id or uuid4(),
        user=SimpleNamespace(username="owner"),
        title=title,
        variables={},
        message_count=3,
        token_usage=7,
        created_at=timestamp,
        updated_at=timestamp,
        delete=AsyncMock(),
    )


@pytest.mark.anyio
async def test_access_helpers_cover_team_and_agent_scopes():
    member = user()
    team_id = uuid4()
    team = SimpleNamespace(id=team_id)
    membership = SimpleNamespace(role="admin")
    team_query = QueryMock(first=team)
    membership_query = QueryMock(first=membership)

    with (
        patch.object(conversations.Team, "filter", return_value=team_query),
        patch.object(conversations.TeamMember, "filter", return_value=membership_query),
    ):
        assert await conversations.check_team_access(team_id, member) is team
        assert await conversations.has_conversation_team_admin_access(member, team_id)

    with (
        patch.object(conversations.Team, "filter", return_value=QueryMock(first=None)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.check_team_access(team_id, member)
    assert exc_info.value.status_code == 404

    member.roles = [SimpleNamespace(permissions=[Permission("*")])]
    assert await conversations.has_conversation_team_admin_access(member, None)

    member.roles = []
    membership_ids = QueryMock(rows=[(uuid4(),), uuid4()])
    agent_ids = QueryMock(rows=[(uuid4(),), uuid4()])
    with (
        patch.object(conversations.TeamMember, "filter", return_value=membership_ids),
        patch.object(conversations.Agent, "filter", return_value=agent_ids),
    ):
        result = await conversations.get_user_team_agent_ids(member)
    assert result == agent_ids.rows


@pytest.mark.anyio
async def test_list_conversations_covers_empty_denied_filter_and_member_rows():
    member = user()
    requested_agent = uuid4()

    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            new=AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", new=AsyncMock(return_value=[])
        ),
    ):
        result = await conversations.list_all_conversations(
            agent_id=None,
            user_id=None,
            search=None,
            untitled_only=False,
            page=2,
            page_size=10,
            team_id=None,
            current_user=member,
        )
    assert result["data"] == {"items": [], "total": 0, "page": 2, "page_size": 10}

    accessible_id = uuid4()
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            new=AsyncMock(return_value=False),
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            new=AsyncMock(return_value=[accessible_id]),
        ),
        patch.object(conversations.Conversation, "filter", return_value=QueryMock()),
    ):
        result = await conversations.list_all_conversations(
            agent_id=requested_agent,
            user_id=None,
            search=None,
            untitled_only=False,
            page=1,
            page_size=20,
            team_id=None,
            current_user=member,
        )
    assert result["data"]["total"] == 0

    item = conversation(owner_id=member.id, agent_id=accessible_id)
    query = QueryMock(rows=[item], count=1)
    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            new=AsyncMock(return_value=False),
        ),
        patch.object(
            conversations,
            "get_user_team_agent_ids",
            new=AsyncMock(return_value=[accessible_id]),
        ),
        patch.object(conversations.Conversation, "filter", return_value=query),
    ):
        result = await conversations.list_all_conversations(
            agent_id=None,
            user_id=uuid4(),
            search="Conv",
            untitled_only=False,
            page=1,
            page_size=20,
            team_id=None,
            current_user=member,
        )
    assert result["data"]["items"][0]["agent_name"] == "Agent"
    assert result["data"]["items"][0]["user_name"] == "owner"


@pytest.mark.anyio
async def test_detail_errors_cover_missing_member_and_admin_team_access():
    member = user()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=QueryMock(first=None)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.get_conversation_detail(uuid4(), member)
    assert exc_info.value.status_code == 404

    other_conversation = conversation()
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            return_value=QueryMock(first=other_conversation),
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.get_conversation_detail(other_conversation.id, member)
    assert exc_info.value.status_code == 404

    admin = user(permissions=("admin:dashboard:access",))
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            return_value=QueryMock(first=other_conversation),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", new=AsyncMock(return_value=[])
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.get_conversation_detail(other_conversation.id, admin)
    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_detail_adds_branch_version_counts_to_canonical_payloads():
    admin = user(superuser=True)
    item = conversation(owner_id=admin.id)
    root_id = uuid4()
    child_id = uuid4()
    round_id = uuid4()
    visible = [
        SimpleNamespace(
            id=root_id, parent_id=None, round_id=None, is_round_canonical=False
        ),
        SimpleNamespace(
            id=child_id, parent_id=root_id, round_id=round_id, is_round_canonical=True
        ),
        SimpleNamespace(
            id=uuid4(), parent_id=None, round_id=round_id, is_round_canonical=False
        ),
    ]
    conversation_query = QueryMock(first=item)
    child_counts_query = QueryMock(rows=[{"parent_id": root_id, "count": 2}])
    payloads = [{"id": str(root_id)}, {"id": str(child_id)}]

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=conversation_query
        ),
        patch.object(conversations.Message, "filter", return_value=child_counts_query),
        patch.object(
            conversations,
            "get_visible_conversation_messages",
            new=AsyncMock(return_value=visible),
        ),
        patch.object(
            conversations,
            "build_message_round_payloads",
            new=AsyncMock(return_value=payloads),
        ),
    ):
        result = await conversations.get_conversation_detail(item.id, admin)

    assert [message["version_count"] for message in result["data"]["messages"]] == [
        3,
        3,
    ]
    assert result["data"]["agent_name"] == "Agent"
    assert result["data"]["user_name"] == "owner"


@pytest.mark.anyio
async def test_delete_rejects_inaccessible_conversation():
    member = user()
    item = conversation()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=QueryMock(first=item)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.delete_conversation_admin(item.id, MagicMock(), member)
    assert exc_info.value.status_code == 404
    item.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_delete_updates_agent_stats_deletes_and_audits():
    admin = user(superuser=True)
    item = conversation(owner_id=admin.id, title=None)
    conversation_query = QueryMock(first=item)
    agent_query = QueryMock()
    audit = AsyncMock()
    request = MagicMock()

    with (
        patch.object(
            conversations.Conversation, "filter", return_value=conversation_query
        ),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
        patch.object(conversations.AuditLogService, "log", new=audit),
    ):
        result = await conversations.delete_conversation_admin(item.id, request, admin)

    agent_query.update.assert_awaited_once()
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert result["data"] == {"id": str(item.id)}


@pytest.mark.anyio
async def test_batch_delete_covers_errors_access_and_successful_stat_updates():
    member = user()
    with (
        patch.object(
            conversations.Conversation, "filter", return_value=QueryMock(rows=[])
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.batch_delete_conversations(
            ids=[uuid4()], request=MagicMock(), current_user=member
        )
    assert exc_info.value.status_code == 404

    inaccessible = conversation()
    with (
        patch.object(
            conversations.Conversation,
            "filter",
            return_value=QueryMock(rows=[inaccessible]),
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await conversations.batch_delete_conversations(
            ids=[inaccessible.id], request=MagicMock(), current_user=member
        )
    assert exc_info.value.status_code == 404

    admin = user(superuser=True)
    items = [conversation(owner_id=admin.id), conversation(owner_id=admin.id)]
    delete_query = QueryMock(deleted=2)
    agent_query = QueryMock()
    conversation_filter = MagicMock(side_effect=[QueryMock(rows=items), delete_query])
    audit = AsyncMock()
    with (
        patch.object(conversations.Conversation, "filter", conversation_filter),
        patch.object(conversations.Agent, "filter", return_value=agent_query),
        patch.object(conversations.AuditLogService, "log", new=audit),
    ):
        result = await conversations.batch_delete_conversations(
            ids=[item.id for item in items], request=MagicMock(), current_user=admin
        )

    assert agent_query.update.await_count == 2
    delete_query.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert result["data"]["deleted_count"] == 2
