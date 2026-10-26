"""Remaining chat tool routing tests against the current authorized dispatcher."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import (
    _get_item_value,
    build_file_content_for_context,
    execute_tool_call,
)
from app.core.i18n import t
from app.llm.tools.interaction import ToolInteractionRequest
from app.schemas.response import BusinessError


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "enable_attachments": True,
        "attachment_config": {},
        "tools_config": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_file_content_disabled_empty_and_legacy_metadata_only():
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
    documents = json.loads(content)["documents"]
    assert documents == [
        {
            "filename": "notes.txt",
            "mime_type": "text/plain",
            "size": 5,
            "reading": (
                "Use list_assets to discover a ref, then read_asset for bounded "
                "lines and search_asset to locate text; continue until eof."
            ),
        }
    ]
    assert "hello" not in content
    assert updates is None


def test_file_and_tool_display_helpers():
    obj = SimpleNamespace(value=3)
    assert _get_item_value({"value": 2}, "value") == 2
    assert _get_item_value(obj, "value") == 3
    assert _get_item_value(obj, "missing", 4) == 4


@pytest.mark.anyio
async def test_stored_mcp_and_custom_require_authorized_context():
    for name in ("mcp_server_action", "custom_fetch"):
        missing = json.loads(await execute_tool_call(name, {}))
        assert missing["error"] == t("user_context_required")

    agent = _agent()
    user = SimpleNamespace(id=uuid4())
    delegated = AsyncMock(return_value={"result": {"ok": True}})
    with patch(
        "app.services.agent_tool_execution.execute_agent_stored_tool", delegated
    ):
        payload = json.loads(
            await execute_tool_call(
                "mcp_server_action", {"x": 1}, agent=agent, user=user
            )
        )
    assert payload == {"result": {"ok": True}}
    assert delegated.await_args.args == (
        agent,
        "mcp_server_action",
        {"x": 1},
        user,
    )

    delegated.side_effect = BusinessError(
        code=403, msg_key="tool_access_denied", status_code=403
    )
    with patch(
        "app.services.agent_tool_execution.execute_agent_stored_tool", delegated
    ):
        denied = json.loads(
            await execute_tool_call("custom_fetch", {}, agent=agent, user=user)
        )
    assert denied["error"] == t("tool_access_denied")

    interaction = ToolInteractionRequest(
        tool_name="mcp_server_action",
        arguments={"interaction_kind": "tool_approval", "execution_id": str(uuid4())},
    )
    delegated.side_effect = None
    delegated.return_value = interaction
    with patch(
        "app.services.agent_tool_execution.execute_agent_stored_tool", delegated
    ):
        result = await execute_tool_call(
            "mcp_server_action", {}, agent=agent, user=user
        )
    assert result is interaction


@pytest.mark.anyio
async def test_builtin_boundary_errors_and_unknown_tool():
    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=None),
        patch("app.llm.tools.tool_registry.get_sandbox_tool_class", return_value=None),
    ):
        unknown = json.loads(await execute_tool_call("absent", {}))
    assert unknown["error"] == t("tool_not_found", tool_name="absent")

    agent = _agent()
    user = SimpleNamespace(id=uuid4())
    tool_info = SimpleNamespace(handler=lambda credentials=None: None)
    cases = [
        (
            BusinessError(code=403, msg_key="tool_access_denied", status_code=403),
            "tool_access_denied",
            t("tool_access_denied"),
        ),
        (RuntimeError("tool secret"), "Unavailable", "Unavailable"),
    ]
    for exc, fallback, expected in cases:
        with (
            patch("app.llm.tools.tool_registry.get_tool", return_value=tool_info),
            patch(
                "app.llm.tools.tool_registry.get_sandbox_tool_class",
                return_value=None,
            ),
            patch(
                "app.services.tool.ToolExecutor.execute_builtin_tool",
                new=AsyncMock(side_effect=exc),
            ),
            patch("app.models.user.User.get_or_none", new=AsyncMock(return_value=user)),
            patch(
                "app.services.error_messages.exception_to_user_message",
                return_value=fallback,
            ),
        ):
            result = json.loads(
                await execute_tool_call("builtin", {}, agent=agent, user=user)
            )
        assert result["error"] == expected
