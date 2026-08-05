import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_helpers.general import (
    _safe_json_loads,
    collect_conversation_images,
    parse_user_input_request,
)
from app.api.v1.endpoints.chat_tools import (
    _get_builtin_tool_credentials,
    build_file_content_for_context,
    execute_code_tool,
    execute_tool_call,
)


def test_safe_json_loads_returns_none_for_empty_value_issue255():
    assert _safe_json_loads("") is None


@pytest.mark.parametrize(
    "content",
    [
        "ordinary response",
        """<user_input_request>
        <question>   </question>
        <options><option>Yes</option><option>No</option></options>
        </user_input_request>""",
        """<user_input_request>
        <question>Choose</question>
        <options><option>Only one</option></options>
        </user_input_request>""",
    ],
)
def test_parse_user_input_request_rejects_residual_invalid_shapes_issue255(content):
    assert parse_user_input_request(content) == (None, content)


def test_collect_conversation_images_filters_residual_sources_issue255():
    messages = [
        SimpleNamespace(
            id=uuid4(),
            role="user",
            content="uploaded",
            images=[{}, {"url": "uploaded.png"}],
        ),
        SimpleNamespace(id=uuid4(), role="assistant", content="ignored"),
    ]

    images, inventory = collect_conversation_images(
        messages,
        current_message_id=uuid4(),
        current_images=[{}, {"base64": "current"}],
    )

    assert images == [{"url": "uploaded.png"}, {"base64": "current"}]
    assert inventory == [
        {"origin": "uploaded", "context": "uploaded"},
        {"origin": "uploaded", "context": "current message"},
    ]


@pytest.mark.anyio
async def test_knowledge_search_requires_agent_context_issue255():
    result = json.loads(await execute_tool_call("knowledge_search", {"query": "x"}))

    assert result["error"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("api_key", "expected"),
    [("fallback-key", {"TAVILY_API_KEY": "fallback-key"}), ("", {})],
)
async def test_builtin_credentials_cover_tavily_setting_fallback_issue255(
    api_key, expected
):
    query = MagicMock()
    query.first = AsyncMock(return_value=None)

    with (
        patch("app.models.tool_config.ToolConfig.filter", return_value=query),
        patch("app.core.config.settings.TAVILY_API_KEY", api_key),
    ):
        credentials = await _get_builtin_tool_credentials("web_search", agent=None)

    assert credentials == expected
    query.first.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("stdout", ["", "sandbox log"])
async def test_execute_code_tool_shapes_dict_stdout_residuals_issue255(stdout):
    tool = SimpleNamespace(code_config={"language": "python", "code": "return value"})
    execute_code = AsyncMock(
        return_value=SimpleNamespace(success=True, result={"value": 1}, stdout=stdout)
    )

    with patch("app.llm.tools.sandbox.execute_code", execute_code):
        result = json.loads(await execute_code_tool(tool, {}))

    expected = {"value": 1}
    if stdout:
        expected["__logs__"] = stdout
    assert result == expected


@pytest.mark.anyio
async def test_custom_file_parser_without_tool_id_skips_lookup_issue255():
    agent = SimpleNamespace(
        enable_attachments=True,
        attachment_config={"parser": {"type": "custom"}},
    )

    result = await build_file_content_for_context(
        agent=agent,
        file_urls=[{"url": "https://example.test/file.txt"}],
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=None,
    )

    assert result == ("", None)


@pytest.mark.anyio
async def test_custom_file_parser_config_is_ignored_for_asset_files_issue255():
    agent = SimpleNamespace(
        enable_attachments=True,
        attachment_config={"parser": {"type": "custom", "tool_id": "parser-tool-id"}},
    )

    with (
        patch(
            "app.api.v1.endpoints.chat_tools.execute_tool_call",
            new=AsyncMock(),
        ) as execute_parser,
    ):
        result = await build_file_content_for_context(
            agent=agent,
            file_urls=[{"url": "https://example.test/file.txt"}],
            legacy_files=None,
            user_locale="en",
            tool_timeouts=None,
            user=None,
        )

    assert result == ("", None)
    execute_parser.assert_not_awaited()
