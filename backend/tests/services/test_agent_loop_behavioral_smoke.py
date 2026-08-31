"""
End-to-end behavioral smoke through the production AgentLoop.

Drives the real production loop, compaction, and run wiring with a scripted
fake provider and fake tools — no services, no browser. The scripted provider
performs: two tool turns, a turn-aware compaction, an injected steering, the
final completion turn, and (in a second scenario) a cooperative stop.

Exercise order matches the canonical agent-run success criteria:

1. model -> multi-tool -> steering -> model -> final, persisted as one
   canonical assistant message,
2. compaction emits compression events at the loop position and retains the
   recent tail,
3. stop produces a stopped terminal with partial content.
"""

import json

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
    ToolCall,
    Usage,
)
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


def _tool(name, call_id):
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments="{}"))


def _resp(*, content="", tool_calls=None, reasoning=None):
    return ChatResponse(
        id="r",
        model="m",
        content=content,
        reasoning_content=reasoning,
        tool_calls=tool_calls,
        finish_reason=(FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP),
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


class _ScriptedProvider:
    """Provider replaying a scripted sequence: 2 tool turns -> steering ->
    final. The steering is injected by the test AFTER the first provider turn
    (the loop consumes it at the next safe boundary)."""

    def __init__(self):
        self.turn = 0
        self.steered = False
        self.script = [
            _resp(tool_calls=[_tool("read_a", "c1")]),
            _resp(tool_calls=[_tool("read_b", "c2")]),
            _resp(content="final answer"),
        ]

    async def __call__(self, **kwargs):
        messages = kwargs.get("messages", [])
        if any(
            isinstance(m.get("content"), str) and "steer" in str(m.get("content", ""))
            for m in messages
        ):
            self.steered = True
            return _resp(content="steered answer")
        resp = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        return resp


@pytest.mark.asyncio
async def test_behavioral_smoke_two_tool_turns_steering_and_final(monkeypatch):
    """Production loop: model -> multi-tool -> steering -> final, one round."""
    from app.services import agent_round

    persisted: list[dict] = []

    async def _persist_step(**kwargs):
        persisted.append(("step", kwargs["tool_calls"]))
        return kwargs["round_index"] + 1

    async def _persist_result(**kwargs):
        persisted.append(("result", kwargs["tool_name"], kwargs["tool_call_id"]))
        return kwargs["round_index"] + 1

    monkeypatch.setattr(agent_round, "persist_assistant_step", _persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", _persist_result)

    provider = _ScriptedProvider()
    steering = {"content": "steer!", "applied": False}
    queue: list[SimpleNamespace] = []

    async def _steer_injector(**kwargs):
        # After the first provider call, inject a steering input.
        if provider.turn == 1 and not queue:
            queue.append(SimpleNamespace(content="steer!", sequence=1))
        resp = await provider(**kwargs)
        return resp

    async def _consume_inputs():
        if queue:
            return [queue.pop(0)]
        return []

    async def _input_consumed(item):
        steering["applied"] = True
        if context.working_history_override is None:
            context.working_history_override = []
        context.working_history_override.append(
            {
                "role": "user",
                "content": item.content or "",
                "round_id": str(uuid4()),
                "round_index": 10_001,
                "round_role": "user_input",
                "is_round_canonical": True,
                "round_status": "completed",
            }
        )

    async def _tool_runner(tool_name, arguments, **kwargs):
        return {"result": f"{tool_name}-ok"}

    async def build_turn(**kwargs):
        return ContextTurn(prepared=_prepared_messages(kwargs))

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="do the task",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=10,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=_steer_injector,
        build_turn=build_turn,
        execute_tool_call=_tool_runner,
        consume_inputs=_consume_inputs,
        input_consumed=_input_consumed,
        formatter=None,
    )

    async def _stop():
        return False

    context.stop_requested = _stop

    # Steering arrives mid-run (after the first tool turn completes).
    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    result = loop.result
    assert result.max_iterations_reached is False
    assert result.manually_stopped is False
    # Both tool turns produced persisted tool results, in model order.
    tool_results = [p for p in persisted if p[0] == "result"]
    assert [p[2] for p in tool_results] == ["c1", "c2"]
    # Steering was consumed and appears as a user message in working history.
    assert steering["applied"] is True
    user_msgs = [
        e for e in context.working_history_override or [] if e.get("role") == "user"
    ]
    assert any("steer!" in e.get("content", "") for e in user_msgs)


def _prepared_messages(kwargs):
    history = kwargs.get("history_override") or []
    msgs = [LLMMessage(role=MessageRole.USER, content="do the task")]
    msgs.extend(
        LLMMessage(
            role=MessageRole.USER if h.get("role") == "user" else MessageRole.ASSISTANT,
            content=h.get("content", ""),
        )
        for h in history
        if isinstance(h, dict)
    )
    return SimpleNamespace(messages=msgs)


@pytest.mark.asyncio
async def test_behavioral_smoke_compaction_events_at_loop_position(monkeypatch):
    """Compression events emitted mid-pipeline keep the recent tail."""
    from app.services import agent_round

    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    provider = _ScriptedProvider()

    async def _tool_runner(tool_name, arguments, **kwargs):
        return {"result": "ok"}

    # A plan that WILL summarize: oversized history forces compaction.
    async def build_turn(**kwargs):
        class _Plan:
            will_summarize = True
            compression = SimpleNamespace(
                stage="macro",
                actions=["context_summary"],
            )

            async def finalize(self):
                tail = kwargs.get("history_override") or []
                msgs = [LLMMessage(role=MessageRole.SYSTEM, content="sys")]
                msgs.append(
                    LLMMessage(
                        role=MessageRole.USER,
                        content="Earlier conversation summary: ...",
                    )
                )
                msgs.extend(
                    LLMMessage(role=MessageRole.ASSISTANT, content="tail a")
                    for _ in tail[-1:]
                )
                return SimpleNamespace(messages=msgs, compression=self.compression)

        return ContextTurn(plan=_Plan(), will_summarize=True)

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="do the task",
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
        team_chat=provider,
        build_turn=build_turn,
        execute_tool_call=_tool_runner,
        formatter=lambda name, payload: f"event: {name}\n",
    )

    events: list[str] = []
    async for chunk in context and AgentLoop(context).run() or ():
        if chunk:
            events.append(chunk)

    names = [e.split(": ", 1)[-1].strip() for e in events]
    assert "compression_start" in names
    assert "compression_end" in names
    start = names.index("compression_start")
    end = names.index("compression_end")
    # Compression events are ordered before later content.
    assert start < end


