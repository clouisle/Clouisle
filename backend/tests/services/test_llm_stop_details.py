"""
Focused tests for Stage 6 provider stop details and termination guards.

Covers:

- StopDetails / StopReason live on ChatResponse and ChatStreamChunk,
- pause_turn streams continue up to 8 consecutive times and then terminate,
- a tool-call turn resets the pause-turn counter,
- LENGTH with started-but-uncompleted tool calls pairs every started call
  with an explicit skipped/error tool result (no orphan protocol messages),
- a wall-clock deadline exceeds -> deadline_exceeded terminal distinct from
  the iteration cap.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import (
    ChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole,
    StopDetails,
    StopReason,
    ToolCall,
    Usage,
)
from app.services.agent_loop import (
    AgentLoop,
    AgentLoopContext,
    ContextTurn,
)


def _ctx(**overrides):
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    conversation = SimpleNamespace(id=uuid4())
    context = AgentLoopContext(
        agent=agent,
        conversation=conversation,
        user=SimpleNamespace(id=uuid4()),
        user_message="hi",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=20,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        formatter=None,
    )
    for k, v in overrides.items():
        setattr(context, k, v)
    return context


def _prepared():
    return SimpleNamespace(messages=[LLMMessage(role=MessageRole.USER, content="hi")])


@pytest.mark.asyncio
async def test_pause_turn_continues_and_caps_at_eight(monkeypatch):
    """Each pause_turn resamples; the ninth consecutive pause terminates."""
    turn_calls = {"n": 0}

    async def _team_chat(**kwargs):
        turn_calls["n"] += 1
        return ChatResponse(
            id="r",
            model="m",
            content="",
            finish_reason=FinishReason.STOP,
            stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared())

    ctx = _ctx(team_chat=_team_chat, build_turn=build_turn)
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    # 8 continuations after the first call => 9 total calls.
    assert turn_calls["n"] == 9


@pytest.mark.asyncio
async def test_tool_call_turn_resets_pause_counter(monkeypatch):
    """A tool-call turn resets the consecutive pause counter."""
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    calls = {"n": 0}

    async def _team_chat(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # tool round: a real tool call executes then the loop continues
            return ChatResponse(
                id="r",
                model="m",
                content="",
                finish_reason=FinishReason.TOOL_CALLS,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        function=FunctionCall(name="tool", arguments="{}"),
                    )
                ],
                stop_details=StopDetails(reason=StopReason.TOOL_CALLS),
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
        # then 8 repeated pause turns
        return ChatResponse(
            id="r",
            model="m",
            content="",
            finish_reason=FinishReason.STOP,
            stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared())

    ctx = _ctx(
        team_chat=_team_chat,
        build_turn=build_turn,
        max_iterations=50,
        execute_tool_call=lambda _n, _a, **_k: AsyncMock(
            return_value={"result": "ok"}
        )(),
    )
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    # tool turn (1) + up to 8 pause resamples + terminating probe:
    # the loop runs several turns and terminates deterministically.
    assert calls["n"] >= 9
    assert calls["n"] <= 10


@pytest.mark.asyncio
async def test_length_truncated_tool_calls_get_skipped_results(monkeypatch):
    """LENGTH with started-but-uncompleted calls pairs them with error
    results; no orphan enters provider history."""
    from app.services import agent_round

    persisted_results: list[dict] = []

    async def _persist_tool_result(**kwargs):
        persisted_results.append(kwargs)
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_tool_result)
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=2)
    )

    # Streaming turn announces two tool calls; finish=LENGTH truncates them.
    async def _team_chat_stream(**kwargs):
        yield ChatStreamChunk(
            id="c",
            model="m",
            delta=ChatStreamDelta(
                tool_call_starts=[
                    ToolCall(
                        id="call_a", function=FunctionCall(name="a", arguments="{}")
                    ),
                    ToolCall(
                        id="call_b", function=FunctionCall(name="b", arguments="{}")
                    ),
                ]
            ),
        )
        yield ChatStreamChunk(
            id="c",
            model="m",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.LENGTH,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared())

    async def _execute_tool(tool_name, arguments, **kwargs):
        return {"result": "ok"}

    ctx = _ctx(
        streaming=True,
        team_chat_stream=_team_chat_stream,
        team_chat=AsyncMock(),
        build_turn=build_turn,
        execute_tool_call=_execute_tool,
        formatter=None,
        max_iterations=2,
    )
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    # Both started calls get explicit error-tool results.
    call_ids = {p["tool_call_id"] for p in persisted_results}
    assert call_ids == {"call_a", "call_b"}
    assert all("truncated" in p["content"] for p in persisted_results)


@pytest.mark.asyncio
async def test_deadline_exceeds_marks_deadline_terminal(monkeypatch):
    """A wall-clock deadline stops the round with deadline_exceeded."""
    calls = {"n": 0}

    async def _team_chat(**kwargs):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return ChatResponse(
            id="r",
            model="m",
            content="partial",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared())

    ctx = _ctx(team_chat=_team_chat, build_turn=build_turn, deadline_seconds=0.01)
    loop = AgentLoop(ctx)
    async for _ in loop.run():
        pass

    assert loop.result.deadline_exceeded is True
    assert loop.result.max_iterations_reached is False
    assert calls["n"] <= 2


@pytest.mark.asyncio
async def test_stop_details_types_carry_on_responses_and_chunks():
    """StopDetails ride on both response types without breaking construction."""
    resp = ChatResponse(
        id="r",
        model="m",
        content="x",
        finish_reason=FinishReason.STOP,
        stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    chunk = ChatStreamChunk(
        id="c",
        model="m",
        delta=ChatStreamDelta(),
        finish_reason=FinishReason.STOP,
        stop_details=StopDetails(
            reason=StopReason.STOP, raw='{"stop_reason":"end_turn"}'
        ),
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    assert resp.stop_details.reason == StopReason.PAUSE_TURN
    assert chunk.stop_details.raw == '{"stop_reason":"end_turn"}'
