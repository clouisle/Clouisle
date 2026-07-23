import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import chat
from app.api.v1.endpoints.chat_helpers import StreamIdleTimeoutError
from app.llm.errors import ContextLengthError, QuotaExceededError
from app.llm.types import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message,
    ToolCall,
)
from app.schemas.response import ResponseCode
from tests.api import test_chat_edit_stream_issue255 as edit_support


async def collect(response):
    return "".join([item async for item in response.body_iterator])


@pytest.mark.anyio
async def test_edit_stream_target_arcs_stops_on_failed_heartbeat(monkeypatch):
    state = await edit_support.setup_edit(monkeypatch)
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(False, 0))
    )

    events = await collect(state.response)

    assert "event: message_start" in events
    assert "event: message_end" not in events
    assert state.assistant.is_manually_stopped is True
    state.assistant.save.assert_awaited_once()
    assert chat.activate_conversation_branch.await_count == 2


@pytest.mark.anyio
async def test_edit_stream_target_arcs_retries_context_with_compression(monkeypatch):
    state = await edit_support.setup_edit(monkeypatch)
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="retried")], compression=object()
    )
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(side_effect=ContextLengthError())
    )
    retry = AsyncMock(return_value=prepared)
    monkeypatch.setattr(chat, "retry_prepare_model_context", retry)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        lambda **_kwargs: ("compression-start\n", "compression-end\n"),
    )
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 2**62))
    )

    async def chunks(_stream, **_kwargs):
        yield ChatStreamChunk(
            id="done",
            model="stub/unit-model",
            delta=ChatStreamDelta(reasoning_content="thinking"),
            finish_reason=FinishReason.LENGTH,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert ": heartbeat" in events
    assert "compression-start" in events
    assert "compression-end" in events
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: output_truncated" in events
    retry.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "preserved", "expected"),
    [
        (QuotaExceededError(quota_type="daily"), True, "model_quota_exceeded"),
        (QuotaExceededError(quota_type="monthly"), False, "model_quota_exceeded"),
        (StreamIdleTimeoutError(), True, "stream_timeout_exceeded"),
        (StreamIdleTimeoutError(), False, "stream_timeout_exceeded"),
        (TimeoutError(), False, "stream_timeout_exceeded"),
        (RuntimeError("boom"), True, "unknown_error"),
        (RuntimeError("boom"), False, "unknown_error"),
    ],
)
async def test_edit_stream_target_arcs_error_cleanup_matrix(
    monkeypatch, error, preserved, expected
):
    state = await edit_support.setup_edit(monkeypatch)
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(side_effect=error))
    persist = AsyncMock(return_value=preserved)
    monkeypatch.setattr(chat, "persist_partial_round_error", persist)

    events = await collect(state.response)

    assert f'"msg": "{expected}"' in events
    assert f'"code": {ResponseCode.UNKNOWN_ERROR}' in events or (
        "model_quota_exceeded" in events
        and f'"code": {ResponseCode.MODEL_QUOTA_EXCEEDED}' in events
    )
    if preserved:
        state.cleanup_query.delete.assert_not_awaited()
        assert chat.activate_conversation_branch.await_count == 2
    else:
        state.cleanup_query.delete.assert_awaited_once()
        state.cleanup_query.update.assert_awaited_once_with(is_active=False)
        assert chat.activate_conversation_branch.await_count == 2


@pytest.mark.anyio
@pytest.mark.parametrize("with_content", [False, True])
async def test_edit_stream_target_arcs_cancelled_cleanup(monkeypatch, with_content):
    state = await edit_support.setup_edit(monkeypatch)
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))

    async def chunks(_stream, **_kwargs):
        if with_content:
            yield ChatStreamChunk(
                id="partial",
                model="stub/unit-model",
                delta=ChatStreamDelta(content="partial"),
            )
        raise asyncio.CancelledError
        yield  # pragma: no cover

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert "event: message_end" not in events
    if with_content:
        state.assistant.save.assert_awaited_once()
        state.cleanup_query.delete.assert_not_awaited()
    else:
        state.assistant.save.assert_not_awaited()
        state.cleanup_query.delete.assert_awaited_once()
        state.cleanup_query.update.assert_awaited_once_with(is_active=False)


@pytest.mark.anyio
@pytest.mark.parametrize("disconnect_after_execute", [False, True])
async def test_edit_stream_target_arcs_disconnects_around_tool_execution(
    monkeypatch, disconnect_after_execute
):
    real_namespace = SimpleNamespace
    disconnect = AsyncMock(
        side_effect=[False, False, True] if disconnect_after_execute else [False, True]
    )

    def namespace(*args, **kwargs):
        if not args and set(kwargs) == {"is_disconnected"}:
            return real_namespace(is_disconnected=disconnect)
        return real_namespace(*args, **kwargs)

    monkeypatch.setattr(edit_support, "SimpleNamespace", namespace)
    state = await edit_support.setup_edit(monkeypatch)
    prepared = real_namespace(
        messages=[Message(role="user", content="prepared")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments="{}"),
    )

    async def chunks(_stream, **_kwargs):
        yield ChatStreamChunk(
            id="tool",
            model="stub/unit-model",
            delta=ChatStreamDelta(tool_calls=[tool_call]),
            finish_reason=FinishReason.TOOL_CALLS,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )
    execute = AsyncMock(return_value="result")
    monkeypatch.setattr(chat, "execute_tool_call", execute)
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )

    events = await collect(state.response)

    assert "event: message_end" not in events
    state.assistant.save.assert_awaited_once()
    if disconnect_after_execute:
        execute.assert_awaited_once()
    else:
        execute.assert_not_awaited()
