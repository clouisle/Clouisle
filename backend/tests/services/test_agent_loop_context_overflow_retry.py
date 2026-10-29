"""Provider-side context-overflow recovery in the shared AgentLoop.

Recovery is deliberately narrow: only an unambiguously classified provider
*input* overflow is retried, only before any provider output reached the
client, and only with a strictly smaller request view. These tests exercise
both the streaming and non-streaming request shapes.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError, ProviderError
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
from app.services.agent_loop import (
    CONTEXT_OVERFLOW_MAX_RETRIES,
    CONTEXT_OVERFLOW_OMISSION_NOTICE,
    CONTEXT_OVERFLOW_OMISSION_PREFIX,
    AgentLoop,
    AgentLoopContext,
    ContextTurn,
    _is_provider_context_overflow,
    _reduce_history_messages,
)

CURRENT = "current request"
BIG = "prior context detail " * 40
OVERFLOW = ContextLengthError(
    message=(
        "This model's maximum context length is 4096 tokens. "
        "However, your messages resulted in 8192 tokens."
    )
)


def _response(*, content="", tool_calls=None):
    return ChatResponse(
        id="r",
        model="m",
        content=content,
        tool_calls=tool_calls,
        finish_reason=(FinishReason.TOOL_CALLS if tool_calls else FinishReason.STOP),
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _call(call_id: str, name: str = "read_file") -> ToolCall:
    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments=json.dumps({"path": "x"})),
    )


def _messages():
    return [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question one"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer one"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question two"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer two"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question three"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer three"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question four"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer four"),
        LLMMessage(role=MessageRole.ASSISTANT, content="", tool_calls=[_call("c-old")]),
        LLMMessage(
            role=MessageRole.TOOL, content="old tool result", tool_call_id="c-old"
        ),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]


def _long_messages():
    messages = [LLMMessage(role=MessageRole.SYSTEM, content="system")]
    for index in range(6):
        messages.append(
            LLMMessage(role=MessageRole.USER, content=f"{BIG} question {index}")
        )
        messages.append(
            LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} answer {index}")
        )
    messages.append(LLMMessage(role=MessageRole.USER, content=CURRENT))
    return messages


_UNSET = object()


def _prepared(
    messages=None,
    compression=None,
    input_budget=90000,
    protected_indexes=_UNSET,
):
    resolved = list(messages if messages is not None else _messages())
    if protected_indexes is _UNSET:
        # Model chat_context: the current user instruction is protected.
        protected_indexes = set()
        for index in range(len(resolved) - 1, -1, -1):
            role = getattr(resolved[index].role, "value", resolved[index].role)
            if role == "user":
                protected_indexes = {index}
                break
    return SimpleNamespace(
        messages=resolved,
        token_budget=SimpleNamespace(input_budget=input_budget),
        compression=compression,
        protected_indexes=set(protected_indexes or ()),
    )


def _context(**overrides):
    context = AgentLoopContext(
        agent=SimpleNamespace(
            id=uuid4(), team_id=uuid4(), context_compression_config={"enabled": True}
        ),
        conversation=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        user_message=CURRENT,
        model_id="m",
        tokenizer_model_id=None,
        model_provider="p",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        model_used="m",
        max_iterations=1,
        streaming=False,
        working_history_override=[],
        round_id=uuid4(),
        formatter=None,
    )
    for key, value in overrides.items():
        setattr(context, key, value)
    return context


async def _build_turn(**kwargs):
    return ContextTurn(
        prepared=_prepared(
            input_budget=54321,
            compression=SimpleNamespace(
                stage="none",
                before_tokens=0,
                after_tokens=0,
                input_budget=54321,
                actions=[],
            ),
        )
    )


def _record_formatter(events):
    def formatter(name, payload):
        events.append((name, payload))
        return f"event: {name}\n"

    return formatter


def _roles(messages):
    return [getattr(m.get("role"), "value", m.get("role")) for m in messages]


async def _drain(loop):
    outputs = []
    async for output in loop.run():
        if output:
            outputs.append(output)
    return outputs


@pytest.mark.asyncio
async def test_non_stream_retries_once_with_smaller_view_and_preserves_instruction():
    calls = []
    execute_tool_call = AsyncMock()

    async def _chat(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    context = _context(
        build_turn=_build_turn,
        team_chat=_chat,
        execute_tool_call=execute_tool_call,
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert loop.result.full_content == "recovered"
    assert len(calls) == 2
    first, retried = calls
    assert len(retried) < len(first)
    assert _roles(retried)[0] == "system"
    assert [m["content"] for m in retried].count(CONTEXT_OVERFLOW_OMISSION_NOTICE) == 1
    assert retried[1]["content"] == CONTEXT_OVERFLOW_OMISSION_NOTICE
    assert retried[-1]["content"] == CURRENT
    # Tool-result history is unrecoverable from the provider view, so it is
    # protected and its exchange stays whole.
    retried_roles = _roles(retried)
    assert "tool" in retried_roles
    tool_positions = [
        position for position, role in enumerate(retried_roles) if role == "tool"
    ]
    for position in tool_positions:
        assert retried_roles[position - 1] == "assistant"
        assert retried[position - 1].get("tool_calls")
    # The current user instruction survives verbatim.
    assert [m for m in retried if _roles([m])[0] == "user"][-1]["content"] == CURRENT
    # A failed provider attempt never executes tools.
    execute_tool_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_retries_before_output_and_emits_compression_events():
    calls = []
    events = []

    async def _stream(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            raise OVERFLOW
        yield ChatStreamChunk(
            id="r",
            model="m",
            delta=ChatStreamDelta(content="recovered"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        )

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
        formatter=_record_formatter(events),
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert loop.result.full_content == "recovered"
    assert len(calls) == 2
    assert len(calls[1]) < len(calls[0])
    names = [name for name, _payload in events]
    assert names.count("compression_start") == 1
    assert names.count("compression_end") == 1
    assert names.count("content_delta") == 1
    assert names.index("compression_start") < names.index("compression_end")
    assert names.index("compression_end") < names.index("content_delta")
    end_payload = next(payload for name, payload in events if name == "compression_end")
    meta = end_payload["compression"]
    assert meta.stage == "fallback"
    assert "provider_overflow_retry" in meta.actions
    # The budget comes from PreparedModelContext, not a hardcoded reserve.
    assert meta.input_budget == 54321


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_any_chunk_was_received():
    calls = []
    events = []

    async def _stream(**kwargs):
        calls.append(kwargs)
        # Even a usage-only chunk means the provider stream has started.
        yield ChatStreamChunk(
            id="r",
            model="m",
            delta=ChatStreamDelta(),
            usage=Usage(prompt_tokens=8, completion_tokens=0, total_tokens=8),
        )
        raise OVERFLOW

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
        formatter=_record_formatter(events),
    )
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)

    assert len(calls) == 1
    assert [name for name, _payload in events if name.startswith("compression")] == []


@pytest.mark.asyncio
async def test_stream_fallback_overflow_is_retried_before_output():
    chat_calls = []
    events = []

    async def _stream(**kwargs):
        if False:  # pragma: no cover - completes without a chunk
            yield None

    async def _chat(**kwargs):
        chat_calls.append(list(kwargs["messages"]))
        if len(chat_calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
        team_chat=_chat,
        formatter=_record_formatter(events),
    )
    loop = AgentLoop(context)
    await _drain(loop)

    # The empty stream emitted nothing, so the fallback may retry.
    assert loop.result.full_content == "recovered"
    assert len(chat_calls) == 2
    assert len(chat_calls[1]) < len(chat_calls[0])
    names = [name for name, _payload in events]
    assert names.count("compression_end") == 1
    assert names.count("content_delta") == 1


@pytest.mark.asyncio
async def test_fallback_after_stream_retry_replaces_notice_by_index():
    stream_calls = 0
    chat_calls = []

    async def _stream(**kwargs):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            raise OVERFLOW
        if False:  # second attempt completes without a chunk
            yield None

    async def _chat(**kwargs):
        chat_calls.append(list(kwargs["messages"]))
        if len(chat_calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
        team_chat=_chat,
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert stream_calls == 2
    assert len(chat_calls) == 2
    contents = [message.get("content") for message in chat_calls[1]]
    assert contents.count(CONTEXT_OVERFLOW_OMISSION_NOTICE) == 1
    assert len(chat_calls[1]) < len(chat_calls[0])


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_content_was_emitted():
    calls = []

    async def _stream(**kwargs):
        calls.append(kwargs)
        yield ChatStreamChunk(
            id="r", model="m", delta=ChatStreamDelta(content="partial")
        )
        raise OVERFLOW

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
    )
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_reasoning_was_emitted():
    calls = []

    async def _stream(**kwargs):
        calls.append(kwargs)
        yield ChatStreamChunk(
            id="r", model="m", delta=ChatStreamDelta(reasoning_content="thinking")
        )
        raise OVERFLOW

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
    )
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unrelated_provider_error_is_not_retried():
    calls = []

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise ProviderError(message="upstream exploded")

    context = _context(build_turn=_build_turn, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ProviderError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_ambiguous_context_error_is_not_treated_as_input_overflow():
    calls = []
    ambiguous = ContextLengthError(message="max_tokens is too large for this model")

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise ambiguous

    context = _context(build_turn=_build_turn, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_loose_token_max_mapping_is_not_treated_as_input_overflow():
    calls = []
    loose = ContextLengthError(
        message="token count exceeds max", max_tokens=100, actual_tokens=200
    )

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise loose

    context = _context(build_turn=_build_turn, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_local_preflight_guard_is_not_retried():
    calls = []
    local = ContextLengthError(
        message="Context length exceeded: protected payload over budget",
        details={"retryable": False, "reason": "protected_payload_over_budget"},
    )

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise local

    context = _context(build_turn=_build_turn, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_disabled_compression_disables_overflow_recovery():
    calls = []

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise OVERFLOW

    context = _context(build_turn=_build_turn, team_chat=_chat)
    context.agent.context_compression_config = {"enabled": False}
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retries_are_bounded_and_each_one_reduces_the_view():
    calls = []

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=_long_messages()))

    async def _chat(**kwargs):
        calls.append(list(kwargs["messages"]))
        raise OVERFLOW

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)

    assert len(calls) == 1 + CONTEXT_OVERFLOW_MAX_RETRIES
    for earlier, later in zip(calls, calls[1:]):
        assert len(later) < len(earlier)
    # The loop-owned notice is replaced by index, never accumulated.
    for call in calls[1:]:
        assert [m.get("content") for m in call].count(
            CONTEXT_OVERFLOW_OMISSION_NOTICE
        ) == 1


@pytest.mark.asyncio
async def test_empty_stream_fallback_shares_overflow_retry_budget():
    stream_calls = []
    fallback_calls = []

    async def _empty_stream():
        if False:
            yield None

    def _stream(**kwargs):
        stream_calls.append(kwargs)
        if len(stream_calls) == 1:
            raise OVERFLOW
        return _empty_stream()

    async def _fallback(**kwargs):
        fallback_calls.append(kwargs)
        raise OVERFLOW

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=_long_messages()))

    loop = AgentLoop(
        _context(
            build_turn=_build,
            streaming=True,
            team_chat_stream=_stream,
            team_chat=_fallback,
        )
    )
    with pytest.raises(ContextLengthError):
        await _drain(loop)

    assert len(stream_calls) + len(fallback_calls) == 2 + CONTEXT_OVERFLOW_MAX_RETRIES
    assert len(stream_calls) == 2
    assert len(fallback_calls) == CONTEXT_OVERFLOW_MAX_RETRIES


@pytest.mark.asyncio
async def test_protected_active_round_instructions_survive_reduction():
    calls = []
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content="original task"),
        LLMMessage(role=MessageRole.USER, content="steering"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer one"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question one"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer two"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question two"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer three"),
        LLMMessage(role=MessageRole.USER, content=f"{BIG} old question three"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer four"),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]

    async def _build(**kwargs):
        return ContextTurn(
            prepared=_prepared(messages=messages, protected_indexes={1, 2, 10})
        )

    async def _chat(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    await _drain(loop)

    retried = calls[1]
    contents = [
        getattr(message.get("content"), "value", message.get("content"))
        for message in retried
    ]
    assert "original task" in contents
    assert "steering" in contents
    assert retried[-1]["content"] == CURRENT
    assert len(retried) < len(messages)


@pytest.mark.asyncio
async def test_no_reducible_history_means_no_retry():
    calls = []
    minimal = [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=minimal))

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise OVERFLOW

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


class _Discovery:
    def __init__(self):
        self.loaded = ["optional_tool"]
        self.turn_calls = 0
        self.removed_calls = 0

    def tools_for_turn(self):
        self.turn_calls += 1
        return ["core_tool", *self.loaded]

    async def reduce_for_retry(self):
        self.removed_calls += 1
        removed = list(self.loaded)
        self.loaded.clear()
        return removed


@pytest.mark.asyncio
async def test_first_retry_sheds_optional_tool_schemas_and_recomputes_the_list():
    discovery = _Discovery()
    calls = []
    events = []

    async def _chat(**kwargs):
        calls.append({"messages": list(kwargs["messages"]), "tools": kwargs["tools"]})
        if len(calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    minimal = [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=minimal))

    context = _context(
        build_turn=_build,
        team_chat=_chat,
        tool_discovery=discovery,
        formatter=_record_formatter(events),
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert discovery.removed_calls == 1
    assert calls[0]["tools"] == ["core_tool", "optional_tool"]
    assert calls[1]["tools"] == ["core_tool"]
    end_payload = next(payload for name, payload in events if name == "compression_end")
    assert "provider_overflow_tool_schemas_shed" in end_payload["compression"].actions


@pytest.mark.asyncio
async def test_retry_never_reexecutes_an_already_completed_tool(monkeypatch):
    from app.services import agent_round

    monkeypatch.setattr(
        agent_round, "persist_assistant_step", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(agent_round, "persist_tool_result", AsyncMock(return_value=2))

    tool_runs = 0
    provider_calls = 0

    async def _tool(tool_name, arguments, **kwargs):
        nonlocal tool_runs
        tool_runs += 1
        return json.dumps({"result": "ok"})

    async def _build(**kwargs):
        history = kwargs.get("history_override") or []
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content="system"),
            LLMMessage(role=MessageRole.USER, content=f"{BIG} older question"),
            LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} older answer"),
            LLMMessage(role=MessageRole.USER, content=CURRENT),
        ]
        for entry in history:
            if not isinstance(entry, dict):
                continue
            role = entry.get("role")
            if role == "assistant":
                calls = [
                    ToolCall(
                        id=item["id"],
                        function=FunctionCall(
                            name=item.get("name", ""),
                            arguments=json.dumps(item.get("arguments") or {}),
                        ),
                    )
                    for item in entry.get("tool_calls") or []
                ]
                messages.append(
                    LLMMessage(
                        role=MessageRole.ASSISTANT,
                        content=entry.get("content") or "",
                        tool_calls=calls or None,
                    )
                )
            else:
                messages.append(
                    LLMMessage(
                        role=MessageRole.TOOL,
                        content=entry.get("content") or "",
                        tool_call_id=entry.get("tool_call_id"),
                        name=entry.get("tool_name"),
                    )
                )
        return ContextTurn(prepared=_prepared(messages=messages))

    async def _chat(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            return _response(tool_calls=[_call("c-live")])
        if provider_calls == 2:
            raise OVERFLOW
        return _response(content="final")

    context = _context(
        max_iterations=3,
        build_turn=_build,
        team_chat=_chat,
        execute_tool_call=_tool,
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert tool_runs == 1
    assert loop.result.full_content == "final"
    assert provider_calls == 3


def test_classifier_requires_unambiguous_provider_context_wording():
    assert _is_provider_context_overflow(OVERFLOW) is True
    assert _is_provider_context_overflow(ProviderError(message="x")) is False
    assert (
        _is_provider_context_overflow(
            ContextLengthError(
                message="context length exceeded",
                details={"retryable": False},
            )
        )
        is False
    )
    assert (
        _is_provider_context_overflow(
            ContextLengthError(
                message="context length exceeded",
                details={"reason": "context_summary_did_not_fit"},
            )
        )
        is False
    )
    wrong_code = ContextLengthError(message="maximum context length")
    wrong_code.code = "provider_error"
    assert _is_provider_context_overflow(wrong_code) is False
    assert (
        _is_provider_context_overflow(
            ContextLengthError(message="token count exceeds max")
        )
        is False
    )


@pytest.mark.asyncio
async def test_all_protected_view_fails_closed_without_history_reduction():
    messages = _long_messages()
    calls = []

    async def _build(**kwargs):
        return ContextTurn(
            prepared=_prepared(
                messages=messages, protected_indexes=set(range(len(messages)))
            )
        )

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise OVERFLOW

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)

    # A fully protected view cannot prove which instructions are current
    # beyond protection itself; history is left untouched.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_protection_evidence_fails_closed():
    messages = _long_messages()
    calls = []

    async def _build(**kwargs):
        return ContextTurn(
            prepared=_prepared(messages=messages, protected_indexes=set())
        )

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise OVERFLOW

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_synchronous_stream_factory_overflow_is_retried():
    calls = []

    async def _one_chunk():
        yield ChatStreamChunk(
            id="r",
            model="m",
            delta=ChatStreamDelta(content="recovered"),
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        )

    def _stream(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise OVERFLOW
        return _one_chunk()

    context = _context(
        streaming=True,
        build_turn=_build_turn,
        team_chat_stream=_stream,
    )
    loop = AgentLoop(context)
    await _drain(loop)

    assert loop.result.full_content == "recovered"
    assert len(calls) == 2


class _StaticDiscovery:
    def tools_for_turn(self):
        return ["core"]

    async def reduce_for_retry(self):
        return ["ghost"]


@pytest.mark.asyncio
async def test_unchanged_tool_list_is_not_treated_as_reduction():
    calls = []
    minimal = [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=minimal))

    async def _chat(**kwargs):
        calls.append(kwargs)
        raise OVERFLOW

    context = _context(
        build_turn=_build,
        team_chat=_chat,
        tool_discovery=_StaticDiscovery(),
    )
    loop = AgentLoop(context)
    with pytest.raises(ContextLengthError):
        await _drain(loop)
    assert len(calls) == 1


def test_summary_user_instructions_and_tool_results_are_never_dropped():
    from app.services.chat_context import CONTEXT_SUMMARY_PREFIX

    summary = f"{CONTEXT_SUMMARY_PREFIX}\n\nretain safety constraints"
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": summary},
        {"role": "user", "content": "original instruction"},
        {"role": "assistant", "content": "old answer one"},
        {"role": "user", "content": "follow-up instruction"},
        {"role": "assistant", "content": "old answer two"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "f", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "side effect result", "tool_call_id": "c1"},
        {"role": "user", "content": CURRENT},
    ]
    reduced, dropped, _protected, _notice = _reduce_history_messages(
        messages, drop_all=True, protected_indexes={8}
    )
    contents = [message.get("content") for message in reduced]
    assert summary in contents
    assert "original instruction" in contents
    assert "follow-up instruction" in contents
    assert "side effect result" in contents
    assert contents[-1] == CURRENT
    # Only plain assistant text is removable.
    assert dropped == 2
    assert "old answer one" not in contents
    assert "old answer two" not in contents


def test_user_text_matching_notice_prefix_is_never_deleted():
    tricky = f"{CONTEXT_OVERFLOW_OMISSION_PREFIX} real user instruction"
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": tricky},
        {"role": "assistant", "content": "old answer one"},
        {"role": "assistant", "content": "old answer two"},
        {"role": "assistant", "content": "old answer three"},
        {"role": "assistant", "content": "old answer four"},
        {"role": "user", "content": CURRENT},
    ]
    first, dropped, protected, notice_index = _reduce_history_messages(
        messages, drop_all=False, protected_indexes={6}
    )
    first_contents = [message.get("content") for message in first]
    assert dropped == 2
    assert notice_index == 1
    assert tricky in first_contents
    assert first_contents.count(CONTEXT_OVERFLOW_OMISSION_NOTICE) == 1

    # The second reduction replaces the tracked notice by index, never by text.
    second, dropped_again, _protected, second_notice = _reduce_history_messages(
        first,
        drop_all=False,
        protected_indexes=protected,
        notice_index=notice_index,
    )
    second_contents = [message.get("content") for message in second]
    assert dropped_again == 1
    assert second_notice == 1
    assert tricky in second_contents
    assert second_contents.count(CONTEXT_OVERFLOW_OMISSION_NOTICE) == 1
    assert len(second) < len(first)


@pytest.mark.asyncio
async def test_retry_preserves_user_text_matching_notice_prefix():
    tricky = f"{CONTEXT_OVERFLOW_OMISSION_PREFIX} real user instruction"
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content="system"),
        LLMMessage(role=MessageRole.USER, content=tricky),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer one"),
        LLMMessage(role=MessageRole.ASSISTANT, content=f"{BIG} old answer two"),
        LLMMessage(role=MessageRole.USER, content=CURRENT),
    ]
    calls = []

    async def _build(**kwargs):
        return ContextTurn(prepared=_prepared(messages=messages))

    async def _chat(**kwargs):
        calls.append(list(kwargs["messages"]))
        if len(calls) == 1:
            raise OVERFLOW
        return _response(content="recovered")

    context = _context(build_turn=_build, team_chat=_chat)
    loop = AgentLoop(context)
    await _drain(loop)

    assert len(calls) == 2
    assert any(message.get("content") == tricky for message in calls[1])


def test_reduction_keeps_assistant_tool_calls_and_results_together():
    payloads = [m.model_dump(exclude_none=True) for m in _messages()]
    reduced, dropped, protected, notice_index = _reduce_history_messages(
        payloads, drop_all=True, protected_indexes={11}
    )
    assert dropped == 4
    assert notice_index == 1
    roles = _roles(reduced)
    assert roles == [
        "system",
        "user",
        "user",
        "user",
        "user",
        "user",
        "assistant",
        "tool",
        "user",
    ]
    assert reduced[1]["content"] == CONTEXT_OVERFLOW_OMISSION_NOTICE
    assert protected == {8}
    # The tool exchange stays whole and adjacent; its result is preserved.
    assert reduced[6]["tool_calls"][0]["id"] == "c-old"
    assert reduced[7]["tool_call_id"] == "c-old"
    # Every user instruction (including the current one) is preserved verbatim.
    user_contents = [
        message["content"]
        for message in reduced
        if getattr(message.get("role"), "value", message.get("role")) == "user"
    ]
    assert CURRENT in user_contents
    assert f"{BIG} old question one" in user_contents

    # No protection evidence means no reduction at all (fail closed).
    unchanged, dropped_without_mask, _, _ = _reduce_history_messages(
        payloads, drop_all=True
    )
    assert dropped_without_mask == 0
    assert unchanged == payloads
