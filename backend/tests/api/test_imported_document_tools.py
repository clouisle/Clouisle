from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import chat
from app.llm.tools.builtin import register_all_builtin_tools
from app.models.agent import RAGMode


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["fetch_webpage", "markitdown"])
async def test_web_source_can_be_read_without_enabling_user_uploads(tool_name):
    register_all_builtin_tools()
    agent = SimpleNamespace(
        tools_config=[{"type": "builtin", "name": tool_name}],
        enable_attachments=False,
        enable_user_input_request=False,
        enable_memory=False,
        rag_mode=RAGMode.OFF,
        enable_image_generation=False,
        enable_video_generation=False,
    )
    tools = await chat.get_agent_tools(agent)
    names = {tool["function"]["name"] for tool in tools}
    assert {
        tool_name,
        "list_assets",
        "inspect_asset",
        "read_asset",
        "search_asset",
    } <= names
    assert "materialize_asset" not in names
    assert "view_asset" not in names
