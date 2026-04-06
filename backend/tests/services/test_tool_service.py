"""
Tests for the tool execution service.
"""

from unittest.mock import AsyncMock, MagicMock, patch

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
