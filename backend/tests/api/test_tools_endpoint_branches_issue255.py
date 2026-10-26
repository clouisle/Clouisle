from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import ToolType as DBToolType
from app.schemas.response import BusinessError
from app.schemas.tool import (
    CodeExecuteRequest,
    McpToolsListRequest,
    ToolExecuteRequest,
)


class Query:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


@pytest.mark.asyncio
async def test_mcp_discovery_maps_results_and_wraps_failures(monkeypatch):
    request = McpToolsListRequest(
        mcp_config={"transport": "http", "url": "https://mcp.example.test"}
    )
    discovered = [
        SimpleNamespace(
            name="lookup",
            description="Look up a record",
            parameters={"type": "object"},
        )
    ]
    list_tools = AsyncMock(return_value=discovered)
    monkeypatch.setattr(tools, "list_mcp_tools", list_tools)

    response = await tools.get_mcp_tools(request, SimpleNamespace())

    assert response["data"].tools[0].name == "lookup"
    list_tools.assert_awaited_once_with(request.mcp_config.model_dump())

    monkeypatch.setattr(
        tools,
        "list_mcp_tools",
        AsyncMock(side_effect=RuntimeError("connection secret")),
    )
    with pytest.raises(BusinessError) as exc_info:
        await tools.get_mcp_tools(request, SimpleNamespace())
    assert exc_info.value.msg_key == "mcp_connection_failed"
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_saved_mcp_execution_copies_arguments_and_shapes_results(monkeypatch):
    team_id = uuid4()
    current_user = SimpleNamespace(id=uuid4(), locale="en")
    custom_tool = SimpleNamespace(
        id=uuid4(),
        name="remote",
        team_id=team_id,
        type=DBToolType.MCP,
        custom_type=None,
        mcp_config={},
    )
    monkeypatch.setattr(tools.tool_registry, "get_tool", lambda _name: None)
    monkeypatch.setattr(tools.Tool, "filter", lambda **_kwargs: Query(custom_tool))
    execute = AsyncMock(
        return_value={"success": True, "result": {"value": 1}, "error": None}
    )
    monkeypatch.setattr(tools, "ToolExecutor", lambda: SimpleNamespace(execute=execute))

    missing = await tools.test_tool(
        ToolExecuteRequest(name="remote", arguments={}), team_id, current_user
    )
    assert missing["data"].success is False
    assert missing["data"].error
    execute.assert_not_awaited()

    custom_tool.mcp_config = {"transport": "http", "url": "https://mcp.example.test"}
    arguments = {"__tool_name__": "lookup", "id": 7}
    succeeded = await tools.test_tool(
        ToolExecuteRequest(name="remote", arguments=arguments), team_id, current_user
    )
    assert succeeded["data"].result == {"value": 1}
    tool_arg, args_arg = execute.await_args.args
    assert tool_arg is custom_tool
    assert args_arg == {"id": 7}
    assert execute.await_args.kwargs["operation"] == "lookup"
    assert arguments == {"__tool_name__": "lookup", "id": 7}

    execute.side_effect = RuntimeError("token leaked")
    monkeypatch.setattr(
        tools,
        "resolve_user_visible_error",
        lambda error, fallback_key=None: f"safe:{fallback_key}",
    )
    failed = await tools.test_tool(
        ToolExecuteRequest(name="remote", arguments={}), team_id, current_user
    )
    assert failed["data"].success is False
    assert failed["data"].error == "safe:mcp_tool_execution_failed"


@pytest.mark.asyncio
async def test_direct_code_rejects_unsupported_language_without_execution(monkeypatch):
    compile_job = AsyncMock()
    submit = AsyncMock()
    monkeypatch.setattr(tools, "compile_code_config_job", compile_job)
    monkeypatch.setattr(tools.sandbox_gateway, "submit_and_wait", submit)

    response = await tools.execute_code_directly(
        CodeExecuteRequest(language="ruby", code="puts 1"), SimpleNamespace()
    )

    assert response["data"].success is False
    assert response["data"].error
    compile_job.assert_not_awaited()
    submit.assert_not_awaited()
