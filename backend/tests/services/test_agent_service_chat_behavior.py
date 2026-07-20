import builtins
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import FunctionCall, MessageRole, ToolCall, ToolDefinition
from app.models.agent import RAGMode

# ToolCall is currently evaluated from a TYPE_CHECKING-only import in agent.py.
builtins.ToolCall = ToolCall
AgentService = importlib.import_module("app.services.agent").AgentService
del builtins.ToolCall


@pytest.mark.anyio
async def test_chat_executes_tool_then_aggregates_final_response_usage():
    agent = SimpleNamespace(team_id=None, model_id=None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="search", arguments="{}"),
    )
    first_response = SimpleNamespace(
        content="I will search.",
        tool_calls=[tool_call],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )
    final_response = SimpleNamespace(
        content="The answer.",
        tool_calls=[],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=4, total_tokens=11),
    )
    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])
    service._execute_tool = AsyncMock(return_value={"results": ["match"]})

    with patch(
        "app.services.agent.model_manager.chat",
        new=AsyncMock(side_effect=[first_response, final_response]),
    ) as chat:
        result = await service.chat(agent, "Find it", user_id="user-1")

    assert result == {
        "response": "The answer.",
        "tool_calls": [tool_call.model_dump()],
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
    }
    assert chat.await_count == 2
    second_messages = chat.await_args_list[1].kwargs["messages"]
    assert [(message.role, message.content) for message in second_messages] == [
        ("assistant", "I will search."),
        ("tool", "{'results': ['match']}"),
    ]
    service._execute_tool.assert_awaited_once_with(agent=agent, tool_call=tool_call)


@pytest.mark.anyio
async def test_chat_stream_yields_content_tool_calls_usage_and_final_response():
    agent = SimpleNamespace(team_id=None, model_id=None)
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="search", arguments="{}"),
    )
    usage = SimpleNamespace(model_dump=lambda: {"total_tokens": 5})
    turns = [
        [
            SimpleNamespace(
                delta=SimpleNamespace(content="Searching", tool_calls=[tool_call]),
                usage=usage,
            )
        ],
        [
            SimpleNamespace(
                delta=SimpleNamespace(content="Done", tool_calls=[]), usage=None
            )
        ],
    ]

    async def chat_stream(**kwargs):
        for chunk in turns.pop(0):
            yield chunk

    service = AgentService()
    service._build_messages = AsyncMock(return_value=[])
    service._get_agent_tools = AsyncMock(return_value=[])
    service._execute_tool = AsyncMock(return_value={"results": ["match"]})

    with patch("app.services.agent.model_manager.chat_stream", new=chat_stream):
        events = [event async for event in service.chat_stream(agent, "Find it")]

    assert events == [
        "Searching",
        {"tool_call": tool_call.model_dump()},
        {"usage": {"total_tokens": 5}},
        "Done",
    ]
    service._execute_tool.assert_awaited_once_with(agent=agent, tool_call=tool_call)


@pytest.mark.anyio
async def test_build_messages_adds_context_history_and_rag_before_current_message():
    agent = SimpleNamespace(system_prompt="Be concise", rag_mode=RAGMode.AUTO)
    service = AgentService()
    service._retrieve_rag_context = AsyncMock(return_value="Trusted context")

    messages = await service._build_messages(
        agent,
        "Current question",
        context={"region": "EU"},
        conversation_history=[
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "system", "content": "Additional rule"},
            {"role": "ignored", "content": "Do not include"},
        ],
    )

    assert [(message.role, message.content) for message in messages] == [
        (MessageRole.SYSTEM, "Be concise\n\nContext:\n- region: EU"),
        (MessageRole.USER, "Earlier question"),
        (MessageRole.ASSISTANT, "Earlier answer"),
        (MessageRole.SYSTEM, "Additional rule"),
        (MessageRole.SYSTEM, "Relevant context:\nTrusted context"),
        (MessageRole.USER, "Current question"),
    ]
    service._retrieve_rag_context.assert_awaited_once_with(agent, "Current question")


@pytest.mark.anyio
async def test_agent_tools_include_available_builtin_media_and_agentic_search():
    agent = SimpleNamespace(
        tools_config=[
            {"type": "builtin", "name": "web_search"},
            {"type": "builtin", "name": "missing"},
            {"type": "mcp", "name": "future"},
        ],
        enable_image_generation=True,
        enable_video_generation=False,
        rag_mode=RAGMode.AGENTIC,
    )
    builtin = ToolDefinition(
        type="function",
        function={
            "name": "web_search",
            "description": "Search",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    service = AgentService()
    service._get_builtin_tool = lambda name: builtin if name in {"web_search", "generate_image"} else None

    tools = await service._get_agent_tools(agent)

    assert [tool.function.name for tool in tools] == [
        "web_search",
        "web_search",
        "search_knowledge_base",
    ]
