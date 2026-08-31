from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_api
from app.models.agent_run import AgentRunMode, AgentRunStatus
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


def test_run_usage_mapping():
    """The non-stream response adapter collapses worker token usage."""
    message = SimpleNamespace(
        token_usage={
            "prompt": 7,
            "completion": 3,
            "cache_read": 1,
            "total_input": 8,
        }
    )
    assert chat_api._run_usage(message) == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
        "cache_read_tokens": 1,
        "cache_creation_tokens": 0,
        "total_input_tokens": 8,
    }


@pytest.mark.asyncio
async def test_chat_nonstream_queues_run_and_adapts_canonical_response(monkeypatch):
    started = _started()
    run = SimpleNamespace(id=started["data"].run_id, status=AgentRunStatus.COMPLETED)
    legacy_response = {"data": {"message": {"content": "answer"}}}
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    build_response = AsyncMock(return_value=legacy_response)
    monkeypatch.setattr(chat_api, "_enqueue_durable_chat_run", enqueue)
    monkeypatch.setattr(chat_api, "_wait_for_agent_run", wait)
    monkeypatch.setattr(chat_api, "_build_non_stream_run_response", build_response)

    result = await chat_api.chat(
        uuid4(),
        ChatRequest(message="hello"),
        (SimpleNamespace(id=uuid4(), is_active=True), None),
    )

    assert result is legacy_response
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.NON_STREAM
    wait.assert_awaited_once_with(started["data"].run_id)
    build_response.assert_awaited_once_with(run)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_code", "expected_status"),
    [
        ("model_quota_exceeded", ResponseCode.MODEL_QUOTA_EXCEEDED, 429),
        (None, ResponseCode.UNKNOWN_ERROR, 500),
    ],
)
async def test_chat_nonstream_maps_run_failures(
    error_code, expected_code, expected_status
):
    run = SimpleNamespace(
        id=uuid4(),
        status=AgentRunStatus.FAILED,
        error_code=error_code,
        canonical_message_id=None,
    )

    with pytest.raises(BusinessError) as exc_info:
        await chat_api._build_non_stream_run_response(run)

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status


@pytest.mark.asyncio
async def test_chat_stream_subscribes_and_passes_through_events(monkeypatch):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat_api, "start_chat_run", start_run)

    async def events(run_id, from_sequence=0):
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        yield "event: message_start\ndata: {}\n\n"
        yield 'data: {"delta": "think"}\n\n'
        yield 'data: {"delta": "answer"}\n\n'
        yield "event: message_end\ndata: {}\n\n"

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat_api.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )

    body = await _collect_stream(response)
    assert "event: message_start" in body
    assert 'data: {"delta": "think"}' in body
    assert 'data: {"delta": "answer"}' in body
    assert "event: message_end" in body
    start_run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code",),
    [
        (ResponseCode.MODEL_QUOTA_EXCEEDED,),
        (ResponseCode.MODEL_NOT_FOUND,),
        (ResponseCode.UNKNOWN_ERROR,),
    ],
)
async def test_chat_stream_passes_through_terminal_error_events(
    monkeypatch, error_code
):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat_api, "start_chat_run", start_run)

    async def events(run_id, from_sequence=0):
        yield "event: run_start\ndata: {}\n\n"
        yield f'event: error\ndata: {{"code": {error_code.value}, "message": "failed"}}\n\n'

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat_api.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )

    body = await _collect_stream(response)
    assert "event: run_start" in body
    assert "event: error" in body
    assert f'"code": {error_code.value}' in body
