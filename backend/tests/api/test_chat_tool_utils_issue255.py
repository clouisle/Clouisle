from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_helpers import tool_utils


@pytest.mark.anyio
async def test_get_agent_tools_handles_empty_configuration(monkeypatch):
    agent = SimpleNamespace(tools_config=None)
    get_skills = AsyncMock(return_value=[])
    monkeypatch.setattr(tool_utils.SkillService, "get_agent_skills", get_skills)
    monkeypatch.setattr(
        tool_utils.Tool,
        "filter",
        Mock(side_effect=AssertionError("empty IDs must not query tools")),
    )

    assert await tool_utils.get_agent_tools(agent) == []
    get_skills.assert_awaited_once_with(agent, enabled_only=True)


@pytest.mark.anyio
async def test_get_agent_tools_combines_tools_skills_and_unique_sandbox_tools(
    monkeypatch,
):
    tool_id = uuid4()
    db_tool = SimpleNamespace(
        id=tool_id,
        name="custom",
        description="Custom tool",
        parameters={"type": "object"},
        type="api",
    )
    query = SimpleNamespace(all=AsyncMock(return_value=[db_tool]))
    filter_mock = Mock(return_value=query)
    skill = SimpleNamespace(
        id=uuid4(),
        description="Skill tool",
        input_schema={"type": "object", "properties": {}},
    )
    get_skills = AsyncMock(return_value=[(skill, {})])
    sandbox_infos = [
        SimpleNamespace(
            name="custom",
            description="Duplicate",
            parameters_schema={},
        ),
        SimpleNamespace(
            name="read",
            description="Read files",
            parameters_schema={"type": "object"},
        ),
    ]
    sandbox_mock = Mock(return_value=sandbox_infos)
    monkeypatch.setattr(tool_utils.Tool, "filter", filter_mock)
    monkeypatch.setattr(tool_utils.SkillService, "get_agent_skills", get_skills)
    monkeypatch.setattr(
        tool_utils.SkillService, "build_tool_name", Mock(return_value="skill_demo")
    )
    monkeypatch.setattr(
        tool_utils.tool_registry, "get_sandbox_tool_infos", sandbox_mock
    )
    agent = SimpleNamespace(
        tools_config=[
            {"tool_id": str(tool_id)},
            {"tool_id": str(uuid4())},
            {"name": "ignored"},
        ]
    )

    assert await tool_utils.get_agent_tools(agent) == [
        {
            "id": tool_id,
            "name": "custom",
            "description": "Custom tool",
            "parameters": {"type": "object"},
            "type": "api",
        },
        {
            "id": skill.id,
            "name": "skill_demo",
            "description": "Skill tool",
            "parameters": {"type": "object", "properties": {}},
            "type": "skill",
        },
        {
            "id": "read",
            "name": "read",
            "description": "Read files",
            "parameters": {"type": "object"},
            "type": "builtin",
        },
    ]
    filter_mock.assert_called_once_with(
        id__in=[str(tool_id), agent.tools_config[1]["tool_id"]], is_enabled=True
    )
    sandbox_mock.assert_called_once_with(["read", "edit", "write", "bash"])


@pytest.mark.anyio
async def test_get_tool_display_names_covers_builtin_custom_and_skill_sources(
    monkeypatch,
):
    tool_id = uuid4()
    db_tool = SimpleNamespace(id=tool_id, name="custom", display_name="Custom Display")
    query = SimpleNamespace(all=AsyncMock(return_value=[db_tool]))
    filter_mock = Mock(return_value=query)
    skill = SimpleNamespace(display_name="Skill Display")
    translate = Mock(
        side_effect=lambda key, **_kwargs: {
            "asset_tool_inspect": "Inspect Attachment",
            "asset_tool_read": "Read Attachment",
            "asset_tool_parse": "Parse Attachment",
            "tools.translated": "Translated Builtin",
        }[key]
    )
    monkeypatch.setattr(tool_utils.Tool, "filter", filter_mock)
    monkeypatch.setattr(
        tool_utils.SkillService,
        "get_agent_skills",
        AsyncMock(return_value=[(skill, {})]),
    )
    monkeypatch.setattr(
        tool_utils.SkillService, "build_tool_name", Mock(return_value="skill_demo")
    )
    monkeypatch.setattr(tool_utils, "t", translate)
    monkeypatch.setitem(
        tool_utils.BUILTIN_TOOLS_METADATA,
        "translated",
        {"display_name_key": "tools.translated"},
    )
    monkeypatch.setitem(
        tool_utils.BUILTIN_TOOLS_METADATA,
        "fallback",
        {"display_name": "Fallback Builtin"},
    )
    agent = SimpleNamespace(
        enable_attachments=True,
        tools_config=[
            {"type": "builtin", "name": "translated"},
            {"type": "builtin", "name": "fallback"},
            {"type": "builtin", "name": "unknown"},
            {"type": "builtin"},
            {"type": "custom", "tool_id": str(tool_id)},
            {"type": "custom", "tool_id": str(uuid4())},
        ],
    )

    assert await tool_utils.get_tool_display_names(agent, "zh-CN") == {
        "inspect_asset": "Inspect Attachment",
        "read_asset": "Read Attachment",
        "parse_asset": "Parse Attachment",
        "translated": "Translated Builtin",
        "fallback": "Fallback Builtin",
        "unknown": "unknown",
        "custom": "Custom Display",
        "skill_demo": "Skill Display",
    }
    assert translate.call_args_list[-1] == call("tools.translated", lang="zh-CN")


@pytest.mark.anyio
async def test_get_tool_display_names_skips_database_query_without_ids(monkeypatch):
    agent = SimpleNamespace(tools_config=[])
    monkeypatch.setattr(
        tool_utils.Tool,
        "filter",
        Mock(side_effect=AssertionError("empty IDs must not query tools")),
    )
    monkeypatch.setattr(
        tool_utils.SkillService, "get_agent_skills", AsyncMock(return_value=[])
    )

    assert await tool_utils.get_tool_display_names(agent) == {}
