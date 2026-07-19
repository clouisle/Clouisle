"""
Tests for the tool execution service.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.tool import CustomToolType, ToolType
from app.services.tool import ToolExecutor


class TestToolExecutor:
    @pytest.mark.anyio
    async def test_execute_builtin_tool_by_name(self):
        executor = ToolExecutor()

        with (
            patch.object(
                executor,
                "_get_tool_credentials",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.tool.tool_registry.execute",
                new=AsyncMock(return_value={"now": "2026-04-01 12:00:00"}),
            ) as mock_execute,
        ):
            result = await executor.execute_builtin_tool(
                tool_name="get_current_time",
                arguments={"timezone_name": "Asia/Shanghai"},
                team_id=None,
            )

        assert result == {"now": "2026-04-01 12:00:00"}
        mock_execute.assert_awaited_once_with(
            name="get_current_time",
            arguments={"timezone_name": "Asia/Shanghai"},
            credentials={},
        )

    @pytest.mark.anyio
    async def test_execute_dispatches_custom_tools_with_model_enum(self):
        executor = ToolExecutor()
        tool = MagicMock()
        tool.type = ToolType.CUSTOM
        tool.team_id = "team-1"

        with patch.object(
            executor,
            "_execute_custom_tool",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_execute_custom:
            result = await executor.execute(tool=tool, arguments={"x": 1})

        assert result == {"ok": True}
        mock_execute_custom.assert_awaited_once_with(tool=tool, arguments={"x": 1})

    @pytest.mark.anyio
    async def test_execute_dispatches_mcp_tools_with_plain_string(self):
        executor = ToolExecutor()
        tool = MagicMock()
        tool.type = "mcp"
        tool.team_id = None

        with patch.object(
            executor,
            "_execute_mcp_tool",
            new=AsyncMock(return_value={"ok": True}),
        ) as mock_execute_mcp:
            result = await executor.execute(tool=tool, arguments={"x": 1})

        assert result == {"ok": True}
        mock_execute_mcp.assert_awaited_once_with(tool=tool, arguments={"x": 1})

    @pytest.mark.anyio
    async def test_execute_custom_http_tool_uses_shared_executor_signature(self):
        executor = ToolExecutor()
        tool = MagicMock()
        tool.custom_type = CustomToolType.HTTP
        tool.http_config = {"url": "https://example.com", "method": "GET"}
        tool.credentials = {"api_key": "secret"}

        with patch(
            "app.services.tool.execute_http_tool",
            new=AsyncMock(return_value={"success": True, "result": {"ok": True}}),
        ) as mock_execute_http:
            result = await executor._execute_custom_tool(
                tool=tool, arguments={"q": "x"}
            )

        assert result == {"success": True, "result": {"ok": True}}
        mock_execute_http.assert_awaited_once_with(
            http_config=tool.http_config,
            arguments={"q": "x"},
            credentials=tool.credentials,
        )

    @pytest.mark.anyio
    async def test_execute_custom_code_tool_routes_through_sandbox_gateway(self):
        executor = ToolExecutor()
        tool = MagicMock()
        tool.custom_type = CustomToolType.CODE
        tool.code_config = {
            "language": "python",
            "code": "return {'ok': True}",
            "python_packages": ["requests==2.32.3"],
            "python_package_index_url": " https://mirror.example.com/simple/ ",
        }

        with (
            patch(
                "app.services.tool.compile_code_config_job",
                return_value=SimpleNamespace(
                    limits=SimpleNamespace(timeout_seconds=30.0),
                ),
            ) as mock_compile,
            patch(
                "app.services.tool.sandbox_gateway.submit_and_wait",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        success=True,
                        result={"ok": True},
                        error=None,
                        stdout="log line",
                        stderr="",
                        artifacts=[],
                    )
                ),
            ) as mock_submit,
        ):
            result = await executor._execute_custom_tool(tool=tool, arguments={"x": 1})

        assert result["success"] is True
        assert result["result"] == {"ok": True}
        assert result["stdout"] == "log line"
        mock_compile.assert_called_once()
        mock_submit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_builtin_execution_returns_safe_error(self):
        executor = ToolExecutor()

        with (
            patch.object(
                executor, "_get_tool_credentials", new=AsyncMock(return_value={})
            ),
            patch(
                "app.services.tool.tool_registry.execute",
                new=AsyncMock(side_effect=RuntimeError("provider failed")),
            ),
            patch(
                "app.services.tool.resolve_user_visible_error",
                return_value="Tool unavailable",
            ),
        ):
            result = await executor.execute_builtin_tool("weather", {})

        assert result == {"success": False, "error": "Tool unavailable"}

    @pytest.mark.anyio
    async def test_custom_tool_rejects_missing_configuration_and_unknown_type(self):
        executor = ToolExecutor()
        tool = MagicMock()

        tool.custom_type = CustomToolType.HTTP
        tool.http_config = None
        with pytest.raises(ValueError):
            await executor._execute_custom_tool(tool, {})

        tool.custom_type = "unsupported"
        with pytest.raises(ValueError):
            await executor._execute_custom_tool(tool, {})

    @pytest.mark.anyio
    async def test_mcp_tool_requires_configuration_and_executes(self):
        executor = ToolExecutor()
        tool = MagicMock()
        tool.name = "calendar"
        tool.mcp_config = None
        with pytest.raises(ValueError):
            await executor._execute_mcp_tool(tool, {})

        tool.mcp_config = {"transport": "stdio", "command": "calendar"}
        with patch(
            "app.services.tool.execute_mcp_tool",
            new=AsyncMock(return_value={"events": []}),
        ) as mock_execute:
            result = await executor._execute_mcp_tool(tool, {"date": "2026-04-01"})

        assert result == {"events": []}
        mock_execute.assert_awaited_once_with(
            tool_name="calendar",
            mcp_config=tool.mcp_config,
            arguments={"date": "2026-04-01"},
        )

    @pytest.mark.anyio
    async def test_credentials_prefer_team_config_then_fall_back_to_global(self):
        executor = ToolExecutor()
        team_query = MagicMock(first=AsyncMock(return_value=None))
        global_query = MagicMock(
            first=AsyncMock(return_value=SimpleNamespace(credentials={"key": "global"}))
        )

        with patch(
            "app.services.tool.ToolConfig.filter",
            side_effect=[team_query, global_query],
        ) as mock_filter:
            credentials = await executor._get_tool_credentials("weather", UUID(int=1))

        assert credentials == {"key": "global"}
        assert mock_filter.call_args_list[0].kwargs == {
            "tool_name": "weather",
            "team_id": UUID(int=1),
        }
        assert mock_filter.call_args_list[1].kwargs == {
            "tool_name": "weather",
            "team_id": None,
        }

    @pytest.mark.anyio
    async def test_execute_rejects_unknown_tool_type(self):
        tool = MagicMock()
        tool.type = "other"
        tool.team_id = None

        with pytest.raises(ValueError):
            await ToolExecutor().execute(tool, {})
