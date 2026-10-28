from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.tools import (
    _build_accessible_tools,
    _get_accessible_teams,
    list_tools,
    list_tools_legacy,
    test_tool as execute_test_tool,
)
from app.models.tool import CustomToolType, ToolType as DBToolType, ToolVisibility
from app.schemas.response import BusinessError
from app.schemas.tool import ToolExecuteRequest, ToolOut, ToolType


class QueryResult:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    async def first(self):
        return self.value

    async def all(self):
        return self.value

    async def count(self):
        return self.value

    def __await__(self):
        async def result():
            return self.value

        return result().__await__()


def user(*, is_superuser=False):
    return SimpleNamespace(is_superuser=is_superuser, locale="en", username="tester")


def tool_out(**overrides):
    values = {
        "name": "search_tool",
        "display_name": "Search Tool",
        "description": "Searches data",
        "type": ToolType.CUSTOM,
        "category": "search",
        "is_enabled": True,
        "team_id": uuid4(),
        "created_by_name": "alice",
    }
    values.update(overrides)
    return ToolOut(**values)


@pytest.mark.anyio
async def test_get_accessible_teams_superuser_returns_all_teams_ordered():
    query = QueryResult([SimpleNamespace(name="Alpha")])
    with patch("app.api.v1.endpoints.tools.Team.all", return_value=query) as team_all:
        teams = await _get_accessible_teams(user(is_superuser=True))

    assert teams == query.value
    team_all.assert_called_once_with()


@pytest.mark.anyio
async def test_build_accessible_tools_keeps_owned_tool_over_shared_duplicate():
    team = SimpleNamespace(id=uuid4(), name="Team")
    db_tool = SimpleNamespace(
        id=uuid4(),
        type=DBToolType.CUSTOM,
        team_id=team.id,
        team=team,
        created_by=None,
    )
    shared = SimpleNamespace(tool=db_tool, permission="read_only")
    owned_out = tool_out(id=db_tool.id, team_id=team.id)
    shared_out = tool_out(id=db_tool.id, team_id=team.id)
    converted = iter([owned_out, shared_out])

    def filter_tools(**kwargs):
        if kwargs.get("type") == DBToolType.CUSTOM:
            return QueryResult([db_tool])
        return QueryResult([])

    with (
        patch("app.api.v1.endpoints.tools.get_builtin_tools", return_value=[]),
        patch("app.api.v1.endpoints.tools.Tool.filter", side_effect=filter_tools),
        patch(
            "app.api.v1.endpoints.tools.ToolShare.filter",
            side_effect=[QueryResult(0), QueryResult([shared]), QueryResult(0)],
        ),
        patch(
            "app.api.v1.endpoints.tools.db_tool_to_out",
            side_effect=lambda *_args: next(converted),
        ),
    ):
        tools = await _build_accessible_tools(user(), [team])

    assert tools == [owned_out]
    assert tools[0].is_owned is True


@pytest.mark.anyio
async def test_list_tools_rejects_each_nonmatching_filter_branch():
    team_id = uuid4()
    tools = [
        tool_out(name="wrong type", type=ToolType.MCP, team_id=team_id),
        tool_out(name="wrong category", category="math", team_id=team_id),
        tool_out(name="wrong status", is_enabled=False, team_id=team_id),
        tool_out(name="wrong team", team_id=None),
        tool_out(name="wrong creator", created_by_name="bob", team_id=team_id),
        tool_out(name="included", team_id=team_id),
    ]
    with (
        patch(
            "app.api.v1.endpoints.tools._get_accessible_teams",
            new=AsyncMock(return_value=[SimpleNamespace(id=team_id)]),
        ),
        patch(
            "app.api.v1.endpoints.tools._build_accessible_tools",
            new=AsyncMock(return_value=tools),
        ),
    ):
        response = await list_tools(
            page=1,
            page_size=10,
            search=None,
            type=["custom"],
            category=["search"],
            status=["enabled"],
            team_id=[team_id],
            creator=["alice"],
            current_user=user(),
        )

    assert [item.name for item in response["data"].items] == ["included"]


