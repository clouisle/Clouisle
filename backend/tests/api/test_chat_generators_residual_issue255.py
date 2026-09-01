from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.responses import StreamingResponse

from app.api.v1.endpoints import chat as chat_api
from app.schemas.agent import ChatRequest, RunStartOut


def _started() -> dict:
    return {
        "data": RunStartOut(
            run_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            status="queued",
            stream_url="/agents/run/chat/runs/run/stream",
        )
    }


async def _collect(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_chat_stream_uses_durable_run_event_generator(monkeypatch):
    """The stream endpoint subscribes to durable events, not a loop body."""
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat_api, "start_chat_run", start_run)

    async def events(run_id, from_sequence=0):
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        yield "event: run_start\ndata: {}\n\n"
        yield "event: run_end\ndata: {}\n\n"

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat_api.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )

    assert isinstance(response, StreamingResponse)
    assert await _collect(response) == (
        "event: run_start\ndata: {}\n\nevent: run_end\ndata: {}\n\n"
    )
    start_run.assert_awaited_once()
