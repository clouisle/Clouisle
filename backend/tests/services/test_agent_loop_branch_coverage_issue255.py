from __future__ import annotations

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
from app.services import agent_loop, agent_round
from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn


def _tool(name: str, call_id: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=arguments),
    )


def _prepared(content: str = "request") -> SimpleNamespace:
    return SimpleNamespace(
        messages=[LLMMessage(role=MessageRole.USER, content=content)],
        compression=None,
    )


def _response(
    *,
    content: str = "done",
    reasoning: str | None = None,
    tool_calls: list[ToolCall] | None = None,
    finish_reason: FinishReason | None = None,
    stop_details: StopDetails | None = None,
    usage: Usage | None = None,
) -> ChatResponse:
    return ChatResponse(
        id="response",
        model="model",
        content=content,
        reasoning_content=reasoning,
        tool_calls=tool_calls,
        finish_reason=finish_reason
        or (FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP),
        stop_details=stop_details,
        usage=usage or Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _context(**overrides: object) -> AgentLoopContext:
    async def build_turn(**_kwargs: object) -> ContextTurn:
        return ContextTurn(prepared=_prepared())

    async def team_chat(**_kwargs: object) -> ChatResponse:
        return _response()

    context = AgentLoopContext(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message="request",
        model_id="model",
        tokenizer_model_id=None,
        model_provider="provider",
        model_context_limit=100_000,
        model_max_output_tokens=1_000,
        model_used="model",
        max_iterations=3,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        build_turn=build_turn,
        team_chat=team_chat,
        formatter=None,
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


async def _consume_loop(loop: AgentLoop) -> list[str | None]:
    return [event async for event in loop.run()]


def test_agent_loop_helper_paths_keep_tool_protocol_complete():
    empty_arguments = agent_loop._safe_arguments(None)
    assert empty_arguments == {}
    arguments = {"path": "notes.txt"}
    assert agent_loop._safe_arguments(arguments) is arguments

    context = _context(
        tool_concurrency=lambda name: (
            "shared" if name.startswith("read") else "exclusive"
        )
    )
    loop = AgentLoop(context)
    assert loop._partition_tool_batch([]) == []
    groups = loop._partition_tool_batch(
        [_tool("read_a", "a"), _tool("read_b", "b"), _tool("write", "c")]
    )
    assert [[call.id for call in group] for group in groups] == [["a", "b"], ["c"]]
    assert loop._build_tool_call_sse(_tool("", "missing")) == ""

    skipped_call = loop._skipped_tool(_tool("write", "skipped"), reason="stopped")
    assert skipped_call[3]["name"] == "write"
    malformed = loop._skipped_tool(_tool("", "truncated"), reason="truncated")
    assert malformed[0] == ""
    assert "truncated" in malformed[3]["display_result"]


@pytest.mark.asyncio
async def test_agent_loop_tool_execution_media_and_malformed_records(monkeypatch):
    from app.services import agent_round

    generated = []
    images = []
    inventory = []

    def append_generated_images(image_pool, image_inventory, display_result):
        generated.append((image_pool, image_inventory, display_result))

    async def execute_tool(_name, _arguments, **_kwargs):
        return {
            "kind": "media.image",
            "success": True,
            "images": [{"image": {"url": "https://example.test/generated.png"}}],
        }

    context = _context(
        execute_tool_call=execute_tool,
        append_generated_images=append_generated_images,
    )
    loop = AgentLoop(context)
    call_sse, result_sse, media_sse, record = await loop._execute_one_tool(
        tc=_tool("generate", "image-call"),
        image_pool=images,
        image_inventory=inventory,
    )
    assert call_sse and result_sse and media_sse
    assert record["name"] == "generate"
    assert generated and generated[0][0] is images

    persisted = AsyncMock(return_value=2)
    monkeypatch.setattr(agent_round, "persist_tool_result", persisted)
    loop = AgentLoop(_context(round_id=uuid4(), working_history_override=[]))
    await loop._persist_tool_record(
        {
            "id": "truncated",
            "name": "",
            "arguments": {},
            "display_result": '{"error":"truncated"}',
            "llm_result": '{"error":"truncated"}',
            "display_name": "",
        },
        iteration=1,
        content="",
        reasoning="",
    )
    persisted.assert_awaited_once()
    assert loop.context.working_history_override[-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_agent_loop_error_capture_and_empty_iteration(monkeypatch):
    async def fail_build(**_kwargs):
        raise RuntimeError("build failed")

    loop = AgentLoop(_context(build_turn=fail_build))
    with pytest.raises(RuntimeError, match="build failed"):
        await _consume_loop(loop)
    assert loop.result.duration_ms >= 0

    loop.result.duration_ms = 1
    with pytest.raises(RuntimeError, match="build failed"):
        await _consume_loop(loop)

    provider = AsyncMock(return_value=_response())
    empty_loop = AgentLoop(_context(max_iterations=0, team_chat=provider))
    await _consume_loop(empty_loop)
    provider.assert_not_awaited()
    assert empty_loop.result.max_iterations_reached is False


@pytest.mark.asyncio
async def test_agent_loop_guards_heartbeat_inputs_and_plans():
    events: list[str] = []

    def formatter(name, _payload):
        events.append(name)
        return name

    consumed = []

    async def heartbeat(_last_event, _interval, _request):
        return True, 1.0

    async def consume_inputs():
        return [SimpleNamespace(content="steer")]

    async def input_consumed(item):
        consumed.append(item.content)

    async def stop_false():
        return False

    def count_tools(_tools, _model, _provider):
        return 7

    context = _context(
        formatter=formatter,
        send_heartbeat_if_needed=heartbeat,
        initial_last_event_time=0.0,
        consume_inputs=consume_inputs,
        input_consumed=input_consumed,
        stop_requested=stop_false,
        tools=[object()],
        count_tool_definition_tokens=count_tools,
    )
    loop = AgentLoop(context)
    await _consume_loop(loop)
    assert "heartbeat" in events
    assert consumed == ["steer"]

    async def stop_heartbeat(_last_event, _interval, _request):
        return False, 1.0

    stopped_provider = AsyncMock(return_value=_response())
    stopped = AgentLoop(
        _context(
            send_heartbeat_if_needed=stop_heartbeat,
            team_chat=stopped_provider,
        )
    )
    await _consume_loop(stopped)
    assert stopped.result.manually_stopped is True
    stopped_provider.assert_not_awaited()

    class Plan:
        will_summarize = False
        compression = SimpleNamespace(stage="none")

        async def finalize(self):
            return SimpleNamespace(
                messages=_prepared().messages, compression=self.compression
            )

    async def no_summary_plan(**_kwargs):
        return ContextTurn(plan=Plan(), will_summarize=False)

    plan_events: list[str] = []
    planned = AgentLoop(
        _context(
            build_turn=no_summary_plan,
            formatter=lambda name, _payload: plan_events.append(name) or name,
        )
    )
    await _consume_loop(planned)
    assert "compression_start" not in plan_events
    assert "compression_end" in plan_events

    class SummaryPlan(Plan):
        will_summarize = True

    async def summary_plan(**_kwargs):
        return ContextTurn(plan=SummaryPlan(), will_summarize=True)

    no_event = AgentLoop(
        _context(build_turn=summary_plan, formatter=lambda *_args: None)
    )
    await _consume_loop(no_event)
    assert no_event.result.full_content == "done"


@pytest.mark.asyncio
async def test_agent_loop_stream_reasoning_shared_tools_and_results(monkeypatch):
    awaitables = []
    events: list[str] = []
    provider_calls = 0
    persisted = []

    async def persist_step(**kwargs):
        persisted.append(("step", kwargs["tool_calls"]))
        return 1

    async def persist_result(**kwargs):
        persisted.append(("result", kwargs["tool_call_id"]))
        return 2

    monkeypatch.setattr(agent_round, "persist_assistant_step", persist_step)
    monkeypatch.setattr(agent_round, "persist_tool_result", persist_result)

    start_a = _tool("read_a", "a")
    unchanged_a = _tool("read_a", "a")
    complete_a = _tool("read_a", "a", '{"path":"a.txt"}')
    complete_b = _tool("read_b", "b")
    empty_name = _tool("", "truncated")

    async def stream(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            yield ChatStreamChunk(
                id="stream-1",
                model="model",
                delta=ChatStreamDelta(
                    reasoning_content="think",
                    tool_call_starts=[
                        start_a,
                        ToolCall(
                            id="", function=FunctionCall(name="read_a", arguments="{}")
                        ),
                        empty_name,
                    ],
                ),
            )
            yield ChatStreamChunk(
                id="stream-1",
                model="model",
                delta=ChatStreamDelta(
                    reasoning_content=" more",
                    tool_call_starts=[unchanged_a],
                ),
            )
            yield ChatStreamChunk(
                id="stream-1",
                model="model",
                delta=ChatStreamDelta(content="answer"),
            )
            yield ChatStreamChunk(
                id="stream-1",
                model="model",
                delta=ChatStreamDelta(tool_calls=[complete_a, complete_b]),
                finish_reason=FinishReason.TOOL_CALLS,
            )
            yield ChatStreamChunk(
                id="stream-1",
                model="model",
                delta=ChatStreamDelta(),
                usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            )
            return
        yield ChatStreamChunk(
            id="stream-2",
            model="model",
            delta=ChatStreamDelta(content="final"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=3, completion_tokens=1, total_tokens=4),
        )

    generated = []

    def append_generated_images(*args):
        generated.append(args)

    async def execute_tool(name, _arguments, **_kwargs):
        await asyncio.sleep(0)
        awaitables.append(name)
        if name == "read_a":
            return {
                "kind": "media.image",
                "success": True,
                "images": [],
            }
        raise RuntimeError("read failed")

    async def disconnected():
        return False

    async def stop_false():
        return False

    def formatter(name, _payload):
        events.append(name)
        return name

    def calculate_usage(**_kwargs):
        return 3, 2, 1, 1, 4

    async def record_usage(**_kwargs):
        events.append("usage_recorded")

    async def build_turn(**_kwargs):
        return ContextTurn(prepared=_prepared())

    context = _context(
        streaming=True,
        team_chat_stream=stream,
        team_chat=AsyncMock(),
        build_turn=build_turn,
        execute_tool_call=execute_tool,
        append_generated_images=append_generated_images,
        tool_concurrency=lambda name: (
            "shared" if name.startswith("read") else "exclusive"
        ),
        is_disconnected=disconnected,
        stop_requested=stop_false,
        formatter=formatter,
        calculate_usage=calculate_usage,
        record_stream_usage=record_usage,
        persist_step_per_tool=True,
        max_iterations=3,
    )
    loop = AgentLoop(context)
    await _consume_loop(loop)

    assert provider_calls == 2
    assert awaitables == ["read_a", "read_b"]
    assert "reasoning_start" in events
    assert "reasoning_end" in events
    assert "media_result" in events
    assert "usage_recorded" in events
    assert generated
    assert any(item[0] == "result" and item[1] == "a" for item in persisted)
    assert any(item[0] == "result" and item[1] == "truncated" for item in persisted)
    assert loop.result.full_content == "final"


@pytest.mark.asyncio
async def test_agent_loop_stream_fallback_and_disconnect_paths():
    fallback_events: list[str] = []

    async def empty_stream(**_kwargs):
        yield ChatStreamChunk(
            id="empty",
            model="model",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def fallback_response(**_kwargs):
        return _response(content="fallback", reasoning="because")

    context = _context(
        streaming=True,
        team_chat_stream=empty_stream,
        team_chat=fallback_response,
        formatter=lambda name, _payload: fallback_events.append(name) or name,
    )
    loop = AgentLoop(context)
    await _consume_loop(loop)
    assert loop.result.full_content == "fallback"
    assert "reasoning_start" in fallback_events

    no_reasoning_events: list[str] = []

    async def no_reasoning_fallback(**_kwargs):
        return _response(content="fallback without reasoning", reasoning=None)

    no_reasoning = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=empty_stream,
            team_chat=no_reasoning_fallback,
            formatter=lambda name, _payload: no_reasoning_events.append(name) or name,
        )
    )
    await _consume_loop(no_reasoning)
    assert no_reasoning.result.full_content == "fallback without reasoning"
    assert "content_delta" in no_reasoning_events

    disconnect_events: list[str] = []

    async def disconnected_stream(**_kwargs):
        yield ChatStreamChunk(
            id="disconnect",
            model="model",
            delta=ChatStreamDelta(content="partial"),
        )

    async def is_disconnected():
        return True

    disconnected = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=disconnected_stream,
            team_chat=AsyncMock(),
            is_disconnected=is_disconnected,
            formatter=lambda name, _payload: disconnect_events.append(name) or name,
        )
    )
    await _consume_loop(disconnected)
    assert disconnected.result.manually_stopped is True
    assert disconnected.result.full_content == ""


@pytest.mark.asyncio
async def test_agent_loop_stop_and_disconnect_barriers_emit_protocol_results(
    monkeypatch,
):
    from app.services import agent_round

    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    checks = 0

    async def stop_at_tool_barrier():
        nonlocal checks
        checks += 1
        return checks >= 2

    def formatter(name, _payload):
        return name

    async def two_tools(**_kwargs):
        return _response(
            content="partial",
            tool_calls=[_tool("read_a", "a"), _tool("read_b", "b")],
        )

    async def build_turn(**_kwargs):
        return ContextTurn(prepared=_prepared())

    stopped = AgentLoop(
        _context(
            team_chat=two_tools,
            build_turn=build_turn,
            stop_requested=stop_at_tool_barrier,
            tool_concurrency=lambda _name: "shared",
            formatter=formatter,
        )
    )
    await _consume_loop(stopped)
    assert stopped.result.manually_stopped is True
    assert stopped.context.created_message_count > 2

    async def disconnected_at_barrier():
        return True

    disconnected = AgentLoop(
        _context(
            team_chat=two_tools,
            build_turn=build_turn,
            is_disconnected=disconnected_at_barrier,
            formatter=formatter,
        )
    )
    await _consume_loop(disconnected)
    assert disconnected.result.manually_stopped is True


@pytest.mark.asyncio
async def test_agent_loop_pause_with_partial_content_preserves_history():
    calls = 0

    async def team_chat(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _response(
                content="paused partial",
                stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
            )
        return _response(content="completed")

    context = _context(
        team_chat=team_chat,
        working_history_override=None,
        max_iterations=3,
    )
    loop = AgentLoop(context)
    await _consume_loop(loop)
    assert calls == 2
    assert context.working_history_override
    assert context.working_history_override[0]["content"] == "paused partial"
    assert loop.result.full_content == "completed"


@pytest.mark.asyncio
async def test_agent_loop_shared_scheduler_converts_unexpected_exception(monkeypatch):
    from app.services import agent_round

    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )

    async def team_chat(**_kwargs):
        return _response(
            content="",
            tool_calls=[_tool("read_a", "a"), _tool("read_b", "b")],
        )

    async def build_turn(**_kwargs):
        return ContextTurn(prepared=_prepared())

    context = _context(
        team_chat=team_chat,
        build_turn=build_turn,
        tool_concurrency=lambda _name: "shared",
        persist_step_per_tool=True,
    )
    loop = AgentLoop(context)

    async def fake_execute(*, tc, **_kwargs):
        if tc.id == "b":
            raise RuntimeError("unexpected")
        return (
            "",
            "result",
            None,
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": {},
                "display_result": "ok",
                "llm_result": "ok",
                "display_name": tc.function.name,
            },
        )

    loop._execute_one_tool = fake_execute
    await _consume_loop(loop)
    assert context.created_message_count > 2


