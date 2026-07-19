import builtins
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.types import FunctionCall, ToolCall

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
