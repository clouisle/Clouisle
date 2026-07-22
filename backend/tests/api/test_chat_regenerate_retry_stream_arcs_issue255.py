from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import ContextLengthError
from app.llm.types import ChatStreamChunk, ChatStreamDelta, FinishReason
from tests.api.test_chat_regenerate_outer_loop_companion_issue255 import (
    collect,
    prepared,
    setup_regeneration,
)


@pytest.mark.anyio
async def test_regenerate_reactive_retry_stream_emits_all_chunk_kinds(monkeypatch):
    state = await setup_regeneration(monkeypatch)
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(return_value=prepared())
    )
    monkeypatch.setattr(
        chat, "retry_prepare_model_context", AsyncMock(return_value=prepared("retried"))
    )
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        Mock(side_effect=[(None, None), ("compression-start", "compression-end")]),
    )
    calls = 0

    async def chunks(_stream, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ContextLengthError
        for chunk in (
            ChatStreamChunk(
                id="reasoning-1",
                model="unit",
                delta=ChatStreamDelta(reasoning_content="think"),
            ),
            ChatStreamChunk(
                id="reasoning-2",
                model="unit",
                delta=ChatStreamDelta(reasoning_content=" more"),
            ),
            ChatStreamChunk(
                id="content-1",
                model="unit",
                delta=ChatStreamDelta(content="answer"),
            ),
            ChatStreamChunk(
                id="content-2",
                model="unit",
                delta=ChatStreamDelta(content=" done"),
                finish_reason=FinishReason.LENGTH,
            ),
        ):
            yield chunk

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert "compression-startcompression-end" in events
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: content_delta" in events
    assert "event: output_truncated" in events
    assert state.created.content == "answer done"
