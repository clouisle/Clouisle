from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.schemas.tool import ToolType


class Chain:
    def __init__(self, value=None):
        self.value = value

    def all(self):
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    async def first(self):
        return self.value

    async def count(self):
        return self.value

    def __await__(self):
        async def _result():
            return self.value

        return _result().__await__()


def tool_info(name):
    return SimpleNamespace(name=name, description=f"{name} desc", parameters=[])


def db_tool(team_id, *, http_config=None, name="parser"):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        display_name=name.title(),
        description=f"{name} desc",
        type=tools.DBToolType.CUSTOM,
        category=tools.ToolCategory.FILE.value,
        icon=None,
        parameters=[],
        is_enabled=True,
        credentials={},
        custom_type=tools.DBCustomToolType.HTTP,
        http_config=http_config,
        code_config={},
        mcp_config={},
        team_id=team_id,
        created_by_id=None,
        created_by=None,
    )


def response_data(response):
    return response["data"]


@pytest.mark.anyio
async def test_list_file_parsers_keeps_builtin_parser_and_custom_parameter_branches(
    monkeypatch,
):
    team_id = uuid4()
    user = SimpleNamespace(locale="en")
    custom_with_params = db_tool(
        team_id,
        http_config={
            "parameters": [
                {
                    "name": "file_url",
                    "type": "string",
                    "description": "File URL",
                    "required": True,
                }
            ]
        },
        name="custom_parser",
    )
    custom_without_config = db_tool(team_id, http_config=None, name="empty_parser")

    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        tools.tool_registry,
        "get_all_tools",
        lambda: [tool_info("builtin_parser"), tool_info("not_a_parser")],
    )
    monkeypatch.setattr(
        tools,
        "BUILTIN_TOOLS_METADATA",
        {
            "builtin_parser": {"is_file_parser": True, "category": "file"},
            "not_a_parser": {"category": "other"},
        },
    )
    monkeypatch.setattr(
        tools.Tool,
        "filter",
        MagicMock(return_value=Chain([custom_with_params, custom_without_config])),
    )

    response = await tools.list_file_parsers(team_id, user)

    parsers = response_data(response)
    assert [parser.name for parser in parsers] == [
        "builtin_parser",
        "custom_parser",
        "empty_parser",
    ]
    assert parsers[1].parameters[0].name == "file_url"
    assert parsers[2].parameters == []
    tools.Tool.filter.assert_called_once_with(
        team_id=team_id,
        is_enabled=True,
        category=tools.ToolCategory.FILE.value,
    )


@pytest.mark.anyio
async def test_filter_options_include_dynamic_categories_and_skip_empty_creators(
    monkeypatch,
):
    team = SimpleNamespace(id=uuid4(), name="Team A")
    monkeypatch.setattr(tools, "_get_accessible_teams", AsyncMock(return_value=[team]))
    monkeypatch.setattr(
        tools,
        "_build_accessible_tools",
        AsyncMock(
            return_value=[
                SimpleNamespace(category="vendor", created_by_name="zoe"),
                SimpleNamespace(category="api", created_by_name=None),
            ]
        ),
    )

    response = await tools.get_tool_filter_options(current_user=SimpleNamespace())

    data = response_data(response)
    assert any(option.value == "vendor" for option in data.categories)
    assert [option.value for option in data.creators] == ["zoe"]
    assert [(option.value, option.label) for option in data.teams] == [
        (str(team.id), team.name)
    ]


@pytest.mark.anyio
async def test_builtin_execution_uses_team_credentials_before_global_fallback(
    monkeypatch,
):
    team_id = uuid4()
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        tools.tool_registry,
        "get_tool",
        lambda name: tool_info(name) if name == "builtin" else None,
    )
    monkeypatch.setattr(tools.tool_registry, "execute", execute)

    from app.models.tool_config import ToolConfig

    monkeypatch.setattr(
        ToolConfig,
        "filter",
        MagicMock(
            side_effect=[
                Chain(SimpleNamespace(credentials={"team": "secret"})),
            ]
        ),
    )

    response = await tools.test_tool(
        tools.ToolExecuteRequest(name="builtin", arguments={"q": "x"}),
        team_id=team_id,
        current_user=SimpleNamespace(),
    )

    assert response_data(response).success is True
    execute.assert_awaited_once_with(
        "builtin", {"q": "x"}, credentials={"team": "secret"}
    )
    ToolConfig.filter.assert_called_once_with(tool_name="builtin", team_id=team_id)


@pytest.mark.anyio
async def test_builtin_execution_uses_global_credentials_when_team_config_empty(
    monkeypatch,
):
    team_id = uuid4()
    execute = AsyncMock(return_value="global-ok")
    monkeypatch.setattr(
        tools.tool_registry,
        "get_tool",
        lambda name: tool_info(name) if name == "builtin" else None,
    )
    monkeypatch.setattr(tools.tool_registry, "execute", execute)

    from app.models.tool_config import ToolConfig

    monkeypatch.setattr(
        ToolConfig,
        "filter",
        MagicMock(
            side_effect=[
                Chain(SimpleNamespace(credentials={})),
                Chain(SimpleNamespace(credentials={"global": "secret"})),
            ]
        ),
    )

    response = await tools.test_tool(
        tools.ToolExecuteRequest(name="builtin"),
        team_id=team_id,
        current_user=SimpleNamespace(),
    )

    assert response_data(response).result == "global-ok"
    execute.assert_awaited_once_with("builtin", {}, credentials={"global": "secret"})


def test_db_tool_to_out_maps_optional_fields_and_credentials():
    team_id = uuid4()
    tool = db_tool(
        team_id,
        http_config={"method": "GET", "url": "https://example.test"},
        name="http_tool",
    )
    tool.credentials = {"api_key": "secret"}
    tool.created_by_id = uuid4()

    out = tools.db_tool_to_out(tool, creator_name="ada")

    assert out.type == ToolType.CUSTOM
    assert out.category == "file"
    assert out.requires_config is True
    assert out.config_fields == ["api_key"]
    assert out.custom_type == tools.CustomToolType.HTTP
    assert out.http_config.url == "https://example.test"
    assert out.created_by_name == "ada"


def test_matches_filter_empty_none_and_value_branches():
    assert tools._matches_filter(None, set()) is True
    assert tools._matches_filter(None, {"enabled"}) is False
    assert tools._matches_filter("enabled", {"enabled"}) is True
    assert tools._matches_filter("disabled", {"enabled"}) is False


def test_category_value_accepts_enum_and_plain_values():
    assert tools._category_value(tools.ToolCategory.FILE) == "file"
    assert tools._category_value("vendor") == "vendor"