@pytest.mark.asyncio
async def test_agent_loop_pre_turn_deadline_and_missing_model_are_terminal():
    provider = AsyncMock(return_value=_response())
    deadline = AgentLoop(_context(team_chat=provider, deadline_seconds=-1))
    await _consume_loop(deadline)
    provider.assert_not_awaited()
    assert deadline.result.deadline_exceeded is True

    missing_model = AgentLoop(_context(team_chat=None))
    await _consume_loop(missing_model)
    assert missing_model.result.full_content == ""
    assert missing_model.result.max_iterations_reached is False


@pytest.mark.asyncio
async def test_agent_loop_stream_pause_truncation_and_suppressed_events():
    stream_calls = 0
    heartbeat_calls = 0
    events: list[str] = []

    async def heartbeat(_last_event, _interval, _request):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        return True, 1.0

    async def consume_inputs():
        return [SimpleNamespace(content="steer")]

    async def stream(**_kwargs):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            yield ChatStreamChunk(
                id="pause-1",
                model="model",
                delta=ChatStreamDelta(reasoning_content="thinking"),
            )
            yield ChatStreamChunk(
                id="pause-1",
                model="model",
                delta=ChatStreamDelta(content="partial"),
                finish_reason=FinishReason.LENGTH,
                stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return
        yield ChatStreamChunk(
            id="pause-2",
            model="model",
            delta=ChatStreamDelta(content="final"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    def formatter(name, _payload):
        events.append(name)
        return (
            name
            if name in {"reasoning_end", "content_delta", "output_truncated"}
            else None
        )

    loop = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=stream,
            formatter=formatter,
            send_heartbeat_if_needed=heartbeat,
            initial_last_event_time=0.0,
            consume_inputs=consume_inputs,
            max_iterations=3,
        )
    )
    output = await _consume_loop(loop)

    assert stream_calls == 2
    assert heartbeat_calls == 2
    assert loop.result.full_content == "final"
    assert "output_truncated" in output
    assert "heartbeat" not in output
    assert events.count("reasoning_end") == 1


@pytest.mark.asyncio
async def test_agent_loop_stream_fallback_and_finish_event_suppression():
    async def empty_stream(**_kwargs):
        yield ChatStreamChunk(
            id="empty",
            model="model",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def fallback_response(**_kwargs):
        return _response(content="", reasoning="fallback reasoning")

    fallback = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=empty_stream,
            team_chat=fallback_response,
            formatter=lambda _name, _payload: None,
        )
    )
    await _consume_loop(fallback)
    assert fallback.result.full_reasoning == "fallback reasoning"
    assert fallback.result.full_content == ""

    async def reasoning_only_stream(**_kwargs):
        yield ChatStreamChunk(
            id="reasoning-only",
            model="model",
            delta=ChatStreamDelta(reasoning_content="reasoning"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    reasoning_only = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=reasoning_only_stream,
            formatter=lambda _name, _payload: None,
        )
    )
    await _consume_loop(reasoning_only)
    assert reasoning_only.result.full_reasoning == "reasoning"


