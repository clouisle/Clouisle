from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import RAGMode


class _FirstQuery:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


def _agent(tools_config, **overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "tools_config": tools_config,
        "enable_user_input_request": True,
        "enable_memory": False,
        "rag_mode": RAGMode.OFF,
        "enable_image_generation": False,
        "enable_video_generation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tool_schema(name):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Run {name}",
            "parameters": {"type": "object"},
        },
    }


@pytest.mark.anyio
async def test_agent_tools_cover_media_dedup_custom_skill_and_mcp(monkeypatch):
    custom_id = uuid4()
    mcp_id = uuid4()
    custom_tool = SimpleNamespace(
        name="weather",
        description="Weather lookup",
        parameters=[
            {"name": "city", "required": True},
            {"name": "units", "type": "number", "description": "Unit code"},
        ],
    )
    mcp_tool = SimpleNamespace(name="remote", mcp_config={"url": "test"})
    filter_tool = Mock(side_effect=[_FirstQuery(custom_tool), _FirstQuery(mcp_tool)])
    monkeypatch.setattr("app.models.tool.Tool.filter", filter_tool)
    monkeypatch.setattr(
        chat.tool_registry,
        "to_openai_tools",
        Mock(side_effect=lambda names: [_tool_schema(name) for name in names]),
    )
    monkeypatch.setattr(
        chat.tool_registry,
        "to_openai_sandbox_tools",
        Mock(return_value=[_tool_schema("read"), _tool_schema("generate_image")]),
    )
    skill = SimpleNamespace(name="analysis")
    monkeypatch.setattr(
        "app.services.skill.SkillService.get_skill_for_team",
        AsyncMock(return_value=skill),
    )
    monkeypatch.setattr(
        "app.services.skill.SkillService.to_tool_info",
        Mock(
            return_value=SimpleNamespace(to_openai_schema=lambda: _tool_schema("skill"))
        ),
    )
    monkeypatch.setattr(
        "app.llm.tools.mcp_client.list_mcp_tools",
        AsyncMock(
            return_value=[
                SimpleNamespace(name="ping", description=None, parameters=None)
            ]
        ),
    )
    agent = _agent(
        [
            {"type": "builtin", "name": "generate_image"},
            {"type": "builtin"},
            {"type": "custom", "tool_id": str(custom_id)},
            {"type": "skill", "skill_id": "skill-id"},
            {"type": "mcp", "server_id": str(mcp_id)},
        ],
        enable_image_generation=True,
        enable_video_generation=True,
    )

    tools = await chat.get_agent_tools(agent)
    by_name = {tool["function"]["name"]: tool for tool in tools}

    assert [tool["function"]["name"] for tool in tools].count("generate_image") == 1
    assert {
        "generate_video",
        "custom_weather",
        "skill",
        "read",
        "mcp_remote_ping",
    } <= set(by_name)
    assert by_name["custom_weather"]["function"]["parameters"] == {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": ""},
            "units": {"type": "number", "description": "Unit code"},
        },
        "required": ["city"],
    }
    assert by_name["mcp_remote_ping"]["function"]["description"] == "MCP tool: ping"
    assert by_name["mcp_remote_ping"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }


@pytest.mark.anyio
async def test_agent_tools_skip_unavailable_optional_sources(monkeypatch):
    query = _FirstQuery(SimpleNamespace(name="remote", mcp_config={"url": "test"}))
    monkeypatch.setattr("app.models.tool.Tool.filter", Mock(return_value=query))
    monkeypatch.setattr(
        "app.services.skill.SkillService.get_skill_for_team",
        AsyncMock(side_effect=RuntimeError("skill offline")),
    )
    monkeypatch.setattr(
        "app.llm.tools.mcp_client.list_mcp_tools",
        AsyncMock(side_effect=RuntimeError("mcp offline")),
    )
    agent = _agent(
        [
            {"type": "custom"},
            {"type": "skill", "skill_id": "missing"},
            {"type": "mcp", "tool_id": "remote"},
        ]
    )

    assert [tool["function"]["name"] for tool in await chat.get_agent_tools(agent)] == [
        "ask_user"
    ]


@pytest.mark.anyio
async def test_tool_display_names_cover_media_builtin_custom_skill_and_mcp(monkeypatch):
    custom_tool = SimpleNamespace(name="weather", display_name="Weather")
    mcp_tool = SimpleNamespace(
        name="remote", display_name="Remote Server", mcp_config={"url": "test"}
    )
    monkeypatch.setattr(
        "app.models.tool.Tool.filter",
        Mock(side_effect=[_FirstQuery(custom_tool), _FirstQuery(mcp_tool)]),
    )
    monkeypatch.setattr(
        "app.services.skill.SkillService.get_skill_for_team",
        AsyncMock(
            return_value=SimpleNamespace(name="analysis", display_name="Analysis")
        ),
    )
    monkeypatch.setattr(
        "app.services.skill.SkillService.build_tool_name",
        Mock(return_value="skill_analysis"),
    )
    monkeypatch.setattr(
        "app.llm.tools.mcp_client.list_mcp_tools",
        AsyncMock(return_value=[SimpleNamespace(name="ping")]),
    )
    monkeypatch.setattr(
        "app.schemas.tool.BUILTIN_TOOLS_METADATA",
        {
            "generate_image": {"display_name_key": "image.key"},
            "generate_video": {},
            "clock": {"display_name": "Clock"},
        },
    )
    monkeypatch.setattr(
        "app.core.i18n.t", Mock(side_effect=lambda key, lang=None: f"{lang}:{key}")
    )
    agent = _agent(
        [
            {"type": "builtin", "name": "clock"},
            {"type": "builtin", "name": "unknown"},
            {"type": "custom", "tool_id": "custom"},
            {"type": "skill", "skill_id": "skill"},
            {"type": "mcp", "server_id": "mcp"},
        ],
        enable_image_generation=True,
        enable_video_generation=True,
    )

    names = await chat.get_tool_display_names(agent, "en")

    assert names == {
        "ask_user": "Ask user",
        "generate_image": "en:image.key",
        "generate_video": "generate_video",
        "clock": "Clock",
        "unknown": "unknown",
        "custom_weather": "Weather",
        "skill_analysis": "Analysis",
        "mcp_remote_ping": "Remote Server/ping",
    }
