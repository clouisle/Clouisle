from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat import get_agent_tools, get_tool_display_names
from app.models.agent import RAGMode


def _agent(tools_config, **overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "tools_config": tools_config,
        "enable_memory": False,
        "memory_config": {},
        "rag_mode": RAGMode.OFF,
        "enable_image_generation": False,
        "enable_video_generation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _query_result(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.anyio
async def test_get_agent_tools_combines_memory_rag_media_builtin_and_custom_tools():
    agent = _agent(
        [
            {"type": "builtin", "name": "generate_image"},
            {"type": "custom", "tool_id": "custom-id"},
            {"type": "custom"},
            {"type": "unknown"},
        ],
        enable_memory=True,
        memory_config={"auto_extract": False},
        rag_mode=RAGMode.AGENTIC,
        enable_image_generation=True,
        enable_video_generation=True,
    )
    memory_tools = [
        {
            "name": "create_memory_entity",
            "description": "create",
            "input_schema": {"type": "object"},
        },
        {
            "name": "search_memory",
            "description": "search",
            "input_schema": {"type": "object"},
        },
    ]
    knowledge_base = SimpleNamespace(name="Handbook", description="Policies")
    custom_tool = SimpleNamespace(
        name="weather",
        description="Forecast",
        parameters=[
            {"name": "city", "required": True},
            {"name": "days", "type": "integer", "description": "Count"},
        ],
    )

    def media_schema(name):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": name,
                "parameters": {"type": "object"},
            },
        }

    kb_query = MagicMock()
    kb_query.prefetch_related = AsyncMock(
        return_value=[SimpleNamespace(knowledge_base=knowledge_base)]
    )

    with (
        patch("app.llm.tools.memory_tools.get_memory_tools", return_value=memory_tools),
        patch(
            "app.api.v1.endpoints.chat.AgentKnowledgeBase.filter",
            return_value=kb_query,
        ),
        patch(
            "app.api.v1.endpoints.chat.tool_registry.to_openai_tools",
            side_effect=lambda names: [media_schema(names[0])],
        ),
        patch(
            "app.api.v1.endpoints.chat.tool_registry.to_openai_sandbox_tools",
            return_value=[],
        ),
        patch("app.models.tool.Tool.filter", return_value=_query_result(custom_tool)),
    ):
        tools = await get_agent_tools(agent)

    by_name = {tool["function"]["name"]: tool for tool in tools}
    assert set(by_name) == {
        "search_memory",
        "knowledge_search",
        "generate_image",
        "generate_video",
        "custom_weather",
    }
    assert "Handbook" in by_name["knowledge_search"]["function"]["description"]
    assert by_name["custom_weather"]["function"]["parameters"] == {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": ""},
            "days": {"type": "integer", "description": "Count"},
        },
        "required": ["city"],
    }


@pytest.mark.anyio
async def test_get_agent_tools_handles_skill_and_mcp_success_and_failures():
    agent = _agent(
        [
            {"type": "skill", "skill_id": "good-skill"},
            {"type": "skill", "skill_id": "bad-skill"},
            {"type": "mcp", "server_id": "good-mcp"},
            {"type": "mcp", "tool_id": "bad-mcp"},
        ]
    )
    skill_schema = {
        "type": "function",
        "function": {
            "name": "skill_research",
            "description": "Research",
            "parameters": {"type": "object"},
        },
    }
    skill_info = MagicMock()
    skill_info.to_openai_schema.return_value = skill_schema
    mcp_tool = SimpleNamespace(
        name="docs", mcp_config={"url": "https://unused.example"}
    )
    mcp_result = SimpleNamespace(name="lookup", description=None, parameters=None)

    with (
        patch(
            "app.services.skill.SkillService.get_skill_for_team",
            new=AsyncMock(side_effect=[SimpleNamespace(), RuntimeError("disabled")]),
        ),
        patch("app.services.skill.SkillService.to_tool_info", return_value=skill_info),
        patch(
            "app.api.v1.endpoints.chat.tool_registry.to_openai_sandbox_tools",
            return_value=[skill_schema],
        ),
        patch(
            "app.models.tool.Tool.filter",
            side_effect=[_query_result(mcp_tool), _query_result(mcp_tool)],
        ),
        patch(
            "app.llm.tools.mcp_client.list_mcp_tools",
            new=AsyncMock(side_effect=[[mcp_result], RuntimeError("offline")]),
        ),
    ):
        tools = await get_agent_tools(agent)

    assert [tool["function"]["name"] for tool in tools] == [
        "skill_research",
        "mcp_docs_lookup",
    ]
    assert tools[1]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }


@pytest.mark.anyio
async def test_get_tool_display_names_covers_every_configured_tool_kind():
    agent = _agent(
        [
            {"type": "builtin", "name": "get_current_time"},
            {"type": "builtin", "name": "unlisted"},
            {"type": "custom", "tool_id": "custom-id"},
            {"type": "skill", "skill_id": "skill-id"},
            {"type": "mcp", "server_id": "mcp-id"},
        ],
        enable_memory=True,
        rag_mode=RAGMode.AGENTIC,
        enable_image_generation=True,
        enable_video_generation=True,
    )
    custom_tool = SimpleNamespace(name="weather", display_name="Weather")
    skill = SimpleNamespace(display_name="Research")
    mcp_tool = SimpleNamespace(
        name="docs", display_name="Docs", mcp_config={"url": "unused"}
    )

    with (
        patch("app.api.v1.endpoints.chat.AgentKnowledgeBase.filter") as kb_filter,
        patch(
            "app.models.tool.Tool.filter",
            side_effect=[_query_result(custom_tool), _query_result(mcp_tool)],
        ),
        patch(
            "app.services.skill.SkillService.get_skill_for_team",
            new=AsyncMock(return_value=skill),
        ),
        patch(
            "app.services.skill.SkillService.build_tool_name",
            return_value="skill_research",
        ),
        patch(
            "app.llm.tools.mcp_client.list_mcp_tools",
            new=AsyncMock(return_value=[SimpleNamespace(name="lookup")]),
        ),
    ):
        kb_filter.return_value.count = AsyncMock(return_value=1)
        names = await get_tool_display_names(agent, "en")

    assert names["knowledge_search"]
    assert names["search_memory"]
    assert names["generate_image"]
    assert names["generate_video"]
    assert names["get_current_time"]
    assert names["unlisted"] == "unlisted"
    assert names["custom_weather"] == "Weather"
    assert names["skill_research"] == "Research"
    assert names["mcp_docs_lookup"] == "Docs/lookup"


@pytest.mark.anyio
async def test_get_tool_display_names_ignores_unavailable_skill_and_mcp():
    agent = _agent(
        [
            {"type": "skill", "skill_id": "missing"},
            {"type": "skill"},
            {"type": "mcp", "server_id": "offline"},
            {"type": "mcp"},
            {"type": "custom"},
        ]
    )
    mcp_tool = SimpleNamespace(name="docs", mcp_config={"url": "unused"})

    with (
        patch(
            "app.services.skill.SkillService.get_skill_for_team",
            new=AsyncMock(side_effect=RuntimeError("missing")),
        ),
        patch("app.models.tool.Tool.filter", return_value=_query_result(mcp_tool)),
        patch(
            "app.llm.tools.mcp_client.list_mcp_tools",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
    ):
        names = await get_tool_display_names(agent, "en")

    assert names == {}