@pytest.mark.asyncio
async def test_agent_loop_stop_skip_emits_media_with_filtered_events(monkeypatch):
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    async def team_chat(**_kwargs):
        return _response(content="", tool_calls=[_tool("write", "write-1")])

    async def build_turn(**_kwargs):
        return ContextTurn(prepared=_prepared())

    def skipped_tool(tc, *, reason):
        record = {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": {},
            "display_result": reason,
            "llm_result": reason,
            "display_name": tc.function.name,
        }
        return "call", "result", "media", record

    def make_loop(formatter):
        checks = 0

        async def stop_requested():
            nonlocal checks
            checks += 1
            return checks >= 2

        loop = AgentLoop(
            _context(
                team_chat=team_chat,
                build_turn=build_turn,
                stop_requested=stop_requested,
                formatter=formatter,
                persist_step_per_tool=True,
            )
        )
        loop._skipped_tool = skipped_tool
        return loop

    filtered = make_loop(lambda _name, _payload: None)
    await _consume_loop(filtered)
    assert filtered.result.manually_stopped is True

    media_events: list[str] = []

    def media_formatter(name, _payload):
        media_events.append(name)
        return name if name == agent_loop.MEDIA_RESULT else None

    visible_media = make_loop(media_formatter)
    await _consume_loop(visible_media)
    assert visible_media.result.manually_stopped is True
    assert "media_result" in media_events


