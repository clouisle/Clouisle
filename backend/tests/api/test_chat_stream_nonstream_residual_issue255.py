"""Residual chat entry-point contracts after durable-run extraction."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent_run import AgentRunMode, AgentRunStatus
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
async def test_nonstream_queues_run_and_uses_canonical_response_adapter(monkeypatch):
    started = _started()
    run = SimpleNamespace(
        id=started["data"].run_id,
        status=AgentRunStatus.COMPLETED,
    )
    legacy_response = {"data": {"message": {"content": "answer"}}}
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    build_response = AsyncMock(return_value=legacy_response)
    monkeypatch.setattr(chat, "_enqueue_durable_chat_run", enqueue)
    monkeypatch.setattr(chat, "_wait_for_agent_run", wait)
    monkeypatch.setattr(chat, "_build_non_stream_run_response", build_response)

    result = await chat.chat(
        uuid4(),
        ChatRequest(message="hello"),
        (SimpleNamespace(id=uuid4(), is_active=True), None),
    )

    assert result is legacy_response
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.NON_STREAM
    wait.assert_awaited_once_with(started["data"].run_id)
    build_response.assert_awaited_once_with(run)


@pytest.mark.asyncio
async def test_stream_empty_replay_does_not_call_legacy_provider_fallback(monkeypatch):
    from app.services import agent_run_stream

    started = _started()
    start_run = AsyncMock(return_value=started)
    monkeypatch.setattr(chat, "start_chat_run", start_run)
    legacy_team_chat = AsyncMock()
    monkeypatch.setattr("app.llm.model_manager.team_chat", legacy_team_chat)

    async def events(run_id, from_sequence=0):
        assert run_id == started["data"].run_id
        assert from_sequence == 0
        if False:
            yield ""

    monkeypatch.setattr(agent_run_stream, "sse_events", events)
    response = await chat.chat_stream(
        uuid4(),
        ChatRequest(message="hello"),
        SimpleNamespace(),
        (SimpleNamespace(id=uuid4()), None),
    )

    assert await _collect(response) == ""
    start_run.assert_awaited_once()
    legacy_team_chat.assert_not_awaited()
