from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent_run import AgentRunStatus
from app.schemas.agent import ChatRequest, RunStartOut
from app.schemas.response import BusinessError, ResponseCode


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


async def _collect_stream(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


def _event_names(body: str) -> list[str]:
    return [
        line.split(": ", 1)[1]
        for line in body.splitlines()
        if line.startswith("event: ")
    ]


@pytest.mark.asyncio
async def test_nonstream_interrupted_run_maps_to_business_error():
    run = SimpleNamespace(
        status=AgentRunStatus.INTERRUPTED,
        canonical_message_id=None,
    )

    with pytest.raises(BusinessError) as exc_info:
        await chat._build_non_stream_run_response(run)

    assert exc_info.value.code == ResponseCode.UNKNOWN_ERROR
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_chat_stream_passes_through_reasoning_content_and_usage(monkeypatch):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat, "start_chat_run", start_run)

    async def events(run_id, from_sequence=0):
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        yield "event: run_start\ndata: {}\n\n"
        yield "event: reasoning_start\ndata: {}\n\n"
        yield 'event: reasoning_delta\ndata: {"delta": "thinking"}\n\n'
        yield "event: reasoning_end\ndata: {}\n\n"
        yield 'event: content_delta\ndata: {"delta": "answer"}\n\n'
        yield (
            "event: message_end\n"
            'data: {"usage": {"prompt_tokens": 29, "completion_tokens": 11}}\n\n'
        )

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )

    body = await _collect_stream(response)

    assert _event_names(body) == [
        "run_start",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "content_delta",
        "message_end",
    ]
    assert 'data: {"delta": "thinking"}' in body
    assert 'data: {"delta": "answer"}' in body
    assert '"prompt_tokens": 29' in body
    start_run.assert_awaited_once()
