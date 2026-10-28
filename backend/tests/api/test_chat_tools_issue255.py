import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat_tools


def _patch_policy_boundary(monkeypatch, user):
    """Run the real invoke resolver but skip the persistence boundary."""
    from app.services import builtin_tools, tool_execution

    async def execute(definition, operation, arguments, context, invoke, **kwargs):
        return await invoke(arguments, None)

    monkeypatch.setattr(tool_execution, "execute_stored_tool", execute)
    monkeypatch.setattr(
        builtin_tools,
        "get_builtin_definition",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), name="definition")),
    )
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )


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
    user = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    _patch_policy_boundary(monkeypatch, user)
    result = await chat_tools.execute_tool_call(
        "search_memory",
        {"query": "topic", "top_k": 3},
        user=user,
        agent=agent,
    )

    assert json.loads(result) == {"items": ["match"]}
    search.assert_awaited_once()


@pytest.mark.anyio
async def test_mcp_tools_validate_name_configuration_and_result(monkeypatch):
    missing = await chat_tools.execute_tool_call("mcp_invalid", {})
    assert "error" in json.loads(missing)

    delegated = AsyncMock(return_value={"result": {"ok": True}})
    monkeypatch.setattr(
        "app.services.agent_tool_execution.execute_agent_stored_tool", delegated
    )
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    result = await chat_tools.execute_tool_call(
        "mcp_server_action", {"value": 1}, agent=agent, user=user
    )

    assert json.loads(result)["result"] == {"ok": True}
    assert delegated.await_args.args == (
        agent,
        "mcp_server_action",
        {"value": 1},
        user,
    )


@pytest.mark.anyio
async def test_custom_tool_missing_unsupported_and_code_paths(monkeypatch):
    from app.schemas.response import BusinessError

    delegated = AsyncMock(return_value={"success": True, "result": 7})
    monkeypatch.setattr(
        "app.services.agent_tool_execution.execute_agent_stored_tool", delegated
    )
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    result = await chat_tools.execute_tool_call(
        "custom_calculate", {"value": 3}, agent=agent, user=user
    )
    assert json.loads(result)["result"] == 7

    delegated.side_effect = BusinessError(
        code=404, msg_key="tool_not_found", status_code=404
    )
    missing = await chat_tools.execute_tool_call(
        "custom_missing", {}, agent=agent, user=user
    )
    assert "error" in json.loads(missing)


@pytest.mark.anyio
async def test_registered_builtin_executes_and_unknown_tool_fails(monkeypatch):
    from app.llm.tools import tool_registry

    def handler(credentials=None):
        return credentials

    team_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=team_id, tools_config=[])
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        tool_registry,
        "get_tool",
        lambda name: SimpleNamespace(handler=handler) if name == "weather" else None,
    )
    monkeypatch.setattr(tool_registry, "get_sandbox_tool_class", lambda name: None)
    execute = AsyncMock(return_value={"temperature": 20})
    monkeypatch.setattr("app.services.tool.ToolExecutor.execute_builtin_tool", execute)
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )

    result = await chat_tools.execute_tool_call(
        "weather", {"city": "Paris"}, agent=agent, user=user
    )
    assert result == {"temperature": 20}
    assert execute.await_args.kwargs["team_id"] == team_id
    assert execute.await_args.kwargs["tool_name"] == "weather"

    missing = await chat_tools.execute_tool_call("not_registered", {})
    assert "error" in json.loads(missing)


def test_tool_helpers_cover_display_and_item_values():
    assert chat_tools._get_item_value({"name": "value"}, "name") == "value"
    assert chat_tools._get_item_value(SimpleNamespace(name="value"), "name") == "value"


@pytest.mark.anyio
async def test_builtin_execution_routes_through_unified_boundary(monkeypatch):
    from app.llm.tools import tool_registry

    team_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=team_id, tools_config=[])
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        tool_registry,
        "get_tool",
        lambda _name: SimpleNamespace(handler=lambda credentials=None: None),
    )
    monkeypatch.setattr(tool_registry, "get_sandbox_tool_class", lambda _name: None)
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr("app.services.tool.ToolExecutor.execute_builtin_tool", execute)
    monkeypatch.setattr(
        "app.models.user.User.get_or_none", AsyncMock(return_value=user)
    )

    await chat_tools.execute_tool_call("get_current_time", {}, agent=agent, user=user)

    kwargs = execute.await_args.kwargs
    assert kwargs["team_id"] == team_id
    assert kwargs["user"] is user
    assert kwargs["agent"] is agent