@pytest.mark.asyncio
async def test_agent_loop_shared_and_sequential_media_paths(monkeypatch):
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    start_a = _tool("read_a", "a")
    start_b = _tool("read_b", "b")
    final_a = _tool("read_a", "a", '{"path":"changed"}')
    final_b = _tool("read_b", "b")
    stream_calls = 0

    async def shared_stream(**_kwargs):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            yield ChatStreamChunk(
                id="shared-1",
                model="model",
                delta=ChatStreamDelta(tool_call_starts=[start_a, start_b]),
            )
            yield ChatStreamChunk(
                id="shared-1",
                model="model",
                delta=ChatStreamDelta(tool_calls=[final_a, final_b]),
                finish_reason=FinishReason.TOOL_CALLS,
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
            return
        yield ChatStreamChunk(
            id="shared-2",
            model="model",
            delta=ChatStreamDelta(content="done"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def fake_shared_execute(*, tc, **_kwargs):
        return (
            "",
            "result",
            "media",
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": {},
                "display_result": "display",
                "llm_result": "llm",
                "display_name": tc.function.name,
            },
        )

    def formatter(name, _payload):
        return None if name == agent_loop.MEDIA_RESULT else name

    shared = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=shared_stream,
            formatter=formatter,
            tool_concurrency=lambda _name: "shared",
            persist_step_per_tool=True,
        )
    )
    shared._build_tool_call_sse = lambda _tc: ""
    shared._execute_one_tool = fake_shared_execute
    await _consume_loop(shared)
    assert shared.result.full_content == "done"

    async def cancelled_execute(*, tc, **_kwargs):
        raise asyncio.CancelledError()

    async def shared_response(**_kwargs):
        return _response(
            content="",
            tool_calls=[_tool("read_a", "cancel-a"), _tool("read_b", "cancel-b")],
        )

    cancelled = AgentLoop(
        _context(
            team_chat=shared_response,
            tool_concurrency=lambda _name: "shared",
            persist_step_per_tool=True,
        )
    )
    cancelled._execute_one_tool = cancelled_execute
    with pytest.raises(asyncio.CancelledError):
        await _consume_loop(cancelled)

    sequential_calls = 0
    media_count = 0

    async def sequential_response(**_kwargs):
        nonlocal sequential_calls
        sequential_calls += 1
        if sequential_calls == 1:
            return _response(
                content="",
                tool_calls=[_tool("one", "one"), _tool("two", "two")],
            )
        return _response(content="finished")

    async def fake_sequential_execute(*, tc, **_kwargs):
        return (
            "",
            "result",
            "media",
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": {},
                "display_result": "display",
                "llm_result": "llm",
                "display_name": tc.function.name,
            },
        )

    def sequential_formatter(name, _payload):
        nonlocal media_count
        if name == agent_loop.MEDIA_RESULT:
            media_count += 1
            return name if media_count == 1 else None
        return name

    sequential = AgentLoop(
        _context(
            team_chat=sequential_response,
            formatter=sequential_formatter,
            tool_concurrency=lambda _name: "exclusive",
            persist_step_per_tool=True,
        )
    )
    sequential._execute_one_tool = fake_sequential_execute
    await _consume_loop(sequential)
    assert sequential.result.full_content == "finished"
    assert media_count == 2


