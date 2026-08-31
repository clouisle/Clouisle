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


async def _stream_with_events(monkeypatch, event_lines):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat, "start_chat_run", start_run)

    async def events(run_id, from_sequence=0):
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        for event in event_lines:
            yield event

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )
    return await _collect_stream(response), start_run


@pytest.mark.asyncio
async def test_stream_passes_through_ordered_compression_reasoning_content_and_length(
    monkeypatch,
):
    body, start_run = await _stream_with_events(
        monkeypatch,
        [
            "event: run_start\ndata: {}\n\n",
            'event: compression_start\ndata: {"stage": "proactive"}\n\n',
            "event: reasoning_start\ndata: {}\n\n",
            'event: reasoning_delta\ndata: {"delta": "think"}\n\n',
            "event: reasoning_end\ndata: {}\n\n",
            'event: content_delta\ndata: {"delta": "answer"}\n\n',
            'event: output_truncated\ndata: {"reason": "length"}\n\n',
            "event: compression_end\ndata: {}\n\n",
            "event: message_end\ndata: {}\n\n",
            "event: run_end\ndata: {}\n\n",
        ],
    )

    assert _event_names(body) == [
        "run_start",
        "compression_start",
        "reasoning_start",
        "reasoning_delta",
        "reasoning_end",
        "content_delta",
        "output_truncated",
        "compression_end",
        "message_end",
        "run_end",
    ]
    assert 'data: {"delta": "think"}' in body
    assert 'data: {"delta": "answer"}' in body
    assert 'data: {"reason": "length"}' in body
    start_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_passes_through_tool_and_media_events(monkeypatch):
    body, _start_run = await _stream_with_events(
        monkeypatch,
        [
            "event: run_start\ndata: {}\n\n",
            'event: tool_call\ndata: {"tool_call_id": "call-1", "arguments": {}}\n\n',
            'event: tool_call\ndata: {"tool_call_id": "call-1", "arguments": {"query": "x"}}\n\n',
            'event: tool_result\ndata: {"tool_call_id": "call-1", "result": "ok"}\n\n',
            'event: media_result\ndata: {"kind": "media.video", "task_id": "vid-1"}\n\n',
            "event: message_end\ndata: {}\n\n",
            "event: run_end\ndata: {}\n\n",
        ],
    )

    assert body.count("event: tool_call\n") == 2
    assert body.index('"arguments": {}') < body.index('"arguments": {"query": "x"}')
    assert "event: tool_result" in body
    assert "event: media_result" in body
