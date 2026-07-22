from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import teams, tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolType as DBToolType
from app.schemas.team import TeamMemberAdd, TeamMemberRole
from app.schemas.tool import (
    CodeExecuteRequest,
    McpConfigSchema,
    McpToolInfoOut,
    McpToolsListRequest,
    ToolExecuteRequest,
)


class _AwaitableQuery:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def exclude(self, **_kwargs):
        return self

    async def all(self):
        return self.value

    async def count(self):
        return self.value

    async def exists(self):
        return bool(self.value)

    async def first(self):
        return self.value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class _ToolModel:
    tool = None

    @classmethod
    def filter(cls, **_kwargs):
        return _AwaitableQuery(cls.tool)


class _TeamModel:
    team = None

    @classmethod
    def filter(cls, **_kwargs):
        return _AwaitableQuery(cls.team)


class _UserModel:
    users = {}

    @classmethod
    def filter(cls, **kwargs):
        return _AwaitableQuery(cls.users.get(kwargs["id"]))


class _TeamMemberModel:
    memberships = {}
    created = None

    @classmethod
    def filter(cls, **kwargs):
        if kwargs.get("role") == TeamMemberRole.OWNER:
            value = next(
                (
                    membership
                    for membership in cls.memberships.values()
                    if membership.role == TeamMemberRole.OWNER
                ),
                None,
            )
            return _AwaitableQuery(value)
        user = kwargs.get("user")
        return _AwaitableQuery(cls.memberships.get(getattr(user, "id", None)))

    @classmethod
    async def create(cls, **kwargs):
        cls.created = SimpleNamespace(
            id=uuid4(),
            joined_at=datetime(2026, 1, 1, tzinfo=UTC),
            **kwargs,
        )
        cls.memberships[kwargs["user"].id] = cls.created
        return cls.created


def _user(**overrides):
    values = {
        "id": uuid4(),
        "username": "user",
        "email": "user@example.test",
        "avatar_url": None,
        "locale": "en",
        "is_superuser": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _team(owner=None):
    return SimpleNamespace(
        id=uuid4(),
        name="Team",
        description=None,
        avatar_url=None,
        is_default=False,
        owner=owner,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        save=AsyncMock(),
    )


def _membership(user, role=TeamMemberRole.MEMBER):
    return SimpleNamespace(
        id=uuid4(),
        user=user,
        role=role,
        joined_at=datetime(2026, 1, 1, tzinfo=UTC),
        save=AsyncMock(),
        delete=AsyncMock(),
    )


@pytest.mark.anyio
async def test_mcp_list_tools_success_and_failure_are_mocked():
    request = McpToolsListRequest(mcp_config=McpConfigSchema(url="https://mcp.test"))
    tool_info = McpToolInfoOut(name="lookup", description="Lookup", parameters={})

    with patch(
        "app.api.v1.endpoints.tools.list_mcp_tools",
        new=AsyncMock(return_value=[tool_info]),
    ):
        response = await tools.get_mcp_tools(request, current_user=_user())

    assert response["data"].tools[0].name == "lookup"

    with (
        patch(
            "app.api.v1.endpoints.tools.list_mcp_tools",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        pytest.raises(tools.BusinessError) as error,
    ):
        await tools.get_mcp_tools(request, current_user=_user())

    assert error.value.msg_key == "mcp_connection_failed"


@pytest.mark.anyio
async def test_test_tool_mcp_branches_do_not_hit_real_mcp():
    mcp_tool = SimpleNamespace(
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={"transport": "http", "url": "https://mcp.test"},
    )
    _ToolModel.tool = mcp_tool
    result = SimpleNamespace(success=True, result={"ok": True}, error=None)
    request = ToolExecuteRequest(
        name="stored_mcp", arguments={"__tool_name__": "remote_lookup", "q": "x"}
    )

    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool", _ToolModel),
        patch(
            "app.api.v1.endpoints.tools.execute_mcp_tool",
            new=AsyncMock(return_value=result),
        ) as execute,
    ):
        response = await tools.test_tool(request, team_id=uuid4(), current_user=_user())

    execute.assert_awaited_once_with(
        mcp_config=mcp_tool.mcp_config,
        tool_name="remote_lookup",
        arguments={"q": "x"},
        timeout=60.0,
    )
    assert response["data"].success is True
    assert request.arguments == {"q": "x"}

    mcp_tool.mcp_config = {}
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool", _ToolModel),
    ):
        missing_config = await tools.test_tool(
            ToolExecuteRequest(name="stored_mcp", arguments={}),
            team_id=uuid4(),
            current_user=_user(),
        )

    assert missing_config["data"].success is False
    assert "stored_mcp" in missing_config["data"].error

    mcp_tool.mcp_config = {"transport": "http"}
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool", _ToolModel),
        patch(
            "app.api.v1.endpoints.tools.execute_mcp_tool",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "app.api.v1.endpoints.tools.resolve_user_visible_error",
            return_value="safe error",
        ),
    ):
        failed = await tools.test_tool(
            ToolExecuteRequest(name="stored_mcp", arguments={}),
            team_id=uuid4(),
            current_user=_user(),
        )

    assert failed["data"].success is False
    assert failed["data"].error == "safe error"


