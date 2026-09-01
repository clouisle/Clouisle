"""Durable chat-stream transport failure contracts.

Provider execution failures are persisted by the AgentRun worker. The HTTP
endpoint only subscribes to the run event stream and passes terminal events
through unchanged.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
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
async def test_stream_passes_through_worker_failure_event(monkeypatch):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat, "start_chat_run", start_run)
    subscribe_calls = []

    async def events(run_id, from_sequence=0):
        subscribe_calls.append((run_id, from_sequence))
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        yield "event: run_start\ndata: {}\n\n"
        yield 'event: error\ndata: {"code": "run_failed", "msg": "provider failed"}\n\n'
        yield 'event: run_end\ndata: {"status": "failed"}\n\n'

    monkeypatch.setattr(agent_run_stream, "sse_events", events)

    response = await chat.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )
    body = await _collect(response)

    assert [line for line in body.splitlines() if line.startswith("event: ")] == [
        "event: run_start",
        "event: error",
        "event: run_end",
    ]
    error_payload = json.loads(
        body.split("event: error\n", 1)[1].split("data: ", 1)[1].split("\n", 1)[0]
    )
    assert error_payload == {"code": "run_failed", "msg": "provider failed"}
    start_run.assert_awaited_once()
    assert subscribe_calls == [(started["data"].run_id, 0)]


@pytest.mark.asyncio
async def test_stream_does_not_subscribe_when_run_start_fails(monkeypatch):
    from app.services import agent_run_stream

    start_run = AsyncMock(side_effect=RuntimeError("enqueue failed"))
    subscribe = AsyncMock()
    monkeypatch.setattr(chat, "start_chat_run", start_run)
    monkeypatch.setattr(agent_run_stream, "sse_events", subscribe)

    with pytest.raises(RuntimeError, match="enqueue failed"):
        await chat.chat_stream(
            uuid4(),
            ChatRequest(message="hello"),
            SimpleNamespace(),
            (SimpleNamespace(id=uuid4()), None),
        )

    subscribe.assert_not_called()
