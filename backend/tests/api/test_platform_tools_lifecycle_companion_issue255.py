from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import CustomToolType, ToolType
from app.schemas.response import BusinessError
from app.schemas.tool import ToolExecuteRequest, ToolUpdateInput


class Query:
    def __init__(self, *, first=None, items=(), count=0):
        self.first_value = first
        self.items = list(items)
        self.count_value = count

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
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
    return SimpleNamespace(
        id=uuid4(), username="member", locale="en", is_superuser=False
    )


def db_tool(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(name="Owners"),
        "name": "weather",
        "display_name": "Weather",
        "description": "Forecasts",
        "icon": None,
        "category": "other",
        "type": ToolType.CUSTOM,
        "custom_type": CustomToolType.HTTP,
        "parameters": [],
        "http_config": {"url": "https://example.test", "method": "GET"},
        "code_config": {},
        "mcp_config": {},
        "credentials": {"token": "secret"},
        "is_enabled": True,
        "created_by_id": uuid4(),
        "created_by": SimpleNamespace(username="creator"),
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def data(response):
    return response["data"]


@pytest.mark.asyncio
async def test_legacy_list_classifies_owned_and_shared_custom_and_mcp(monkeypatch):
    current = user()
    team_id = uuid4()
    owned_custom = db_tool(team_id=team_id)
    owned_mcp = db_tool(
        team_id=team_id,
        name="owned_mcp",
        type=ToolType.MCP,
        custom_type=None,
        http_config={},
        mcp_config={"transport": "sse", "url": "https://mcp.test"},
    )
    shared_custom = db_tool(name="shared_custom", created_by=None)
    shared_mcp = db_tool(
        name="shared_mcp",
        type=ToolType.MCP,
        custom_type=None,
        http_config={},
        mcp_config={"transport": "sse", "url": "https://mcp.test"},
    )
    shares = [
        SimpleNamespace(tool=shared_custom, permission="read_only"),
        SimpleNamespace(tool=shared_mcp, permission="read_execute"),
    ]
    tool_queries = iter([Query(items=[owned_custom]), Query(items=[owned_mcp])])

    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(tools, "get_builtin_tools", lambda _locale: [])
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: next(tool_queries))
    monkeypatch.setattr(
        tools.ToolShare,
        "filter",
        lambda **kwargs: Query(
            items=shares if "shared_with_team_id" in kwargs else (), count=2
        ),
    )

    result = data(await tools.list_tools_legacy(team_id, True, current))

    assert [item.name for item in result.custom] == ["weather", "shared_custom"]
    assert [item.name for item in result.mcp] == ["owned_mcp", "shared_mcp"]
    assert result.custom[0].shared_with_count == 2
    assert result.custom[1].created_by_name is None
    assert result.mcp[1].share_permission.value == "read_execute"


@pytest.mark.asyncio
async def test_update_covers_remaining_fields_and_not_found(monkeypatch):
    current = user()
    request = MagicMock()
    existing = db_tool()
    queries = iter([Query(first=existing), Query()])
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: next(queries))
    monkeypatch.setattr(tools, "check_tool_write_access", AsyncMock())
    monkeypatch.setattr(tools.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(tools.AuditLogService, "log", AsyncMock())

    result = data(
        await tools.update_tool(
            existing.id,
            ToolUpdateInput(
                icon="cloud",
                http_config={"url": "https://updated.test", "method": "POST"},
                mcp_config={"transport": "sse", "url": "https://mcp.test"},
            ),
            request,
            current,
        )
    )

    assert result.icon == "cloud"
    assert result.http_config.url == "https://updated.test"
    assert result.mcp_config.url == "https://mcp.test"
    existing.save.assert_awaited_once()

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.update_tool(uuid4(), ToolUpdateInput(), request, current)
    assert exc_info.value.msg_key == "tool_not_found"


@pytest.mark.asyncio
async def test_name_lookup_uses_sandbox_then_database_and_reports_missing(monkeypatch):
    current = user()
    team_id = uuid4()
    sandbox_info = SimpleNamespace(
        name="read",
        description="Read",
        parameters=[],
    )
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(
        tools.tool_registry,
        "get_sandbox_tool_infos",
        lambda names: [sandbox_info] if names == ["read"] else [],
    )

    sandbox = data(await tools.get_tool_by_name("read", None, current))
    assert sandbox.name == "read"

    existing = db_tool(team_id=team_id)
    access = AsyncMock()
    monkeypatch.setattr(tools, "check_team_access", access)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=existing))
    custom = data(await tools.get_tool_by_name(existing.name, team_id, current))
    assert custom.id == existing.id
    access.assert_awaited_once_with(team_id, current)

    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await tools.get_tool_by_name("missing", team_id, current)
    assert exc_info.value.msg_key == "tool_not_found"


@pytest.mark.asyncio
async def test_custom_mcp_execution_covers_configuration_success_and_failure(
    monkeypatch,
):
    current = user()
    team_id = uuid4()
    mcp_tool = db_tool(
        team_id=team_id,
        name="mcp_proxy",
        type=ToolType.MCP,
        custom_type=None,
        http_config={},
        mcp_config={},
    )
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=mcp_tool))

    missing = data(
        await tools.test_tool(ToolExecuteRequest(name=mcp_tool.name), team_id, current)
    )
    assert missing.success is False
    assert missing.error

    mcp_tool.mcp_config = {"transport": "sse", "url": "https://mcp.test"}
    execute = AsyncMock(
        return_value=SimpleNamespace(success=True, result={"ok": True}, error=None)
    )
    monkeypatch.setattr(tools, "execute_mcp_tool", execute)
    request = ToolExecuteRequest(
        name=mcp_tool.name,
        arguments={"__tool_name__": "remote_name", "value": 1},
    )
    succeeded = data(await tools.test_tool(request, team_id, current))
    assert succeeded.success is True
    execute.assert_awaited_once_with(
        mcp_config=mcp_tool.mcp_config,
        tool_name="remote_name",
        arguments={"value": 1},
        timeout=60.0,
    )

    monkeypatch.setattr(
        tools, "execute_mcp_tool", AsyncMock(side_effect=RuntimeError("secret detail"))
    )
    monkeypatch.setattr(
        tools,
        "resolve_user_visible_error",
        lambda _error, **_kwargs: "safe MCP error",
    )
    failed = data(
        await tools.test_tool(ToolExecuteRequest(name=mcp_tool.name), team_id, current)
    )
    assert failed.success is False
    assert failed.error == "safe MCP error"


@pytest.mark.asyncio
async def test_custom_code_missing_and_unsupported_types_do_not_execute(monkeypatch):
    current = user()
    team_id = uuid4()
    custom = db_tool(
        team_id=team_id,
        custom_type=CustomToolType.CODE,
        http_config={},
        code_config={},
    )
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools, "check_team_access", AsyncMock())
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(first=custom))
    submit = AsyncMock()
    monkeypatch.setattr(tools.sandbox_gateway, "submit_and_wait", submit)

    missing_code = data(
        await tools.test_tool(ToolExecuteRequest(name=custom.name), team_id, current)
    )
    assert missing_code.success is False
    submit.assert_not_awaited()

    custom.custom_type = None
    unsupported = data(
        await tools.test_tool(ToolExecuteRequest(name=custom.name), team_id, current)
    )
    assert unsupported.success is False
    assert unsupported.error
    submit.assert_not_awaited()