@pytest.mark.anyio
async def test_list_tools_legacy_includes_shared_custom_and_mcp_tools():
    team_id = uuid4()
    shared_custom = SimpleNamespace(
        tool=SimpleNamespace(
            id=uuid4(),
            type=DBToolType.CUSTOM,
            visibility=ToolVisibility.TEAM,
            team_id=uuid4(),
            team=SimpleNamespace(name="Owner"),
            created_by=None,
        ),
        permission="read_only",
    )
    shared_mcp = SimpleNamespace(
        tool=SimpleNamespace(
            id=uuid4(),
            visibility=ToolVisibility.TEAM,
            type=DBToolType.MCP,
            team_id=uuid4(),
            team=SimpleNamespace(name="Owner"),
            created_by=None,
        ),
        permission="read_execute",
    )
    converted = {
        shared_custom.tool.id: tool_out(type=ToolType.CUSTOM),
        shared_mcp.tool.id: tool_out(type=ToolType.MCP),
    }

    def filter_tools(**_kwargs):
        return QueryResult([])

    with (
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.get_builtin_tools", return_value=[]),
        patch("app.api.v1.endpoints.tools.Tool.filter", side_effect=filter_tools),
        patch(
            "app.api.v1.endpoints.tools.ToolShare.filter",
            return_value=QueryResult([shared_custom, shared_mcp]),
        ),
        patch(
            "app.api.v1.endpoints.tools.db_tool_to_out",
            side_effect=lambda value, _creator: converted[value.id],
        ),
    ):
        response = await list_tools_legacy(team_id, True, user())

    assert len(response["data"].custom) == 1
    assert len(response["data"].mcp) == 1


@pytest.mark.anyio
async def test_list_tools_legacy_skips_shared_query_when_disabled():
    with (
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.get_builtin_tools", return_value=[]),
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=QueryResult([])),
        patch("app.api.v1.endpoints.tools.ToolShare.filter") as share_filter,
    ):
        response = await list_tools_legacy(uuid4(), False, user())

    assert response["data"].custom == []
    assert response["data"].mcp == []
    share_filter.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("custom_tool", "expected_error"),
    [
        (
            SimpleNamespace(name="saved_tool", type=DBToolType.MCP, mcp_config={}),
            "no configuration",
        ),
        (
            SimpleNamespace(
                name="saved_tool",
                type=DBToolType.CUSTOM,
                custom_type=CustomToolType.CODE,
                code_config={},
            ),
            "code",
        ),
    ],
)
async def test_test_tool_returns_failures_for_invalid_saved_tools(
    custom_tool, expected_error
):
    request = ToolExecuteRequest(name="saved_tool", arguments={})
    execute = AsyncMock()
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await execute_test_tool(
            request, team_id=uuid4(), current_user=user()
        )

    assert response["data"].success is False
    assert expected_error in response["data"].error.lower()
    execute.assert_not_awaited()


@pytest.mark.anyio
async def test_test_tool_reports_unsupported_custom_type_from_executor():
    custom_tool = SimpleNamespace(
        name="saved_tool",
        team_id=uuid4(),
        type=DBToolType.CUSTOM,
        custom_type=None,
    )
    request = ToolExecuteRequest(name="saved_tool", arguments={})
    execute = AsyncMock(side_effect=ValueError("unsupported custom tool type"))
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await execute_test_tool(
            request, team_id=custom_tool.team_id, current_user=user()
        )

    assert response["data"].success is False
    assert response["data"].error


@pytest.mark.anyio
async def test_test_tool_executes_http_saved_tool():
    custom_tool = SimpleNamespace(
        name="http_tool",
        team_id=uuid4(),
        type=DBToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        http_config={"url": "https://example.test"},
        credentials={"token": "secret"},
    )
    request = ToolExecuteRequest(name="http_tool", arguments={"q": "value"})
    execute = AsyncMock(return_value={"success": True, "result": "ok"})
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await execute_test_tool(
            request, team_id=custom_tool.team_id, current_user=user()
        )

    assert response["data"].result == "ok"
    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom_tool
    assert args_arg == {"q": "value"}
    assert execute.await_args.kwargs["operation"] == "http_tool"


@pytest.mark.anyio
async def test_test_tool_returns_localized_mcp_exception():
    custom_tool = SimpleNamespace(
        name="mcp_server",
        team_id=uuid4(),
        type=DBToolType.MCP,
        mcp_config={"transport": "http", "url": "https://mcp.test"},
    )
    request = ToolExecuteRequest(
        name="mcp_server", arguments={"__tool_name__": "remote_tool", "x": 1}
    )
    execute = AsyncMock(side_effect=RuntimeError("connection failed"))
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.ToolExecutor",
            return_value=SimpleNamespace(execute=execute),
        ),
    ):
        response = await execute_test_tool(
            request, team_id=custom_tool.team_id, current_user=user()
        )

    assert response["data"].success is False
    assert response["data"].error
    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom_tool
    assert args_arg == {"x": 1}
    assert execute.await_args.kwargs["operation"] == "remote_tool"


@pytest.mark.anyio
async def test_test_tool_without_team_raises_not_found():
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        pytest.raises(BusinessError),
    ):
        await execute_test_tool(
            ToolExecuteRequest(name="missing", arguments={}),
            team_id=None,
            current_user=user(),
        )
