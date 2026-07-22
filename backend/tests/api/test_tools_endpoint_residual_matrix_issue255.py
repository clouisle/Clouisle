from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import ToolType as DBToolType
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import (
    McpConfigSchema,
    McpToolsListRequest,
    ToolShareInput,
    ToolSharePermission,
    ToolUpdateInput,
)


class Query:
    def __init__(self, result=None, *, exists=False):
        self.result = result
        self.exists_result = exists

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    async def first(self):
        return self.result

    async def all(self):
        return self.result

    async def exists(self):
        return self.exists_result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def assert_error(exc_info, code, status_code):
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.anyio
async def test_write_access_respects_superuser_creator_and_admin_boundaries(
    monkeypatch,
):
    team_id, creator_id = uuid4(), uuid4()
    tool = SimpleNamespace(team_id=team_id, created_by_id=creator_id)
    check_access = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", check_access)

    await tools.check_tool_write_access(tool, SimpleNamespace(is_superuser=True))
    check_access.assert_not_awaited()

    await tools.check_tool_write_access(
        tool, SimpleNamespace(is_superuser=False, id=creator_id)
    )
    check_access.assert_awaited_once_with(team_id, ANY)

    check_access.reset_mock()
    user = SimpleNamespace(is_superuser=False, id=uuid4())
    await tools.check_tool_write_access(tool, user)
    assert check_access.await_args_list == [
        ((team_id, user), {}),
        ((team_id, user), {"require_admin": True}),
    ]


@pytest.mark.anyio
async def test_list_tools_rejects_any_inaccessible_requested_team(monkeypatch):
    allowed_id, denied_id = uuid4(), uuid4()
    user = SimpleNamespace()
    build = AsyncMock()
    monkeypatch.setattr(
        tools,
        "_get_accessible_teams",
        AsyncMock(return_value=[SimpleNamespace(id=allowed_id)]),
    )
    monkeypatch.setattr(tools, "_build_accessible_tools", build)

    with pytest.raises(BusinessError) as denied:
        await tools.list_tools(team_id=[allowed_id, denied_id], current_user=user)

    assert_error(denied, ResponseCode.NOT_TEAM_MEMBER, 403)
    build.assert_not_awaited()


@pytest.mark.anyio
async def test_get_mcp_tools_maps_client_exception_to_business_error(monkeypatch):
    monkeypatch.setattr(
        tools, "list_mcp_tools", AsyncMock(side_effect=RuntimeError("offline"))
    )
    request = McpToolsListRequest(
        mcp_config=McpConfigSchema(transport="http", url="https://mcp.example.test")
    )

    with pytest.raises(BusinessError) as failed:
        await tools.get_mcp_tools(request, current_user=object())

    assert_error(failed, ResponseCode.INTERNAL_ERROR, 500)