@pytest.mark.anyio
async def test_code_execution_validation_and_saved_code_missing_code():
    unsupported = await tools.execute_code_directly(
        CodeExecuteRequest(language="ruby", code="puts 1"), current_user=_user()
    )
    assert unsupported["data"].success is False
    assert "ruby" in unsupported["data"].error

    _ToolModel.tool = SimpleNamespace(
        type=DBToolType.CUSTOM,
        custom_type=DBCustomToolType.CODE,
        code_config={},
    )
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool", _ToolModel),
    ):
        response = await tools.test_tool(
            ToolExecuteRequest(name="empty_code", arguments={}),
            team_id=uuid4(),
            current_user=_user(),
        )

    assert response["data"].success is False
    assert response["data"].error == "No code defined for this tool"


@pytest.mark.anyio
async def test_team_member_add_remove_and_leave_branches_mock_notifications():
    owner = _user(username="owner")
    admin = _user(username="admin")
    member = _user(username="member")
    team = _team(owner=owner)
    admin_membership = _membership(admin, TeamMemberRole.ADMIN)
    member_membership = _membership(member, TeamMemberRole.MEMBER)
    _TeamModel.team = team
    _UserModel.users = {member.id: member}
    _TeamMemberModel.memberships = {admin.id: admin_membership}
    _TeamMemberModel.created = None

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch(
            "app.api.v1.endpoints.teams.deps.check_scoped_permission", new=AsyncMock()
        ),
        patch("app.api.v1.endpoints.teams.AuditLogService.log", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_user",
            new=AsyncMock(),
        ) as notify_user,
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_team",
            new=AsyncMock(),
        ) as notify_team,
        patch(
            "app.api.v1.endpoints.teams.get_default_language",
            new=AsyncMock(return_value="en"),
        ),
        patch(
            "app.api.v1.endpoints.teams.sync_user_role_from_teams", new=AsyncMock()
        ) as sync_roles,
    ):
        added = await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=member.id, role=TeamMemberRole.MEMBER),
            current_user=admin,
        )

    assert added["data"]["user_id"] == member.id
    assert notify_user.await_count == 1
    assert notify_team.await_count == 1
    sync_roles.assert_awaited_once_with(member)

    _TeamMemberModel.memberships = {
        admin.id: admin_membership,
        member.id: member_membership,
    }
    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch(
            "app.api.v1.endpoints.teams.deps.check_scoped_permission", new=AsyncMock()
        ),
        patch("app.api.v1.endpoints.teams.AuditLogService.log", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_user",
            new=AsyncMock(),
        ),
        patch(
            "app.api.v1.endpoints.teams.AutoNotificationService.send_to_team",
            new=AsyncMock(),
        ),
        patch(
            "app.api.v1.endpoints.teams.get_default_language",
            new=AsyncMock(return_value="en"),
        ),
        patch(
            "app.api.v1.endpoints.teams.sync_user_role_from_teams", new=AsyncMock()
        ) as sync_removed,
    ):
        removed = await teams.remove_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            user_id=member.id,
            current_user=admin,
        )

    assert removed["data"] == {"user_id": str(member.id)}
    member_membership.delete.assert_awaited_once()
    sync_removed.assert_awaited_once_with(member)

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch(
            "app.api.v1.endpoints.teams.deps.check_scoped_permission", new=AsyncMock()
        ),
        patch(
            "app.api.v1.endpoints.teams.sync_user_role_from_teams", new=AsyncMock()
        ) as sync_left,
    ):
        left = await teams.leave_team(team_id=team.id, current_user=member)

    assert left["data"] == {"team_id": str(team.id)}
    assert member_membership.delete.await_count == 2
    sync_left.assert_awaited_once_with(member)


@pytest.mark.anyio
async def test_team_error_branches_for_missing_user_and_owner_guard():
    owner = _user(username="owner")
    team = _team(owner=owner)
    _TeamModel.team = team
    _UserModel.users = {}
    _TeamMemberModel.memberships = {owner.id: _membership(owner, TeamMemberRole.OWNER)}

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.User", _UserModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch(
            "app.api.v1.endpoints.teams.deps.check_scoped_permission", new=AsyncMock()
        ),
        pytest.raises(teams.BusinessError) as missing_user,
    ):
        await teams.add_team_member(
            request=SimpleNamespace(),
            team_id=team.id,
            member_in=TeamMemberAdd(user_id=uuid4(), role=TeamMemberRole.MEMBER),
            current_user=owner,
        )
    assert missing_user.value.msg_key == "user_not_found"

    with (
        patch("app.api.v1.endpoints.teams.Team", _TeamModel),
        patch("app.api.v1.endpoints.teams.TeamMember", _TeamMemberModel),
        patch(
            "app.api.v1.endpoints.teams.deps.check_scoped_permission", new=AsyncMock()
        ),
        pytest.raises(teams.BusinessError) as owner_leave,
    ):
        await teams.leave_team(team_id=team.id, current_user=owner)
    assert owner_leave.value.msg_key == "owner_cannot_leave"
