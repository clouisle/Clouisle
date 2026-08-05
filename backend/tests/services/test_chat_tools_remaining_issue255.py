import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.v1.endpoints.chat_tools import (
    _get_item_value,
    build_file_content_for_context,
    build_file_content_for_prompt,
    execute_code_tool,
    execute_http_tool,
    execute_tool_call,
)
from app.core.i18n import t
from app.models.tool import CustomToolType


def _agent(**overrides):
    values = {
        "id": "agent-1",
        "team_id": "team-1",
        "enable_attachments": True,
        "attachment_config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _query(result):
    return SimpleNamespace(first=AsyncMock(return_value=result))


@pytest.mark.anyio
async def test_file_content_disabled_empty_legacy_and_prompt_wrapper():
    disabled = _agent(enable_attachments=False)
    assert await build_file_content_for_context(disabled, [], [], "en", None, None) == (
        "",
        None,
    )

    agent = _agent()
    assert await build_file_content_for_context(agent, [], [], "en", None, None) == (
        "",
        None,
    )

    legacy = SimpleNamespace(
        filename="notes.txt",
        content="hello",
        mime_type="text/plain",
        size=5,
        truncated=True,
        original_length=10,
    )
    content, updates = await build_file_content_for_context(
        agent, None, [legacy], "en", None, None
    )
    assert "notes.txt" in content and "hello" in content
    assert updates is None

    with patch(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        new=AsyncMock(return_value=("prompt files", [{"cached": True}])),
    ) as build:
        assert (
            await build_file_content_for_prompt(
                agent, [], [legacy], "en", {"http": 1}, "user"
            )
            == "prompt files"
        )
    build.assert_awaited_once()


def test_file_and_tool_display_helpers():
    obj = SimpleNamespace(value=3)
    assert _get_item_value({"value": 2}, "value") == 2
    assert _get_item_value(obj, "value") == 3
    assert _get_item_value(obj, "missing", 4) == 4


@pytest.mark.anyio
async def test_mcp_routes_invalid_missing_success_and_error():
    assert json.loads(await execute_tool_call("mcp_invalid", {}))["error"] == t(
        "invalid_mcp_tool_name"
    )

    with patch("app.models.tool.Tool.filter", return_value=_query(None)):
        missing = json.loads(await execute_tool_call("mcp_server_action", {}))
    assert missing["error"] == t("mcp_tool_missing_configuration", tool_name="server")

    server = SimpleNamespace(mcp_config={"url": "https://mcp.example"})
    result = SimpleNamespace(success=True, result={"ok": True}, error=None)
    with (
        patch("app.models.tool.Tool.filter", return_value=_query(server)),
        patch(
            "app.llm.tools.mcp_client.execute_mcp_tool",
            new=AsyncMock(return_value=result),
        ) as execute,
    ):
        payload = json.loads(
            await execute_tool_call(
                "mcp_server_action", {"x": 1}, tool_timeouts={"mcp": 9}
            )
        )
    assert payload == {"success": True, "result": {"ok": True}, "error": None}
    execute.assert_awaited_once_with(
        mcp_config=server.mcp_config,
        tool_name="action",
        arguments={"x": 1},
        timeout=9,
    )

    with (
        patch("app.models.tool.Tool.filter", return_value=_query(server)),
        patch(
            "app.llm.tools.mcp_client.execute_mcp_tool",
            new=AsyncMock(side_effect=RuntimeError("network secret")),
        ),
        patch(
            "app.services.error_messages.exception_to_user_message",
            return_value="MCP unavailable",
        ),
    ):
        failed = json.loads(await execute_tool_call("mcp_server_action", {}))
    assert failed == {"error": "MCP unavailable"}


@pytest.mark.anyio
async def test_custom_http_routes_success_error_missing_and_unsupported():
    with patch("app.models.tool.Tool.filter", return_value=_query(None)):
        missing = json.loads(await execute_tool_call("custom_missing", {}))
    assert missing["error"] == t("custom_tool_not_found")

    http_tool = SimpleNamespace(
        custom_type=CustomToolType.HTTP,
        http_config={"url": "https://example.com"},
        credentials={"token": "x"},
    )
    with (
        patch("app.models.tool.Tool.filter", return_value=_query(http_tool)),
        patch(
            "app.llm.tools.executors.execute_http_tool",
            new=AsyncMock(return_value={"success": True, "result": {"ok": True}}),
        ) as execute,
        patch(
            "app.llm.tools.executors.format_http_result_for_llm",
            return_value="formatted",
        ),
    ):
        payload = json.loads(
            await execute_tool_call(
                "custom_fetch", {"q": "x"}, tool_timeouts={"http": 7}
            )
        )
    assert payload["llm_result"] == "formatted"
    execute.assert_awaited_once_with(
        http_config=http_tool.http_config,
        arguments={"q": "x"},
        credentials=http_tool.credentials,
        timeout=7,
    )

    with (
        patch("app.models.tool.Tool.filter", return_value=_query(http_tool)),
        patch(
            "app.llm.tools.executors.execute_http_tool",
            new=AsyncMock(side_effect=RuntimeError("network secret")),
        ),
        patch(
            "app.services.error_messages.exception_to_user_message",
            return_value="HTTP unavailable",
        ),
    ):
        assert json.loads(await execute_tool_call("custom_fetch", {})) == {
            "error": "HTTP unavailable"
        }

    unsupported = SimpleNamespace(custom_type="other")
    with patch("app.models.tool.Tool.filter", return_value=_query(unsupported)):
        payload = json.loads(await execute_tool_call("custom_other", {}))
    assert payload["error"] == t("unsupported_tool_type")


@pytest.mark.anyio
async def test_download_builtin_and_unknown_route_errors():
    with (
        patch(
            "app.llm.tools.executors.execute_http_tool",
            new=AsyncMock(return_value={"success": True, "result": "body"}),
        ) as execute,
        patch(
            "app.llm.tools.executors.format_http_result_for_llm",
            return_value="downloaded",
        ),
    ):
        payload = json.loads(
            await execute_tool_call(
                "file_download",
                {"url": "https://example.com/file"},
                tool_timeouts={"download": 8},
            )
        )
    assert payload["llm_result"] == "downloaded"
    execute.assert_awaited_once_with(
        http_config={"url": "https://example.com/file", "method": "GET"},
        arguments={},
        timeout=8,
    )

    with (
        patch(
            "app.llm.tools.executors.execute_http_tool",
            new=AsyncMock(side_effect=RuntimeError("download secret")),
        ),
        patch(
            "app.services.error_messages.exception_to_user_message",
            return_value="Download unavailable",
        ),
    ):
        assert json.loads(await execute_tool_call("file_download", {})) == {
            "error": "Download unavailable"
        }

    handler = AsyncMock()
    tool_info = SimpleNamespace(handler=handler)
    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=tool_info),
        patch("app.llm.tools.tool_registry.get_sandbox_tool_class", return_value=None),
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(side_effect=RuntimeError("tool secret")),
        ),
        patch(
            "app.services.error_messages.exception_to_user_message",
            return_value="Tool unavailable",
        ),
    ):
        assert json.loads(await execute_tool_call("builtin", {})) == {
            "error": "Tool unavailable"
        }

    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=None),
        patch("app.llm.tools.tool_registry.get_sandbox_tool_class", return_value=None),
    ):
        unknown = json.loads(await execute_tool_call("absent", {}))
    assert unknown["error"] == t("tool_not_found", tool_name="absent")


