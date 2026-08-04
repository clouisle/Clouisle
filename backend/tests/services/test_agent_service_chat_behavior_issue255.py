import builtins
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.llm.types import MessageRole, ToolDefinition
from app.llm.types.chat import ToolCall
from app.models.agent import RAGMode

builtins.ToolCall = ToolCall
try:
    AgentService = import_module("app.services.agent").AgentService
finally:
    del builtins.ToolCall


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "model_id": uuid4(),
        "system_prompt": "Be useful",
        "tools_config": [],
        "enable_image_generation": False,
        "enable_video_generation": False,
        "rag_mode": RAGMode.OFF,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_build_messages_adds_context_history_and_rag_before_current_message():
    service = AgentService()
    agent = _agent(rag_mode=RAGMode.AUTO)

    with patch.object(
        service, "_retrieve_rag_context", AsyncMock(return_value="Stored context")
    ):
        messages = await service._build_messages(
            agent,
            "Current question",
            context={"locale": "en"},
            conversation_history=[
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "system", "content": "Extra instruction"},
                {"role": "ignored", "content": "not included"},
            ],
        )

    pairs = [(message.role, message.content) for message in messages]
    # Workflow mode injects Markdown/language guidance into the system prompt.
    assert pairs[0][0] is MessageRole.SYSTEM
    assert pairs[0][1].startswith("Be useful\n\nContext:\n- locale: en")
    assert "## Markdown Output" in pairs[0][1]
    assert pairs[1:] == [
        (MessageRole.USER, "Earlier question"),
        (MessageRole.ASSISTANT, "Earlier answer"),
        (MessageRole.SYSTEM, "Extra instruction"),
        (MessageRole.SYSTEM, "Relevant context:\nStored context"),
        (MessageRole.USER, "Current question"),
    ]


@pytest.mark.anyio
async def test_get_agent_tools_combines_configured_media_and_agentic_tools():
    service = AgentService()
    builtin = ToolDefinition.model_validate(
        {
            "type": "function",
            "function": {
                "name": "builtin",
                "description": "Built in",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    )
    skill_tool = ToolDefinition.model_validate(
        {
            "type": "function",
            "function": {
                "name": "skill_demo",
                "description": "Skill",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    )
    agent = _agent(
        tools_config=[
            {"type": "builtin", "name": "web_search"},
            {"type": "skill", "skill_id": "skill-1"},
            {"type": "skill"},
            {"type": "mcp"},
        ],
        enable_image_generation=True,
        enable_video_generation=True,
        rag_mode=RAGMode.AGENTIC,
    )

    with (
        patch.object(service, "_get_builtin_tool", return_value=builtin) as get_builtin,
        patch(
            "app.services.skill.SkillService.get_skill_for_team",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        patch(
            "app.services.skill.SkillService.to_tool_definition",
            return_value=skill_tool,
        ),
    ):
        tools = await service._get_agent_tools(agent)

    assert [tool.function.name for tool in tools] == [
        "builtin",
        "skill_demo",
        "builtin",
        "builtin",
        "search_knowledge_base",
    ]
    assert [call.args[0] for call in get_builtin.call_args_list] == [
        "web_search",
        "generate_image",
        "generate_video",
    ]


@pytest.mark.anyio
async def test_execute_tool_handles_invalid_unknown_and_configured_calls():
    service = AgentService()
    agent = _agent()

    invalid = SimpleNamespace(
        function=SimpleNamespace(name="web_search", arguments="{"), id="call-1"
    )
    assert (await service._execute_tool(agent, invalid))["error"]

    unknown = SimpleNamespace(
        function=SimpleNamespace(name="missing", arguments={}), id="call-2"
    )
    with patch("app.llm.tools.tool_registry.get_tool", return_value=None):
        result = await service._execute_tool(agent, unknown)
    assert result == {
        "error": "Tool not found",
        "tool_name": "missing",
        "success": False,
    }

    configured = SimpleNamespace(
        function=SimpleNamespace(name="web_search", arguments='{"query": "test"}'),
        id="call-3",
    )
    team_config = SimpleNamespace(credentials={"token": "secret"})
    query = SimpleNamespace(first=AsyncMock(return_value=team_config))
    with (
        patch("app.llm.tools.tool_registry.get_tool", return_value=object()),
        patch(
            "app.models.tool_config.ToolConfig.filter", return_value=query
        ) as filter_,
        patch(
            "app.llm.tools.tool_registry.execute",
            new=AsyncMock(return_value={"answer": 42}),
        ) as execute,
    ):
        result = await service._execute_tool(agent, configured)

    assert result == {"answer": 42}
    filter_.assert_called_once_with(tool_name="web_search", team_id=agent.team_id)
    execute.assert_awaited_once_with(
        name="web_search",
        arguments={"query": "test"},
        credentials={"token": "secret"},
        agent=agent,
        team_id=str(agent.team_id),
    )


@pytest.mark.anyio
async def test_retrieve_rag_context_sorts_results_and_tolerates_failures():
    service = AgentService()
    agent = _agent()
    first_kb = SimpleNamespace(
        id="kb-1",
        name="First",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=agent.team_id,
        status="active",
        settings=None,
    )
    second_kb = SimpleNamespace(
        id="kb-2",
        name="Second",
        embedding_model_id="embedding-1",
        rerank_model_id="rerank-1",
        team_id="team-1",
        status="active",
        settings=None,
    )
    links = [
        SimpleNamespace(
            knowledge_base=first_kb,
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.2,
        ),
        SimpleNamespace(
            knowledge_base=None,
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.2,
        ),
        SimpleNamespace(
            knowledge_base=second_kb,
            search_mode="vector",
            retrieval_top_k=2,
            score_threshold=0.5,
        ),
    ]
    query = SimpleNamespace(prefetch_related=AsyncMock(return_value=links))
    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {"kb_name": "Second", "content": "higher", "score": 0.9},
                {"kb_name": "First", "content": "lower", "score": 0.4},
            )
        )
    )

    with (
        patch("app.services.agent.AgentKnowledgeBase.filter", return_value=query),
        patch("app.services.retrieval.retrieve", retrieve),
    ):
        context = await service._retrieve_rag_context(agent, "question")

    assert context == "[Second] higher\n\n[First] lower"
    request = retrieve.await_args.args[0]
    assert [target.kb_id for target in request.targets] == ["kb-1", "kb-2"]

    broken_query = SimpleNamespace(
        prefetch_related=AsyncMock(side_effect=RuntimeError("db unavailable"))
    )
    with patch(
        "app.services.agent.AgentKnowledgeBase.filter", return_value=broken_query
    ):
        assert await service._retrieve_rag_context(agent, "question") is None


@pytest.mark.anyio
async def test_chat_executes_tool_then_returns_final_response_and_usage():
    service = AgentService()
    agent = _agent()
    tool_call = ToolCall(
        id="call-1",
        function={"name": "demo", "arguments": "{}"},
    )
    usage = SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)
    responses = [
        SimpleNamespace(content="", tool_calls=[tool_call], usage=usage),
        SimpleNamespace(content="Final answer", tool_calls=[], usage=None),
    ]

    with (
        patch.object(service, "_build_messages", AsyncMock(return_value=[])),
        patch.object(service, "_get_agent_tools", AsyncMock(return_value=[])),
        patch.object(service, "_execute_tool", AsyncMock(return_value={"ok": True})),
        patch(
            "app.services.agent.model_manager.chat",
            new=AsyncMock(side_effect=responses),
        ),
    ):
        result = await service.chat(agent, "question")

    assert result == {
        "response": "Final answer",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "demo", "arguments": "{}"},
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }
