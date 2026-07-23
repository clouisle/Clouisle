import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat_tools


class Query:
    def __init__(self, result=None):
        self.result = result

    async def first(self):
        return self.result


@pytest.mark.anyio
async def test_memory_tools_require_user_and_dispatch(monkeypatch):
    missing = await chat_tools.execute_tool_call("search_memory", {})
    assert "error" in json.loads(missing)

    from app.services.memory import MemoryService

    search = AsyncMock(return_value={"items": ["match"]})
    monkeypatch.setattr(MemoryService, "handle_search_memory", search)
    result = await chat_tools.execute_tool_call(
        "search_memory",
        {"query": "topic", "top_k": 3},
        user=SimpleNamespace(id=uuid4()),
    )

    assert json.loads(result) == {"items": ["match"]}
    search.assert_awaited_once()


@pytest.mark.anyio
async def test_mcp_tools_validate_name_configuration_and_result(monkeypatch):
    invalid = await chat_tools.execute_tool_call("mcp_invalid", {})
    assert "error" in json.loads(invalid)

    from app.models.tool import Tool
    from app.llm.tools import mcp_client

    monkeypatch.setattr(Tool, "filter", lambda **kwargs: Query(None))
    missing = await chat_tools.execute_tool_call("mcp_server_action", {})
    assert "error" in json.loads(missing)

    monkeypatch.setattr(
        Tool,
        "filter",
        lambda **kwargs: Query(SimpleNamespace(mcp_config={"command": "test"})),
    )
    execute = AsyncMock(
        return_value=SimpleNamespace(success=True, result={"ok": True}, error=None)
    )
    monkeypatch.setattr(mcp_client, "execute_mcp_tool", execute)
    result = await chat_tools.execute_tool_call(
        "mcp_server_action", {"value": 1}, tool_timeouts={"mcp": 4}
    )

    assert json.loads(result)["result"] == {"ok": True}
    assert execute.await_args.kwargs["timeout"] == 4


@pytest.mark.anyio
async def test_custom_tool_missing_unsupported_and_code_paths(monkeypatch):
    from app.models.tool import Tool, CustomToolType

    monkeypatch.setattr(Tool, "filter", lambda **kwargs: Query(None))
    assert "error" in json.loads(
        await chat_tools.execute_tool_call("custom_missing", {})
    )

    monkeypatch.setattr(
        Tool, "filter", lambda **kwargs: Query(SimpleNamespace(custom_type="unknown"))
    )
    assert "error" in json.loads(
        await chat_tools.execute_tool_call("custom_unknown", {})
    )

    code_tool = SimpleNamespace(custom_type=CustomToolType.CODE)
    monkeypatch.setattr(Tool, "filter", lambda **kwargs: Query(code_tool))
    execute = AsyncMock(return_value={"success": True, "result": 7})
    monkeypatch.setattr(chat_tools, "_execute_code_tool", execute)
    result = await chat_tools.execute_tool_call(
        "custom_calculate", {"value": 3}, session_id="session"
    )
    assert json.loads(result)["result"] == 7


@pytest.mark.anyio
async def test_registered_builtin_executes_and_unknown_tool_fails(monkeypatch):
    from app.llm.tools import tool_registry

    def handler(credentials=None):
        return credentials

    monkeypatch.setattr(
        tool_registry,
        "get_tool",
        lambda name: SimpleNamespace(handler=handler) if name == "weather" else None,
    )
    monkeypatch.setattr(tool_registry, "get_sandbox_tool_class", lambda name: None)
    execute = AsyncMock(return_value={"temperature": 20})
    monkeypatch.setattr(tool_registry, "execute", execute)
    monkeypatch.setattr(
        chat_tools,
        "_get_builtin_tool_credentials",
        AsyncMock(return_value={"key": "test"}),
    )

    result = await chat_tools.execute_tool_call("weather", {"city": "Paris"})
    assert result == {"temperature": 20}
    assert execute.await_args.kwargs["credentials"] == {"key": "test"}

    missing = await chat_tools.execute_tool_call("not_registered", {})
    assert "error" in json.loads(missing)


def test_tool_helpers_cover_credentials_and_display():
    def accepts(credentials=None):
        return credentials

    assert chat_tools._tool_accepts_credentials(accepts)
    assert not chat_tools._tool_accepts_credentials(lambda: None)
    assert chat_tools._get_item_value({"name": "value"}, "name") == "value"
    assert chat_tools._get_item_value(SimpleNamespace(name="value"), "name") == "value"
    assert chat_tools._get_tool_result_display({"ok": True}) == '{"ok": true}'
    assert chat_tools._get_tool_result_display("text") == "text"
    assert chat_tools._get_tool_result_display(4) == "4"
    assert chat_tools._get_tool_result_display(None) is None


@pytest.mark.anyio
async def test_builtin_credentials_prefer_team_then_global(monkeypatch):
    from app.models.tool_config import ToolConfig

    team = SimpleNamespace(credentials={"team": "value"})
    monkeypatch.setattr(ToolConfig, "filter", lambda **kwargs: Query(team))
    assert await chat_tools._get_builtin_tool_credentials(
        "weather", SimpleNamespace(team_id=uuid4())
    ) == {"team": "value"}

    monkeypatch.setattr(
        ToolConfig,
        "filter",
        lambda **kwargs: Query(SimpleNamespace(credentials={"global": "value"})),
    )
    assert await chat_tools._get_builtin_tool_credentials("weather", None) == {
        "global": "value"
    }
