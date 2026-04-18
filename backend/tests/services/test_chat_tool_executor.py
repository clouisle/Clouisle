import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.chat_helpers.tool_executor import execute_code_tool


class TestChatToolExecutor:
    @pytest.mark.anyio
    async def test_execute_code_tool_routes_through_sandbox_gateway(self):
        tool = MagicMock()
        tool.code_config = {
            "language": "python",
            "code": "return {'value': 42}",
            "python_packages": ["requests==2.32.3"],
            "python_package_index_url": " https://mirror.example.com/simple/ ",
        }

        with (
            patch(
                "app.api.v1.endpoints.chat_helpers.tool_executor.compile_code_config_job",
                return_value=SimpleNamespace(
                    limits=SimpleNamespace(timeout_seconds=60.0),
                ),
            ) as mock_compile,
            patch(
                "app.api.v1.endpoints.chat_helpers.tool_executor.sandbox_gateway.submit_and_wait",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        success=True,
                        result={"value": 42},
                        error=None,
                        stdout="hello",
                        stderr="",
                    )
                ),
            ) as mock_submit,
        ):
            payload = await execute_code_tool(tool, {"x": 1}, timeout=60.0)

        data = json.loads(payload)
        assert data["success"] is True
        assert data["result"] == {"value": 42}
        assert data["stdout"] == "hello"
        mock_compile.assert_called_once()
        mock_submit.assert_awaited_once()
