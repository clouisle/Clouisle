import importlib
import typing
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import FunctionDefinition, ToolDefinition
from app.models.agent import RAGMode

typing.TYPE_CHECKING = True
AgentService = importlib.import_module("app.services.agent").AgentService
typing.TYPE_CHECKING = False


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": None,
        "model_id": None,
        "system_prompt": "",
        "tools_config": [],
        "enable_image_generation": False,
        "enable_video_generation": False,
        "rag_mode": RAGMode.OFF,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        type="function",
        function=FunctionDefinition(
            name=name,
            description=name,
            parameters={"type": "object", "properties": {}},
        ),
    )


@pytest.mark.anyio
async def test_agent_service_build_messages_covers_context_history_and_rag(monkeypatch):
    service = AgentService()
    monkeypatch.setattr(
        service,
        "_retrieve_rag_context",
        AsyncMock(return_value="retrieved text"),
    )

    messages = await service._build_messages(
        agent=_agent(system_prompt="Instructions", rag_mode=RAGMode.AUTO),
        message="current",
        context={"account": "demo"},
        conversation_history=[
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
            {"role": "system", "content": "override"},
            {"role": "ignored", "content": "skip"},
        ],
    )

    assert [message.role.value for message in messages] == [
        "system",
        "user",
        "assistant",
        "system",
        "system",
        "user",
    ]
    assert "- account: demo" in messages[0].content
    assert messages[-2].content == "Relevant context:\nretrieved text"


@pytest.mark.anyio
async def test_agent_service_get_tools_skips_missing_and_failed_tools(monkeypatch):
    service = AgentService()
    monkeypatch.setattr(
        service,
        "_get_builtin_tool",
        lambda name: None if name in {"missing", "generate_image"} else _tool(name),
    )

    from app.services.skill import SkillService

    monkeypatch.setattr(
        SkillService,
        "get_skill_for_team",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    tools = await service._get_agent_tools(
        _agent(
            tools_config=[
                {"type": "builtin", "name": "missing"},
                {"type": "skill", "skill_id": "skill-id"},
                {"type": "skill"},
                {"type": "mcp"},
            ],
            enable_image_generation=True,
            enable_video_generation=True,
            rag_mode=RAGMode.AGENTIC,
        )
    )

    assert [tool.function.name for tool in tools] == [
        "generate_video",
        "search_knowledge_base",
    ]


@pytest.mark.anyio
async def test_agent_service_retrieve_rag_context_sorts_and_skips_empty_kb(
    monkeypatch,
):
    service = AgentService()
    knowledge_base = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=uuid4(),
        status="active",
        settings=None,
    )
    links = [
        SimpleNamespace(knowledge_base=None),
        SimpleNamespace(
            knowledge_base=knowledge_base,
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.2,
        ),
    ]

    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return links

            return resolve().__await__()

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter", lambda **_kwargs: Query()
    )

    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {"kb_name": "Docs", "content": "high", "score": 0.9},
                {"kb_name": "Docs", "content": "low", "score": 0.1},
            )
        )
    )
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)

    result = await service._retrieve_rag_context(_agent(), "query")

    assert result == "[Docs] high\n\n[Docs] low"
    request = retrieve.await_args.args[0]
    assert request.query == "query"
    assert request.top_k == 10
    assert request.targets[0].kb_id == knowledge_base.id
    assert request.targets[0].score_threshold == 0.2


@pytest.mark.anyio
async def test_agent_service_retrieve_rag_context_handles_empty_and_failure(
    monkeypatch,
):
    service = AgentService()

    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return []

            return resolve().__await__()

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter", lambda **_kwargs: Query()
    )
    assert await service._retrieve_rag_context(_agent(), "query") is None

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    assert await service._retrieve_rag_context(_agent(), "query") is None
