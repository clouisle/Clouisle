from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolType as DBToolType
from app.schemas.response import BusinessError


class Query:
    def __init__(self, *, first=None, items=(), count=0):
        self.first_value = first
        self.items = list(items)
        self.count_value = count

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


def user():
    return SimpleNamespace(id=uuid4(), locale="en", is_superuser=False)


def db_tool(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(name="Owners"),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecasts",
        "icon": None,
        "category": "other",
        "type": DBToolType.CUSTOM,
        "custom_type": DBCustomToolType.HTTP,
        "parameters": [],
        "http_config": {"url": "https://example.test", "method": "GET"},
        "code_config": {},
        "mcp_config": {},
        "credentials": {},
        "is_enabled": True,
        "created_by_id": uuid4(),
        "created_by": SimpleNamespace(username="creator"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def data(response):
    return response["data"]


@pytest.mark.anyio
async def test_legacy_list_groups_owned_and_shared_tools(monkeypatch):
    current, team_id = user(), uuid4()
    owned_custom = db_tool(team_id=team_id)
    owned_mcp = db_tool(team_id=team_id, type=DBToolType.MCP, custom_type=None)
    shared_custom = db_tool()
    shared_mcp = db_tool(type=DBToolType.MCP, custom_type=None)
    queries = iter([Query(items=[owned_custom]), Query(items=[owned_mcp])])
    access = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools, "get_builtin_tools", lambda _locale: [])
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: next(queries))
    monkeypatch.setattr(
        tools.ToolShare,
        "filter",
        lambda **kwargs: Query(
            items=[
                SimpleNamespace(tool=shared_custom, permission="read_only"),
                SimpleNamespace(tool=shared_mcp, permission="read_execute"),
            ]
            if "shared_with_team_id" in kwargs
            else (),
            count=2,
        ),
    )

    result = data(await tools.list_tools_legacy(team_id, True, current))

    assert [item.name for item in result.custom] == ["weather", "weather"]
    assert [item.name for item in result.mcp] == ["weather", "weather"]
    assert result.custom[0].is_owned is True
    assert result.custom[1].is_owned is False
    assert result.mcp[1].share_permission.value == "read_execute"
    access.assert_awaited_once_with(team_id, current)


@pytest.mark.anyio
async def test_file_parsers_include_builtin_and_http_parameters(monkeypatch):
    current, team_id = user(), uuid4()
    builtin = SimpleNamespace(name="parser", description="Parse", parameters=[])
    custom = db_tool(
        team_id=team_id,
        category="file",
        http_config={
            "url": "https://parser.test",
            "parameters": [{"name": "file", "type": "string", "required": True}],
        },
    )
    no_http_config = db_tool(
        team_id=team_id,
        name="plain_parser",
        display_name="Plain parser",
        category="file",
        http_config={},
    )
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(tools.tool_registry, "get_all_tools", lambda: [builtin])
    monkeypatch.setattr(
        tools,
        "BUILTIN_TOOLS_METADATA",
        {"parser": {"is_file_parser": True, "category": "file"}},
    )
    monkeypatch.setattr(
        tools.Tool, "filter", lambda **_kwargs: Query(items=[custom, no_http_config])
    )

    result = data(await tools.list_file_parsers(team_id, current))

    assert [item.name for item in result] == ["parser", "weather", "plain_parser"]
    assert result[1].parameters[0].name == "file"
    assert result[2].parameters == []


@pytest.mark.anyio
async def test_get_tool_by_name_uses_sandbox_then_team_and_not_found(monkeypatch):
    current, team_id = user(), uuid4()
    sandbox = SimpleNamespace(name="bash", description="Run", parameters=[])
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(
        tools.tool_registry, "get_sandbox_tool_infos", lambda _names: [sandbox]
    )

    assert data(await tools.get_tool_by_name("bash", None, current)).name == "bash"

    existing = db_tool(team_id=team_id)
    access = AsyncMock()
    monkeypatch.setattr(
        tools.tool_registry, "get_sandbox_tool_infos", lambda _names: []
    )
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    assert (
        data(await tools.get_tool_by_name("weather", team_id, current)).id
        == existing.id
    )
    access.assert_awaited_once_with(team_id, current)

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.get_tool_by_name("missing", team_id, current)
    assert exc_info.value.msg_key == "tool_not_found"


@pytest.mark.anyio
async def test_shared_with_me_projects_custom_and_mcp_ownership(monkeypatch):
    current, team_id = user(), uuid4()
    custom = db_tool()
    mcp = db_tool(type=DBToolType.MCP, custom_type=None, created_by=None)
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        tools.ToolShare,
        "filter",
        lambda **_kwargs: Query(
            items=[
                SimpleNamespace(tool=custom, permission="read_only"),
                SimpleNamespace(tool=mcp, permission="read_execute"),
            ]
        ),
    )

    result = data(await tools.list_shared_tools(team_id, current))

    assert result["builtin"] == []
    assert result["custom"][0]["owner_team_name"] == "Owners"
    assert result["custom"][0]["created_by_name"] == "creator"
    assert result["mcp"][0]["share_permission"] == "read_execute"
    assert result["mcp"][0]["created_by_name"] is None
