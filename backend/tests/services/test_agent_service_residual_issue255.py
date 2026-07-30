import builtins
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.types.chat import ToolCall
from app.models.agent import RAGMode

builtins.ToolCall = ToolCall
from app.services.agent import AgentService  # noqa: E402

del builtins.ToolCall


def agent(**overrides):
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
async def test_build_messages_covers_context_history_and_rag():
    service = AgentService()
    service._retrieve_rag_context = AsyncMock(return_value="retrieved")

    messages = await service._build_messages(
        agent(system_prompt="rules", rag_mode=RAGMode.AUTO),
        "current",
        context={"tenant": "acme"},
        conversation_history=[
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "system", "content": "s"},
            {"role": "ignored", "content": "x"},
        ],
    )

    assert [message.content for message in messages] == [
        "rules\n\nContext:\n- tenant: acme",
        "u",
        "a",
        "s",
        "Relevant context:\nretrieved",
        "current",
    ]


@pytest.mark.anyio
async def test_get_agent_tools_covers_configs_media_and_agentic_rag():
    service = AgentService()
    service._get_builtin_tool = MagicMock(
        side_effect=lambda name: None if name == "missing" else MagicMock(name=name)
    )
    skill_definition = MagicMock()

    with patch("app.services.skill.SkillService") as skill_service:
        skill_service.get_skill_for_team = AsyncMock(
            side_effect=[MagicMock(), RuntimeError("disabled")]
        )
        skill_service.to_tool_definition.return_value = skill_definition
        tools = await service._get_agent_tools(
            agent(
                team_id="team-1",
                tools_config=[
                    {"type": "builtin", "name": "missing"},
                    {"type": "builtin", "name": "web_search"},
                    {"type": "skill", "skill_id": "skill-1"},
                    {"type": "skill", "skill_id": "skill-2"},
                    {"type": "skill"},
                    {"type": "mcp"},
                ],
                enable_image_generation=True,
                enable_video_generation=True,
                rag_mode=RAGMode.AGENTIC,
            )
        )

    assert skill_definition in tools
    assert tools[-1].function.name == "search_knowledge_base"
    assert service._get_builtin_tool.call_args_list[-2].args == ("generate_image",)
    assert service._get_builtin_tool.call_args_list[-1].args == ("generate_video",)


@pytest.mark.anyio
async def test_retrieve_rag_context_sorts_results_and_skips_missing_kb():
    service = AgentService()
    bindings = [
        SimpleNamespace(knowledge_base=None),
        SimpleNamespace(
            knowledge_base=SimpleNamespace(
                id="kb-1",
                name="Docs",
                embedding_model_id=None,
                rerank_model_id=None,
                team_id="team-1",
                status="active",
                settings=None,
            ),
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.1,
        ),
    ]
    query = MagicMock()
    query.prefetch_related = AsyncMock(return_value=bindings)

    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {"kb_name": "Docs", "content": "high", "score": 0.9},
                {"kb_name": "Docs", "content": "low", "score": 0.2},
            )
        )
    )
    with (
        patch("app.services.agent.AgentKnowledgeBase.filter", return_value=query),
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        result = await service._retrieve_rag_context(agent(), "query")

    assert result == "[Docs] high\n\n[Docs] low"
    assert retrieve.await_args.args[0].targets[0].kb_id == "kb-1"


@pytest.mark.anyio
async def test_retrieve_rag_context_handles_empty_and_failure():
    service = AgentService()
    empty_query = MagicMock()
    empty_query.prefetch_related = AsyncMock(return_value=[])
    failed_query = MagicMock()
    failed_query.prefetch_related = AsyncMock(
        side_effect=RuntimeError("db unavailable")
    )

    with patch(
        "app.services.agent.AgentKnowledgeBase.filter",
        side_effect=[empty_query, failed_query],
    ):
        assert await service._retrieve_rag_context(agent(), "empty") is None
        assert await service._retrieve_rag_context(agent(), "failed") is None
