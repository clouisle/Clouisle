from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.tools import (
    _build_accessible_tools,
    _get_accessible_teams,
    create_tool_config,
    delete_tool_config,
    list_tool_configs,
    list_tools,
    list_tools_legacy,
    test_tool as execute_test_tool,
    update_tool_config,
)
from app.models.tool import CustomToolType, ToolType as DBToolType
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


class DummyRequest:
    pass


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
            team_id=uuid4(),
            team=SimpleNamespace(name="Owner"),
            created_by=None,
        ),
        permission="read_only",
    )
    shared_mcp = SimpleNamespace(
        tool=SimpleNamespace(
            id=uuid4(),
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
async def test_test_tool_uses_environment_credentials_for_builtin_tool():
    builtin = object()
    request = ToolExecuteRequest(name="web_search", arguments={"query": "docs"})
    with (
        patch(
            "app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=builtin
        ),
        patch(
            "app.models.tool_config.ToolConfig.filter", return_value=QueryResult(None)
        ),
        patch("app.core.config.settings.TAVILY_API_KEY", "env-key", create=True),
        patch(
            "app.api.v1.endpoints.tools.tool_registry.execute",
            new=AsyncMock(return_value={"answer": "ok"}),
        ) as execute,
    ):
        response = await execute_test_tool(
            request, team_id=uuid4(), current_user=user()
        )

    assert response["data"].success is True
    execute.assert_awaited_once_with(
        "web_search", {"query": "docs"}, credentials={"TAVILY_API_KEY": "env-key"}
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("custom_tool", "expected_error"),
    [
        (SimpleNamespace(type=DBToolType.MCP, mcp_config={}), "no configuration"),
        (
            SimpleNamespace(
                type=DBToolType.CUSTOM,
                custom_type=CustomToolType.CODE,
                code_config={},
            ),
            "code",
        ),
        (
            SimpleNamespace(
                type=DBToolType.CUSTOM,
                custom_type=None,
            ),
            "unsupported",
        ),
    ],
)
async def test_test_tool_returns_failures_for_invalid_saved_tools(
    custom_tool, expected_error
):
    request = ToolExecuteRequest(name="saved_tool", arguments={})
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
    ):
        response = await execute_test_tool(
            request, team_id=uuid4(), current_user=user()
        )

    assert response["data"].success is False
    assert expected_error in response["data"].error.lower()


@pytest.mark.anyio
async def test_test_tool_executes_http_saved_tool():
    custom_tool = SimpleNamespace(
        type=DBToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        http_config={"url": "https://example.test"},
        credentials={"token": "secret"},
    )
    request = ToolExecuteRequest(name="http_tool", arguments={"q": "value"})
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.execute_http_tool",
            new=AsyncMock(return_value={"success": True, "result": "ok"}),
        ) as execute_http,
    ):
        response = await execute_test_tool(
            request, team_id=uuid4(), current_user=user()
        )

    assert response["data"].result == "ok"
    execute_http.assert_awaited_once_with(
        custom_tool.http_config, {"q": "value"}, custom_tool.credentials
    )


@pytest.mark.anyio
async def test_test_tool_returns_localized_mcp_exception():
    custom_tool = SimpleNamespace(
        type=DBToolType.MCP,
        mcp_config={"transport": "http", "url": "https://mcp.test"},
    )
    request = ToolExecuteRequest(
        name="mcp_server", arguments={"__tool_name__": "remote_tool", "x": 1}
    )
    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch(
            "app.api.v1.endpoints.tools.Tool.filter",
            return_value=QueryResult(custom_tool),
        ),
        patch(
            "app.api.v1.endpoints.tools.execute_mcp_tool",
            new=AsyncMock(side_effect=RuntimeError("connection failed")),
        ) as execute_mcp,
    ):
        response = await execute_test_tool(
            request, team_id=uuid4(), current_user=user()
        )

    assert response["data"].success is False
    assert response["data"].error
    execute_mcp.assert_awaited_once_with(
        mcp_config=custom_tool.mcp_config,
        tool_name="remote_tool",
        arguments={"x": 1},
        timeout=60.0,
    )


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


@pytest.mark.anyio
async def test_list_tool_configs_covers_team_and_global_guards():
    team_id = uuid4()
    config = SimpleNamespace(
        id=uuid4(),
        tool_name="search",
        team_id=team_id,
        credentials={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    query = QueryResult([config])
    with (
        patch(
            "app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()
        ) as access,
        patch(
            "app.models.tool_config.ToolConfig.filter", return_value=query
        ) as filter_,
    ):
        response = await list_tool_configs(team_id, user())

    assert len(response["data"]) == 1
    access.assert_awaited_once_with(team_id, response_user := access.await_args.args[1])
    assert response_user.is_superuser is False
    filter_.assert_called_once_with(team_id=team_id)

    with pytest.raises(BusinessError):
        await list_tool_configs(None, user())

    with patch(
        "app.models.tool_config.ToolConfig.filter", return_value=QueryResult([])
    ) as global_filter:
        response = await list_tool_configs(None, user(is_superuser=True))

    assert response["data"] == []
    global_filter.assert_called_once_with(team_id=None)


@pytest.mark.anyio
async def test_create_tool_config_checks_team_admin_and_duplicate():
    team_id = uuid4()
    current_user = user()
    with (
        patch(
            "app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()
        ) as access,
        patch(
            "app.models.tool_config.ToolConfig.filter",
            return_value=QueryResult(SimpleNamespace(id=uuid4())),
        ),
        pytest.raises(BusinessError),
    ):
        await create_tool_config(
            {"tool_name": "search", "credentials": {}},
            DummyRequest(),
            team_id,
            current_user,
        )

    access.assert_awaited_once_with(team_id, current_user, require_admin=True)


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [update_tool_config, delete_tool_config])
async def test_tool_config_mutations_reject_non_superuser_global_access(endpoint):
    args = ["search"]
    if endpoint is update_tool_config:
        args.append({"credentials": {}})
    args.extend([DummyRequest(), None, user()])

    with pytest.raises(BusinessError):
        await endpoint(*args)


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", [update_tool_config, delete_tool_config])
async def test_tool_config_mutations_raise_not_found_for_team_config(endpoint):
    team_id = uuid4()
    current_user = user()
    args = ["search"]
    if endpoint is update_tool_config:
        args.append({"credentials": {}})
    args.extend([DummyRequest(), team_id, current_user])

    with (
        patch(
            "app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()
        ) as access,
        patch(
            "app.models.tool_config.ToolConfig.filter", return_value=QueryResult(None)
        ),
        pytest.raises(BusinessError),
    ):
        await endpoint(*args)

    access.assert_awaited_once_with(team_id, current_user, require_admin=True)
