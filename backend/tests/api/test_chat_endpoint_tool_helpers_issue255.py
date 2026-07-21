from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import RAGMode


class Query:
    def __init__(self, result=None):
        self.result = result
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(id=uuid4()),
        "model_id": None,
        "tools_config": [],
        "enable_memory": False,
        "memory_config": {},
        "rag_mode": RAGMode.OFF,
        "enable_image_generation": False,
        "enable_video_generation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_model_and_stats_helpers_mock_database_boundaries(monkeypatch):
    assert await chat.get_model_identifier(agent()) is None
    assert await chat.get_agent_chat_model(agent()) is None

    model_id = uuid4()
    team_model = SimpleNamespace(
        model=SimpleNamespace(provider="test-provider", model_id="test-model")
    )
    model_query = Query(team_model)
    monkeypatch.setattr(chat.TeamModel, "filter", lambda **_kwargs: model_query)
    configured = agent(model_id=model_id)

    assert await chat.get_model_identifier(configured) == "test-provider/test-model"
    assert await chat.get_agent_chat_model(configured) is team_model

    agent_query = Query()
    team_query = Query()
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: team_query)

    await chat.update_message_stats(configured, {"prompt": 3, "completion": None})

    agent_query.update.assert_awaited_once()
    team_query.update.assert_awaited_once()


@pytest.mark.anyio
async def test_macro_summary_persistence_is_best_effort(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    source_id = uuid4()
    persist = AsyncMock()
    monkeypatch.setattr(chat, "persist_compacted_context_snapshot", persist)
    monkeypatch.setattr(chat, "extract_macro_summary_text", lambda _messages: None)

    await chat.persist_macro_summary_best_effort(
        conversation=conversation,
        source_message_id=source_id,
        messages=[],
        model_id=None,
    )
    persist.assert_not_awaited()

    monkeypatch.setattr(
        chat, "extract_macro_summary_text", lambda _messages: "compact summary"
    )
    await chat.persist_macro_summary_best_effort(
        conversation=conversation,
        source_message_id=source_id,
        messages=[object()],
        model_id="test/model",
    )
    persist.assert_awaited_once_with(
        conversation=conversation,
        source_message_id=source_id,
        summary_text="compact summary",
        model_id="test/model",
    )

    persist.reset_mock(side_effect=True)
    persist.side_effect = RuntimeError("disposable failure")
    await chat.persist_macro_summary_best_effort(
        conversation=conversation,
        source_message_id=source_id,
        messages=[object()],
        model_id=None,
    )


@pytest.mark.anyio
async def test_agent_tools_assemble_memory_rag_builtin_and_custom(monkeypatch):
    from app.models.tool import Tool

    current_agent = agent(
        enable_memory=True,
        memory_config={"auto_extract": False},
        rag_mode=RAGMode.AGENTIC,
        enable_image_generation=True,
        tools_config=[
            {"type": "builtin", "name": "clock"},
            {"type": "custom", "tool_id": "custom-id"},
        ],
    )
    knowledge_base = SimpleNamespace(name="Docs", description="Internal")
    monkeypatch.setattr(
        chat.AgentKnowledgeBase,
        "filter",
        lambda **_kwargs: Query([SimpleNamespace(knowledge_base=knowledge_base)]),
    )
    monkeypatch.setattr(
        "app.llm.tools.memory_tools.get_memory_tools",
        lambda: [
            {
                "name": "create_memory_entity",
                "description": "create",
                "input_schema": {},
            },
            {
                "name": "search_memory",
                "description": "search",
                "input_schema": {"type": "object"},
            },
        ],
    )
    custom_tool = SimpleNamespace(
        name="lookup",
        description="Lookup",
        parameters=[
            {
                "name": "query",
                "type": "string",
                "description": "Search text",
                "required": True,
            }
        ],
    )
    monkeypatch.setattr(Tool, "filter", lambda **_kwargs: Query(custom_tool))
    monkeypatch.setattr(
        chat.tool_registry,
        "to_openai_tools",
        lambda names: [
            {
                "type": "function",
                "function": {
                    "name": names[0],
                    "description": names[0],
                    "parameters": {},
                },
            }
        ],
    )
    monkeypatch.setattr(
        chat.tool_registry, "to_openai_sandbox_tools", lambda _names: []
    )

    tools = await chat.get_agent_tools(current_agent)
    by_name = {item["function"]["name"]: item for item in tools}

    assert set(by_name) == {
        "search_memory",
        "knowledge_search",
        "generate_image",
        "clock",
        "custom_lookup",
    }
    assert by_name["custom_lookup"]["function"]["parameters"]["required"] == ["query"]


@pytest.mark.anyio
async def test_agent_tools_cover_skill_and_mcp_failures_without_network(
    monkeypatch,
):
    from app.models.tool import Tool
    from app.services.skill import SkillService

    current_agent = agent(
        tools_config=[
            {"type": "skill", "skill_id": "broken-skill"},
            {"type": "mcp", "server_id": "mcp-id"},
        ]
    )
    monkeypatch.setattr(
        SkillService,
        "get_skill_for_team",
        AsyncMock(side_effect=RuntimeError("missing skill")),
    )
    monkeypatch.setattr(
        Tool,
        "filter",
        lambda **_kwargs: Query(
            SimpleNamespace(name="server", mcp_config={"url": "mock://server"})
        ),
    )
    monkeypatch.setattr(
        "app.llm.tools.mcp_client.list_mcp_tools",
        AsyncMock(side_effect=RuntimeError("offline")),
    )

    assert await chat.get_agent_tools(current_agent) == []


@pytest.mark.anyio
async def test_tool_display_names_use_local_metadata_and_mocked_models(monkeypatch):
    from app.models.tool import Tool
    from app.schemas.tool import BUILTIN_TOOLS_METADATA

    current_agent = agent(
        enable_memory=True,
        rag_mode=RAGMode.AGENTIC,
        enable_image_generation=True,
        tools_config=[
            {"type": "builtin", "name": "known"},
            {"type": "builtin", "name": "plain"},
            {"type": "custom", "tool_id": "custom-id"},
        ],
    )
    monkeypatch.setattr(chat.AgentKnowledgeBase, "filter", lambda **_kwargs: Query(1))
    monkeypatch.setitem(
        BUILTIN_TOOLS_METADATA, "known", {"display_name_key": "known_key"}
    )
    monkeypatch.setitem(BUILTIN_TOOLS_METADATA, "plain", {"display_name": "Plain tool"})
    monkeypatch.setitem(
        BUILTIN_TOOLS_METADATA,
        "generate_image",
        {"display_name_key": "image_key"},
    )
    monkeypatch.setattr("app.core.i18n.t", lambda key, **_kwargs: f"translated:{key}")
    monkeypatch.setattr(
        Tool,
        "filter",
        lambda **_kwargs: Query(
            SimpleNamespace(name="lookup", display_name="Lookup tool")
        ),
    )

    names = await chat.get_tool_display_names(current_agent, "en")

    assert names["knowledge_search"] == "translated:tool_knowledge_search"
    assert names["search_memory"] == "translated:tool_search_memory"
    assert names["generate_image"] == "translated:image_key"
    assert names["known"] == "translated:known_key"
    assert names["plain"] == "Plain tool"
    assert names["custom_lookup"] == "Lookup tool"