@pytest.mark.anyio
async def test_update_tool_missing_duplicate_and_full_lifecycle(monkeypatch):
    tool_id, team_id = uuid4(), uuid4()
    tool = SimpleNamespace(
        id=tool_id,
        team_id=team_id,
        name="old",
        created_by=SimpleNamespace(username="ada"),
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        tools.Tool,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(tool),
                Query(object()),
                Query(tool),
                Query(None),
            ]
        ),
    )
    monkeypatch.setattr(tools, "check_tool_write_access", AsyncMock())
    scoped = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(tools.deps, "check_scoped_permission", scoped)
    monkeypatch.setattr(tools.AuditLogService, "log", audit)
    monkeypatch.setattr(tools, "db_tool_to_detail", MagicMock(return_value="detail"))
    user, request = SimpleNamespace(), object()

    with pytest.raises(BusinessError) as missing:
        await tools.update_tool(tool_id, ToolUpdateInput(), request, user)
    assert_error(missing, ResponseCode.NOT_FOUND, 404)

    with pytest.raises(BusinessError) as duplicate:
        await tools.update_tool(tool_id, ToolUpdateInput(name="taken"), request, user)
    assert_error(duplicate, ResponseCode.ALREADY_EXISTS, 400)

    update = ToolUpdateInput(
        name="new_name",
        display_name="New",
        description="updated",
        icon="icon",
        category="api",
        custom_type="http",
        parameters=[],
        http_config={"method": "GET", "url": "https://example.test"},
        credentials={"token": "secret"},
        is_enabled=False,
    )
    response = await tools.update_tool(tool_id, update, request, user)

    assert response["data"] == "detail"
    assert (tool.name, tool.display_name, tool.is_enabled) == ("new_name", "New", False)
    assert tool.http_config["url"] == "https://example.test"
    tool.save.assert_awaited_once()
    scoped.assert_awaited_with(user, "tool:update", "team", team_id)
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_duplicate_tool_advances_name_and_creates_disabled_copy(monkeypatch):
    tool_id, team_id = uuid4(), uuid4()
    source = SimpleNamespace(
        id=tool_id,
        team_id=team_id,
        name="runner",
        display_name="Runner",
        description="desc",
        icon=None,
        category="code",
        type=DBToolType.CUSTOM,
        custom_type=None,
        parameters=[],
        http_config={},
        code_config={},
        mcp_config={},
        credentials={},
    )
    duplicate = SimpleNamespace(id=uuid4(), name="runner_copy_2")
    filters = [
        Query(source),
        Query(exists=True),
        Query(exists=True),
        Query(exists=False),
    ]
    monkeypatch.setattr(tools.Tool, "filter", MagicMock(side_effect=filters))
    create = AsyncMock(return_value=duplicate)
    monkeypatch.setattr(tools.Tool, "create", create)
    access = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.AuditLogService, "log", audit)
    monkeypatch.setattr(tools, "db_tool_to_detail", MagicMock(return_value="copy"))
    user = SimpleNamespace(username="ada")

    response = await tools.duplicate_tool(tool_id, object(), user)

    assert response["data"] == "copy"
    access.assert_awaited_once_with(team_id, user, require_admin=True)
    assert create.await_args.kwargs["name"] == "runner_copy_2"
    assert create.await_args.kwargs["is_enabled"] is False
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_share_tool_validates_target_ownership_and_duplicate(monkeypatch):
    tool_id, owner_id, target_id = uuid4(), uuid4(), uuid4()
    tool = SimpleNamespace(id=tool_id, team_id=owner_id, name="runner")
    user = SimpleNamespace(id=uuid4())
    access = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(
        tools.Tool,
        "filter",
        MagicMock(side_effect=[Query(None), Query(tool), Query(tool), Query(tool)]),
    )
    monkeypatch.setattr(
        tools.Team,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(id=owner_id)),
                Query(object()),
            ]
        ),
    )
    monkeypatch.setattr(
        tools.ToolShare, "filter", MagicMock(return_value=Query(object()))
    )

    with pytest.raises(BusinessError) as missing_tool:
        await tools.share_tool(
            tool_id, ToolShareInput(team_id=target_id), object(), user
        )
    assert_error(missing_tool, ResponseCode.NOT_FOUND, 404)

    with pytest.raises(BusinessError) as missing_team:
        await tools.share_tool(
            tool_id, ToolShareInput(team_id=target_id), object(), user
        )
    assert_error(missing_team, ResponseCode.TEAM_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as own_team:
        await tools.share_tool(
            tool_id, ToolShareInput(team_id=owner_id), object(), user
        )
    assert_error(own_team, ResponseCode.BAD_REQUEST, 400)

    with pytest.raises(BusinessError) as duplicate:
        await tools.share_tool(
            tool_id,
            ToolShareInput(
                team_id=target_id, permission=ToolSharePermission.READ_EXECUTE
            ),
            object(),
            user,
        )
    assert_error(duplicate, ResponseCode.DUPLICATE_NAME, 400)
    assert access.await_count == 3


@pytest.mark.anyio
async def test_unshare_tool_missing_share_and_success_lifecycle(monkeypatch):
    tool_id, team_id, owner_id = uuid4(), uuid4(), uuid4()
    tool = SimpleNamespace(id=tool_id, team_id=owner_id, name="runner")
    share = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(
        tools.Tool, "filter", MagicMock(side_effect=[Query(tool), Query(tool)])
    )
    monkeypatch.setattr(
        tools.ToolShare, "filter", MagicMock(side_effect=[Query(None), Query(share)])
    )
    access = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.AuditLogService, "log", audit)
    user, request = object(), object()

    with pytest.raises(BusinessError) as missing:
        await tools.unshare_tool(tool_id, team_id, request, user)
    assert_error(missing, ResponseCode.NOT_FOUND, 404)

    response = await tools.unshare_tool(tool_id, team_id, request, user)

    assert response["data"] is None
    share.delete.assert_awaited_once()
    assert access.await_args_list == [
        ((owner_id, user), {"require_admin": True}),
        ((owner_id, user), {"require_admin": True}),
    ]
    audit.assert_awaited_once()