@pytest.mark.anyio
async def test_standalone_http_and_code_helpers():
    tool = SimpleNamespace(
        http_config={"url": "https://example.com"},
        credentials={"key": "value"},
        code_config={},
    )
    with (
        patch(
            "app.llm.tools.executors.execute_http_tool",
            new=AsyncMock(return_value={"result": "ok"}),
        ) as execute,
        patch(
            "app.llm.tools.executors.format_http_result_for_llm",
            return_value="ok",
        ),
    ):
        assert await execute_http_tool(tool, {"q": 1}, timeout=2) == "ok"
    execute.assert_awaited_once_with(
        http_config=tool.http_config,
        arguments={"q": 1},
        credentials=tool.credentials,
        timeout=2,
    )
    assert json.loads(await execute_code_tool(tool, {}))["error"] == t(
        "tool_code_not_defined"
    )

    tool.code_config = {"language": "python", "code": "return 1"}
    with patch(
        "app.llm.tools.sandbox.execute_code",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True, result=1, stdout="log", error=None
            )
        ),
    ):
        assert json.loads(await execute_code_tool(tool, {})) == {
            "value": 1,
            "__logs__": "log",
        }

    with patch(
        "app.llm.tools.sandbox.execute_code",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=False, result=None, stdout="trace", error=None
            )
        ),
    ):
        failed = json.loads(await execute_code_tool(tool, {}))
    assert failed == {"error": t("code_execution_failed"), "logs": "trace"}

    with (
        patch(
            "app.llm.tools.sandbox.execute_code",
            new=AsyncMock(side_effect=RuntimeError("sandbox secret")),
        ),
        patch(
            "app.services.error_messages.exception_to_user_message",
            return_value="Code unavailable",
        ),
    ):
        assert json.loads(await execute_code_tool(tool, {})) == {
            "error": "Code unavailable"
        }