@pytest.mark.asyncio
async def test_agent_loop_cap_and_pause_without_history_initialization(monkeypatch):
    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))
    assert agent_loop._safe_arguments("not-json") == {}

    async def cap_chat(**_kwargs):
        return _response(content="", tool_calls=[_tool("write", "cap")])

    async def execute_tool(_name, _arguments, **_kwargs):
        return "ok"

    cap = AgentLoop(
        _context(
            team_chat=cap_chat,
            execute_tool_call=execute_tool,
            max_iterations=1,
            formatter=lambda name, _payload: name,
            cap_content=lambda: "iteration cap",
        )
    )
    await _consume_loop(cap)
    assert cap.result.max_iterations_reached is True

    pause_calls = 0

    async def pause_chat(**_kwargs):
        nonlocal pause_calls
        pause_calls += 1
        if pause_calls == 1:
            return _response(
                content="paused",
                stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
            )
        return _response(content="finished")

    pause = AgentLoop(
        _context(
            team_chat=pause_chat,
            working_history_override=[],
            max_iterations=2,
        )
    )
    await _consume_loop(pause)
    assert pause.result.full_content == "finished"
    assert pause.context.working_history_override


@pytest.mark.asyncio
async def test_agent_loop_stream_drops_intermediate_events_and_finishes_reasoning():
    async def content_stream(**_kwargs):
        yield ChatStreamChunk(
            id="content",
            model="model",
            delta=ChatStreamDelta(reasoning_content="reasoning"),
        )
        yield ChatStreamChunk(
            id="content",
            model="model",
            delta=ChatStreamDelta(content="first"),
        )
        yield ChatStreamChunk(
            id="content",
            model="model",
            delta=ChatStreamDelta(content="second"),
            finish_reason=FinishReason.LENGTH,
            usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

    dropped = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=content_stream,
            formatter=lambda _name, _payload: None,
        )
    )
    await _consume_loop(dropped)
    assert dropped.result.full_content == "firstsecond"

    async def reasoning_stream(**_kwargs):
        yield ChatStreamChunk(
            id="reasoning",
            model="model",
            delta=ChatStreamDelta(reasoning_content="only reasoning"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    visible_events: list[str] = []

    def visible_formatter(name, _payload):
        visible_events.append(name)
        return name if name == agent_loop.REASONING_END else None

    reasoning_only = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=reasoning_stream,
            formatter=visible_formatter,
        )
    )
    await _consume_loop(reasoning_only)
    assert reasoning_only.result.full_reasoning == "only reasoning"
    assert agent_loop.REASONING_END in visible_events


