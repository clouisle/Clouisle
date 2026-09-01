import builtins
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from app.llm.types import ToolCall
from app.models.agent import RAGMode

builtins.ToolCall = ToolCall
try:
    AgentService = import_module("app.services.agent").AgentService
finally:
    del builtins.ToolCall


def _agent(**overrides):
    values = {
        "id": "agent-1",
        "team_id": None,
        "model_id": None,
        "system_prompt": None,
        "tools_config": [],
        "enable_image_generation": False,
        "enable_video_generation": False,
        "rag_mode": RAGMode.OFF,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_chat_zero_turns_returns_empty_result_without_calling_model():
    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])

    with patch("app.services.agent.model_manager.chat", new=AsyncMock()) as chat:
        result = await service.chat(_agent(), "question", max_turns=0)

    assert result == {
        "response": "",
        "tool_calls": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "dialogue": [],
        "artifacts": [],
    }
    chat.assert_not_awaited()


@pytest.mark.anyio
async def test_get_agent_tools_skips_missing_and_failed_definitions():
    service = AgentService()
    agent = _agent(
        team_id="team-1",
        tools_config=[
            {"type": "builtin", "name": "missing"},
            {"type": "skill", "skill_id": "skill-1"},
            {"type": "skill"},
            {"type": "mcp"},
        ],
        enable_image_generation=True,
        enable_video_generation=True,
    )

    with (
        patch.object(service, "_get_builtin_tool", return_value=None),
        patch(
            "app.services.skill.SkillService.get_skill_for_team",
            new=AsyncMock(side_effect=RuntimeError("unavailable")),
        ) as get_skill,
    ):
        tools = await service._get_agent_tools(agent)

    assert tools == []
    get_skill.assert_awaited_once_with("skill-1", "team-1", enabled_only=True)


@pytest.mark.anyio
async def test_execute_tool_falls_back_from_team_to_global_credentials():
    service = AgentService()
    agent = _agent(team_id="team-1")
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="search", arguments={"query": "docs"}),
    )
    queries = [
        SimpleNamespace(first=AsyncMock(return_value=None)),
        SimpleNamespace(
            first=AsyncMock(
                return_value=SimpleNamespace(credentials={"token": "global"})
            )
        ),
    ]

    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=object()),
        patch(
            "app.models.tool_config.ToolConfig.filter", side_effect=queries
        ) as filter_,
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(return_value={"ok": True}),
        ) as execute,
    ):
        result = await service._execute_tool(agent, tool_call)

    assert result == {"ok": True}
    assert filter_.call_args_list == [
        call(tool_name="search", team_id="team-1"),
        call(tool_name="search", team_id=None),
    ]
    execute.assert_awaited_once_with(
        name="search",
        arguments={"query": "docs"},
        credentials={"token": "global"},
        agent=agent,
        team_id="team-1",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("links", [[], [SimpleNamespace(knowledge_base=None)]])
async def test_retrieve_rag_context_returns_none_without_searchable_chunks(links):
    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return links

            return resolve().__await__()

    service = AgentService()
    with (
        patch("app.services.agent.AgentKnowledgeBase.filter", return_value=Query()),
        patch("app.services.vector_store.VectorStore") as vector_store,
    ):
        result = await service._retrieve_rag_context(_agent(), "question")

    assert result is None
    vector_store.assert_not_called()
