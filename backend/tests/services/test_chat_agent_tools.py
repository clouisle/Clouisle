from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat import get_agent_tools
from app.llm.tools.builtin import register_all_builtin_tools
from app.models.agent import RAGMode


def _agent(tools_config):
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        tools_config=tools_config,
        enable_memory=False,
        rag_mode=RAGMode.OFF,
        enable_image_generation=False,
        enable_video_generation=False,
    )


@pytest.mark.anyio
async def test_skill_selection_exposes_sandbox_tools():
    register_all_builtin_tools()
    skill = SimpleNamespace(
        id=uuid4(),
        name="demo_skill",
        display_name="Demo Skill",
        description="Run demo skill",
        input_schema={"type": "object", "properties": {}},
    )
    agent = _agent([{"type": "skill", "skill_id": str(skill.id)}])

    with patch(
        "app.services.skill.SkillService.get_skill_for_team",
        new=AsyncMock(return_value=skill),
    ):
        tools = await get_agent_tools(agent)

    names = {tool["function"]["name"] for tool in tools}
    assert any(name.startswith("skill_demo_skill_") for name in names)
    assert {"bash", "read", "write"}.issubset(names)


@pytest.mark.anyio
async def test_selected_sandbox_builtin_tools_are_exposed_independently():
    register_all_builtin_tools()
    agent = _agent(
        [
            {"type": "builtin", "name": "bash"},
            {"type": "builtin", "name": "read"},
        ]
    )

    tools = await get_agent_tools(agent)

    names = {tool["function"]["name"] for tool in tools}
    assert {"bash", "read"}.issubset(names)
    assert "write" not in names