@pytest.mark.asyncio
async def test_agent_loop_fallback_usage_does_not_record_stream_usage():
    async def empty_stream(**_kwargs):
        yield ChatStreamChunk(
            id="empty-fallback",
            model="model",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    async def fallback_response(**_kwargs):
        return _response(content="fallback content")

    recorded = []

    async def record_usage(**kwargs):
        recorded.append(kwargs)

    def calculate_usage(**_kwargs):
        return 1, 2, 0, 0, 3

    fallback = AgentLoop(
        _context(
            streaming=True,
            team_chat_stream=empty_stream,
            team_chat=fallback_response,
            formatter=lambda _name, _payload: None,
            calculate_usage=calculate_usage,
            record_stream_usage=record_usage,
        )
    )
    await _consume_loop(fallback)
    assert fallback.result.full_content == "fallback content"
    assert recorded == []


@pytest.mark.asyncio
async def test_agent_loop_pause_limit_terminates_repeated_provider_pauses():
    calls = 0

    async def pause_chat(**_kwargs):
        nonlocal calls
        calls += 1
        return _response(
            content="paused",
            stop_details=StopDetails(reason=StopReason.PAUSE_TURN),
        )

    loop = AgentLoop(
        _context(
            team_chat=pause_chat,
            max_iterations=10,
            working_history_override=[],
        )
    )
    await _consume_loop(loop)
    assert calls == AgentLoop.PAUSE_TURN_LIMIT + 1
    assert loop.result.full_content == "paused"
