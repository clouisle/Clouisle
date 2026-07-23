from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.schemas.response import BusinessError
from app.schemas.tool import (
    CodeExecuteRequest,
    McpConfigSchema,
    McpToolsListRequest,
    ToolExecuteRequest,
    ToolType,
)


class Chain:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def all(self):
        return self

    def __await__(self):
        async def _result():
            return self.value

        return _result().__await__()

    async def first(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    async def count(self):
        return len(self.value or [])


class ToolFilter:
    def __init__(self, custom=None, mcp=None, by_name=None):
        self.custom = custom or []
        self.mcp = mcp or []
        self.by_name = by_name or {}

    def __call__(self, **kwargs):
        if "name" in kwargs:
            return Chain(self.by_name.get(kwargs["name"]))
        if kwargs.get("type") == tools.DBToolType.MCP:
            return Chain(self.mcp)
        return Chain(self.custom)


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4(), locale="en", is_superuser=False)


@pytest.fixture
def team():
    return SimpleNamespace(id=uuid4(), name="Team A")


def tool_info(name="calc"):
    return SimpleNamespace(
        name=name,
        description="builtin desc",
        parameters=[
            SimpleNamespace(
                name="x",
                type="string",
                description="x",
                required=True,
                enum=None,
                default=None,
            )
        ],
    )


def db_tool(name, team_id, *, type_=None, custom_type=None, enabled=True, config=None):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        display_name=name.title(),
        description=f"{name} desc",
        type=type_ or tools.DBToolType.CUSTOM,
        category="other",
        icon=None,
        parameters=[],
        is_enabled=enabled,
        credentials={},
        custom_type=custom_type,
        http_config=config if custom_type == tools.DBCustomToolType.HTTP else {},
        code_config=config if custom_type == tools.DBCustomToolType.CODE else {},
        mcp_config=config if type_ == tools.DBToolType.MCP else {},
        team_id=team_id,
        created_by_id=uuid4(),
        created_by=SimpleNamespace(username="maker"),
        team=SimpleNamespace(id=team_id, name="Owner"),
    )


def data(response):
    return response["data"]


@pytest.mark.anyio
async def test_list_tools_filters_builtins_custom_mcp_and_rejects_unowned_team(
    monkeypatch, user, team
):
    custom = db_tool("alpha", team.id, custom_type=tools.DBCustomToolType.HTTP)
    mcp = db_tool(
        "remote",
        team.id,
        type_=tools.DBToolType.MCP,
        config={"transport": "http", "url": "https://mcp.test"},
    )

    monkeypatch.setattr(tools, "_get_accessible_teams", AsyncMock(return_value=[team]))
    monkeypatch.setattr(
        tools.tool_registry,
        "get_all_tools",
        lambda: [tool_info("builtin_ok"), tool_info("generate_image")],
    )
    monkeypatch.setattr(
        tools.tool_registry,
        "get_sandbox_tool_infos",
        lambda names: [tool_info(name) for name in names],
    )
    monkeypatch.setattr(tools.Tool, "filter", ToolFilter(custom=[custom], mcp=[mcp]))
    monkeypatch.setattr(tools.ToolShare, "filter", lambda **_kwargs: Chain([]))

    response = await tools.list_tools(
        page=1,
        page_size=10,
        search="remote",
        type=[ToolType.MCP.value],
        category=["other"],
        status=["enabled"],
        team_id=[team.id],
        creator=["maker"],
        current_user=user,
    )

    assert data(response).total == 1
    assert data(response).items[0].name == "remote"

    with pytest.raises(BusinessError) as exc:
        await tools.list_tools(team_id=[uuid4()], current_user=user)
    assert exc.value.msg_key == "not_team_member"


@pytest.mark.anyio
async def test_get_by_name_uses_sandbox_fallback_custom_lookup_and_not_found(
    monkeypatch, user, team
):
    custom = db_tool("saved", team.id, custom_type=tools.DBCustomToolType.HTTP)
    access = AsyncMock()

    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda name: None)
    monkeypatch.setattr(
        tools.tool_registry,
        "get_sandbox_tool_infos",
        lambda names: [tool_info(names[0])],
    )
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.Tool, "filter", ToolFilter(by_name={"saved": custom}))

    sandbox_response = await tools.get_tool_by_name("bash", current_user=user)
    assert data(sandbox_response).name == "bash"

    custom_response = await tools.get_tool_by_name(
        "saved", team_id=team.id, current_user=user
    )
    assert data(custom_response).id == custom.id
    access.assert_awaited_once_with(team.id, user)

    with pytest.raises(BusinessError) as exc:
        await tools.get_tool_by_name("missing", current_user=user)
    assert exc.value.msg_key == "tool_not_found"


