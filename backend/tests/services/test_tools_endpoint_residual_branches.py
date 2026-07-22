from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints import tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import ToolType as DBToolType
from app.schemas.response import BusinessError
from app.schemas.tool import CodeExecuteRequest, McpToolsListRequest, ToolExecuteRequest
from app.services.sandbox.models import SandboxExecutionMetadata, SandboxJobSource


class DummyUser:
    id = "user-1"
    locale = "en"
    is_superuser = False


class QueryStub:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    async def first(self):
        return self.result


class DummyTool:
    def __init__(self, *, type=DBToolType.CUSTOM, custom_type=None, **config):
        self.type = type
        self.custom_type = custom_type
        self.mcp_config = config.get("mcp_config", {})
        self.http_config = config.get("http_config", {})
        self.code_config = config.get("code_config", {})
        self.credentials = config.get("credentials", {})


@pytest.mark.anyio
async def test_get_mcp_tools_wraps_connection_failure():
    request = McpToolsListRequest(
        mcp_config={"transport": "http", "url": "https://mcp.test"}
    )

    with patch(
        "app.api.v1.endpoints.tools.list_mcp_tools",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await tools.get_mcp_tools(request, DummyUser())

    assert exc_info.value.msg_key == "mcp_connection_failed"
    assert exc_info.value.status_code == 500


@pytest.mark.anyio
async def test_test_tool_mcp_requires_saved_config():
    request = ToolExecuteRequest(name="remote", arguments={"x": 1})
    tool = DummyTool(type=DBToolType.MCP, mcp_config={})

    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=QueryStub(tool)),
    ):
        response = await tools.test_tool(
            request, team_id="team-1", current_user=DummyUser()
        )

    assert response["data"].success is False
    assert response["data"].error


@pytest.mark.anyio
async def test_test_tool_mcp_uses_tool_name_override_without_leaking_argument():
    request = ToolExecuteRequest(
        name="remote", arguments={"__tool_name__": "actual", "x": 1}
    )
    tool = DummyTool(
        type=DBToolType.MCP, mcp_config={"transport": "http", "url": "https://mcp.test"}
    )
    result = SimpleNamespace(success=True, result={"ok": True}, error=None)

    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=QueryStub(tool)),
        patch(
            "app.api.v1.endpoints.tools.execute_mcp_tool",
            new=AsyncMock(return_value=result),
        ) as mock_execute,
    ):
        response = await tools.test_tool(
            request, team_id="team-1", current_user=DummyUser()
        )

    mock_execute.assert_awaited_once_with(
        mcp_config=tool.mcp_config,
        tool_name="actual",
        arguments={"x": 1},
        timeout=60.0,
    )
    assert response["data"].success is True
    assert response["data"].result == {"ok": True}


@pytest.mark.anyio
async def test_test_tool_code_without_code_returns_validation_error():
    request = ToolExecuteRequest(name="script", arguments={})
    tool = DummyTool(
        custom_type=DBCustomToolType.CODE, code_config={"language": "python"}
    )

    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=QueryStub(tool)),
    ):
        response = await tools.test_tool(
            request, team_id="team-1", current_user=DummyUser()
        )

    assert response["data"].success is False
    assert response["data"].error


@pytest.mark.anyio
async def test_test_tool_code_submits_sandbox_job_and_serializes_logs():
    request = ToolExecuteRequest(name="script", arguments={"x": 1})
    tool = DummyTool(
        custom_type=DBCustomToolType.CODE,
        code_config={
            "language": "python",
            "code": "print(params)",
            "limits": {"timeout_seconds": 12},
        },
    )
    job = SimpleNamespace(limits=SimpleNamespace(timeout_seconds=12.0))
    runtime_result = SimpleNamespace(
        success=False,
        result=None,
        error="bad",
        stdout="trace",
        artifacts=[],
        metadata=SandboxExecutionMetadata(duration_ms=88, total_ms=88),
    )

    with (
        patch("app.api.v1.endpoints.tools.tool_registry.get_tool", return_value=None),
        patch("app.api.v1.endpoints.tools.check_team_access", new=AsyncMock()),
        patch("app.api.v1.endpoints.tools.Tool.filter", return_value=QueryStub(tool)),
        patch(
            "app.api.v1.endpoints.tools.compile_code_config_job", return_value=job
        ) as mock_compile,
        patch(
            "app.api.v1.endpoints.tools.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=runtime_result),
        ) as mock_submit,
    ):
        response = await tools.test_tool(
            request, team_id="team-1", current_user=DummyUser()
        )

    mock_compile.assert_called_once_with(
        code_config=tool.code_config,
        params={"x": 1},
        timeout=12.0,
        source=SandboxJobSource.TOOL,
    )
    mock_submit.assert_awaited_once_with(job, timeout_seconds=17.0)
    assert response["data"].success is False
    assert response["data"].error == "bad"
    assert response["data"].logs == "trace"
    assert response["data"].duration_ms == 88


@pytest.mark.anyio
async def test_execute_code_directly_rejects_unsupported_language_before_compile():
    request = CodeExecuteRequest(language="ruby", code="puts 1")

    with patch("app.api.v1.endpoints.tools.compile_code_config_job") as mock_compile:
        response = await tools.execute_code_directly(request, DummyUser())

    mock_compile.assert_not_called()
    assert response["data"].success is False
    assert response["data"].error