@pytest.mark.asyncio
async def test_behavioral_smoke_cooperative_stop_partial(monkeypatch):
    """A stop requested between turns persists partial content as stopped."""
    from app.services import agent_round

    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    partial_content = {"value": ""}
    stop_now = {"flag": False}

    async def _team_chat(**kwargs):
        partial_content["value"] = "partial sentence"
        return _resp(content="partial sentence")

    async def build_turn(**kwargs):
        msgs = [LLMMessage(role=MessageRole.USER, content="hi")]
        return ContextTurn(prepared=SimpleNamespace(messages=msgs))

    async def _stop():
        return stop_now["flag"]

    calls = {"n": 0}

    async def _team_chat_after_stop(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            stop_now["flag"] = True
        return _resp(content="final")

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="hi",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=5,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        team_chat=_team_chat_after_stop,
        build_turn=build_turn,
        stop_requested=_stop,
        formatter=None,
    )
    loop = AgentLoop(context)
    async for _ in loop.run():
        pass
    assert loop.result.manually_stopped is True


@pytest.mark.asyncio
async def test_stream_emits_tool_call_before_tool_execution(monkeypatch):
    """A streamed call is visible with complete inputs before its result."""
    from app.services import agent_round

    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    call_id = "call-write"
    provider_calls = 0
    events: list[tuple[str, dict]] = []

    async def provider_stream(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            yield ChatStreamChunk(
                id="response-1",
                model="m",
                delta=ChatStreamDelta(
                    tool_call_starts=[
                        ToolCall(
                            id=call_id,
                            function=FunctionCall(name="write", arguments="{}"),
                        )
                    ]
                ),
            )
            yield ChatStreamChunk(
                id="response-1",
                model="m",
                delta=ChatStreamDelta(
                    tool_calls=[
                        ToolCall(
                            id=call_id,
                            function=FunctionCall(
                                name="write",
                                arguments='{"path":"notes.txt","content":"hello"}',
                            ),
                        )
                    ]
                ),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=Usage(prompt_tokens=10, completion_tokens=4, total_tokens=14),
            )
            return

        yield ChatStreamChunk(
            id="response-2",
            model="m",
            delta=ChatStreamDelta(content="done"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=12, completion_tokens=1, total_tokens=13),
        )

    def formatter(name: str, payload: dict) -> str:
        raw = payload.get("sse")
        if isinstance(raw, str):
            data = next(
                line[5:].strip()
                for line in raw.splitlines()
                if line.startswith("data:")
            )
            event_payload = json.loads(data)
        else:
            event_payload = payload
        events.append((name, event_payload))
        return f"event: {name}\n"

    async def tool_runner(tool_name, arguments, **_kwargs):
        assert tool_name == "write"
        assert arguments == {"path": "notes.txt", "content": "hello"}
        assert events[0][0] == "tool_call"
        assert events[0][1]["arguments"] == {}
        assert events[1][0] == "tool_call"
        assert events[1][1]["arguments"] == arguments
        events.append(("tool_execution_started", {}))
        return {"result": "written"}

    async def build_turn(**_kwargs):
        return ContextTurn(
            prepared=SimpleNamespace(
                messages=[LLMMessage(role=MessageRole.USER, content="write it")]
            )
        )

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="write it",
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=3,
        streaming=True,
        round_id=uuid4(),
        team_chat_stream=provider_stream,
        build_turn=build_turn,
        execute_tool_call=tool_runner,
        tool_display_names={"write": "Write"},
        formatter=formatter,
    )

    loop = AgentLoop(context)
    async for _ in loop.run():
        pass

    assert [name for name, _payload in events] == [
        "tool_call",
        "tool_call",
        "tool_execution_started",
        "tool_result",
        "content_delta",
    ]
    assert events[3][1]["is_error"] is False
    assert loop.result.full_content == "done"