@pytest.mark.anyio
async def test_execute_mcp_handles_name_override_empty_config_and_exception(
    monkeypatch, user, team
):
    empty = db_tool("empty_mcp", team.id, type_=tools.DBToolType.MCP, config={})
    configured = db_tool(
        "remote_mcp",
        team.id,
        type_=tools.DBToolType.MCP,
        config={"transport": "http", "url": "https://mcp.test"},
    )
    execute = AsyncMock(
        return_value=SimpleNamespace(success=True, result={"ok": True}, error=None)
    )

    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        tools.Tool,
        "filter",
        ToolFilter(by_name={"empty_mcp": empty, "remote_mcp": configured}),
    )
    monkeypatch.setattr(tools, "execute_mcp_tool", execute)

    missing_config = await tools.test_tool(
        ToolExecuteRequest(name="empty_mcp"), team_id=team.id, current_user=user
    )
    assert data(missing_config).success is False
    assert "empty_mcp" in data(missing_config).error

    args = {"__tool_name__": "actual_remote", "value": 3}
    ok = await tools.test_tool(
        ToolExecuteRequest(name="remote_mcp", arguments=args),
        team_id=team.id,
        current_user=user,
    )
    assert data(ok).success is True
    assert execute.await_args.kwargs["arguments"] == {"value": 3}
    assert execute.await_args.kwargs["tool_name"] == "actual_remote"

    execute.side_effect = RuntimeError("provider exploded")
    failed = await tools.test_tool(
        ToolExecuteRequest(name="remote_mcp"), team_id=team.id, current_user=user
    )
    assert data(failed).success is False
    assert data(failed).error


@pytest.mark.anyio
async def test_execute_saved_code_returns_logs_artifacts_duration_and_direct_language_branch(
    monkeypatch, user, team
):
    code_tool = db_tool(
        "codey",
        team.id,
        custom_type=tools.DBCustomToolType.CODE,
        config={"code": "return params", "limits": {"timeout_seconds": 2}},
    )
    artifact = {
        "path": "/workspace/out.txt",
        "filename": "out.txt",
        "url": "/files/out.txt",
        "size": 4,
        "content_type": "text/plain",
    }
    runtime = SimpleNamespace(
        success=True,
        result={"done": True},
        error=None,
        stdout="ran\n",
        artifacts=[artifact],
        metadata=SimpleNamespace(duration_ms=17),
    )
    submit = AsyncMock(return_value=runtime)

    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(tools.Tool, "filter", ToolFilter(by_name={"codey": code_tool}))
    monkeypatch.setattr(tools.sandbox_gateway, "submit_and_wait", submit)

    saved = await tools.test_tool(
        ToolExecuteRequest(name="codey", arguments={"a": 1}),
        team_id=team.id,
        current_user=user,
    )
    assert data(saved).success is True
    assert data(saved).logs == "ran\n"
    assert data(saved).duration_ms == 17
    assert data(saved).artifacts[0].filename == "out.txt"

    unsupported = await tools.execute_code_directly(
        CodeExecuteRequest(language="ruby", code="puts 1"), current_user=user
    )
    assert data(unsupported).success is False
    assert "ruby" in data(unsupported).error


@pytest.mark.anyio
async def test_mcp_list_success_and_failure(monkeypatch, user):
    monkeypatch.setattr(
        tools,
        "list_mcp_tools",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="remote", description=None, parameters={"type": "object"}
                )
            ]
        ),
    )
    ok = await tools.get_mcp_tools(
        McpToolsListRequest(
            mcp_config=McpConfigSchema(transport="http", url="https://mcp.test")
        ),
        current_user=user,
    )
    assert data(ok).tools[0].name == "remote"

    monkeypatch.setattr(
        tools, "list_mcp_tools", AsyncMock(side_effect=RuntimeError("down"))
    )
    with pytest.raises(BusinessError) as exc:
        await tools.get_mcp_tools(
            McpToolsListRequest(mcp_config=McpConfigSchema(command="mcp")),
            current_user=user,
        )
    assert exc.value.msg_key == "mcp_connection_failed"


@pytest.mark.anyio
async def test_runtime_helpers_handle_missing_metadata_and_schema_passthrough():
    artifact = tools.SandboxArtifactSchema(path="/workspace/a.txt", filename="a.txt")

    assert tools._runtime_duration_ms(SimpleNamespace()) is None
    assert tools._serialize_runtime_artifacts([artifact])[0] is artifact
