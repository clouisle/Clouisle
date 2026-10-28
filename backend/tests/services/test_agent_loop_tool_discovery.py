"""AgentLoop per-turn tool list wiring for tool discovery."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.types import (
    ChatResponse,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole,
    ToolCall,
    Usage,
)
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


class _Discovery:
    def __init__(self):
        self.calls = 0
        self.lists = [
            ["first-turn-tool"],
            ["first-turn-tool", "loaded-tool"],
        ]

    def tools_for_turn(self):
        index = min(self.calls, len(self.lists) - 1)
        self.calls += 1
        return list(self.lists[index])


@pytest.mark.asyncio
async def test_each_model_turn_receives_the_current_tool_list(monkeypatch):
    from app.services import agent_round

    async def _persist_step(**kwargs):
        return kwargs["round_index"] + 1

    async def _persist_result(**kwargs):
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_assistant_step", _persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_result)

    seen: list[list[str]] = []

    async def _provider(**kwargs):
        seen.append(list(kwargs.get("tools") or []))
        if len(seen) == 1:
            return ChatResponse(
                id="r",
                model="m",
                content="",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        function=FunctionCall(name="load_tools", arguments="{}"),
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                usage=Usage(),
            )
        return ChatResponse(
            id="r",
            model="m",
            content="done",
            tool_calls=None,
            finish_reason=FinishReason.STOP,
            usage=Usage(),
        )

    async def _tool(tool_name, arguments, **kwargs):
        return json.dumps({"loaded": ["loaded-tool"]})

    async def _build_turn(**kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[LLMMessage(role=MessageRole.USER, content="go")],
                compression=None,
            )
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="go",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=3,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=_provider,
        build_turn=_build_turn,
        execute_tool_call=_tool,
        tool_discovery=_Discovery(),
        formatter=None,
    )

    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    assert seen == [
        ["first-turn-tool"],
        ["first-turn-tool", "loaded-tool"],
    ]
    assert loop.result.full_content == "done"
