"""Characterization tests for durable Agent Chat entry points.

The shared AgentLoop owns provider/tool execution. These tests cover the
remaining route responsibilities: durable start and stream delegation, the
legacy non-stream response adapter, and edit/regenerate branch preparation.
Loop behavior is covered by the focused AgentLoop tests.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_api
from app.models.agent import MessageRole, MessageRoundRole, MessageRoundStatus, RAGMode
from app.models.agent_run import AgentRunMode, AgentRunStatus
from app.schemas.agent import ChatRequest, EditMessageRequest, RunStartOut


class _Query:
    """Small chainable queryset double for route preparation tests."""

    def __init__(self, result=None, *, count=0):
        self.result = result
        self.count_result = count

    def filter(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_args, **_kwargs):
        return self

    def using_db(self, *_args, **_kwargs):
        return self

    def select_for_update(self):
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.count_result


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
async def test_chat_stream_starts_and_subscribes_to_durable_run(monkeypatch):
    """Streaming chat delegates execution to the durable run transport."""
    from app.services import agent_run_stream
    from fastapi.responses import StreamingResponse

    user = SimpleNamespace(id=uuid4())
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
        (user, None),
    )

    assert isinstance(response, StreamingResponse)
    assert _event_names(await _collect_stream(response)) == ["run_start", "run_end"]
    start_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_nonstream_adapts_the_shared_durable_run(monkeypatch):
    """The legacy non-stream response waits on the same queued run."""
    started = _started()
    run = SimpleNamespace(
        id=started["data"].run_id,
        status=AgentRunStatus.COMPLETED,
    )
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    legacy_response = {"legacy": True}
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


def _edit_environment(monkeypatch):
    @asynccontextmanager
    async def transaction():
        yield object()

    user = SimpleNamespace(id=uuid4(), locale="en")
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), rag_mode=RAGMode.OFF)
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="original question",
        branch_parent_id=None,
        images=[],
        file_urls=[],
    )
    prefix = SimpleNamespace(id=uuid4())
    created = []

    def message_filter(*_args, **kwargs):
        if kwargs.get("id") == original.id:
            return _Query(original)
        return _Query(count=2)

    async def create_message(**values):
        item = SimpleNamespace(
            id=uuid4(), created_at=datetime.now(UTC), save=AsyncMock()
        )
        for key, value in values.items():
            setattr(item, key, value)
        item.conversation_id = conversation.id
        created.append(item)
        return item

    monkeypatch.setattr(chat_api.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat_api.Conversation,
        "filter",
        lambda **_kwargs: _Query(conversation),
    )
    monkeypatch.setattr(chat_api.Agent, "filter", lambda **_kwargs: _Query(agent))
    monkeypatch.setattr(chat_api, "in_transaction", transaction)
    monkeypatch.setattr(chat_api, "get_version_root_id", lambda _m: original.id)
    monkeypatch.setattr(
        chat_api,
        "get_prefix_path_before",
        AsyncMock(return_value=[prefix]),
    )
    monkeypatch.setattr(chat_api.Message, "create", create_message)
    activate = AsyncMock()
    monkeypatch.setattr(chat_api, "activate_conversation_branch", activate)
    monkeypatch.setattr(
        chat_api.MessageAsset._meta,
        "default_connection",
        None,
        raising=False,
    )

    return SimpleNamespace(
        user=user,
        agent=agent,
        conversation=conversation,
        original=original,
        created=created,
        activate=activate,
    )


@pytest.mark.asyncio
async def test_edit_prepares_branch_then_queues_existing_messages(monkeypatch):
    env = _edit_environment(monkeypatch)
    started = _started()
    enqueue = AsyncMock(return_value=started)
    stream_response = object()
    monkeypatch.setattr(chat_api, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat_api, "_stream_queued_run", lambda _started: stream_response
    )

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="edited question"),
        SimpleNamespace(),
        env.user,
    )

    edited, assistant = env.created
    assert response is stream_response
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.EDIT
    assert enqueue.await_args.kwargs["source_message_id"] == env.original.id
    assert edited.parent_id == env.original.id
    assert edited.version_number == 3
    assert edited.round_role == MessageRoundRole.USER_INPUT
    assert assistant.branch_parent_id == edited.id
    assert env.activate.await_count == 1
    assert env.activate.await_args.args[1][-1] is edited


def _regenerate_environment(monkeypatch):
    user = SimpleNamespace(id=uuid4(), locale="en")
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), rag_mode=RAGMode.OFF)
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    user_message = SimpleNamespace(
        id=uuid4(),
        content="question",
        created_at=datetime.now(UTC),
        role=MessageRole.USER,
        images=[],
        file_urls=[],
    )
    old_assistant = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        branch_parent_id=user_message.id,
        round_status=MessageRoundStatus.COMPLETED,
        version_number=1,
        images=[],
        file_urls=[],
        save=AsyncMock(),
    )
    created = []

    def message_filter(*_args, **kwargs):
        if kwargs.get("id") == old_assistant.id:
            return _Query(old_assistant)
        return _Query()

    async def create_message(**values):
        item = SimpleNamespace(id=uuid4(), save=AsyncMock())
        for key, value in values.items():
            setattr(item, key, value)
        item.conversation_id = conversation.id
        created.append(item)
        return item

    monkeypatch.setattr(chat_api.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat_api.Conversation,
        "filter",
        lambda **_kwargs: _Query(conversation),
    )
    monkeypatch.setattr(chat_api.Agent, "filter", lambda **_kwargs: _Query(agent))
    monkeypatch.setattr(chat_api, "get_version_root_id", lambda _m: old_assistant.id)
    monkeypatch.setattr(
        chat_api,
        "get_prefix_path_before",
        AsyncMock(return_value=[user_message]),
    )
    monkeypatch.setattr(
        chat_api,
        "get_branch_version_count",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(chat_api.Message, "create", create_message)
    activate = AsyncMock()
    monkeypatch.setattr(chat_api, "activate_conversation_branch", activate)
    monkeypatch.setattr(
        chat_api.MessageAsset._meta,
        "default_connection",
        None,
        raising=False,
    )

    return SimpleNamespace(
        user=user,
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        old_assistant=old_assistant,
        created=created,
        activate=activate,
    )


@pytest.mark.asyncio
async def test_regenerate_prepares_new_version_then_queues_run(monkeypatch):
    env = _regenerate_environment(monkeypatch)
    started = _started()
    enqueue = AsyncMock(return_value=started)
    stream_response = object()
    monkeypatch.setattr(chat_api, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat_api, "_stream_queued_run", lambda _started: stream_response
    )

    response = await chat_api.regenerate_message(
        env.agent.id,
        env.old_assistant.id,
        SimpleNamespace(variables={"attempt": 2}),
        SimpleNamespace(),
        env.user,
    )

    new_message = env.created[0]
    assert response is stream_response
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.REGENERATE
    assert enqueue.await_args.kwargs["source_message_id"] == env.old_assistant.id
    assert new_message.parent_id == env.old_assistant.id
    assert new_message.version_number == 2
    assert new_message.branch_parent_id == env.user_message.id
    assert env.activate.await_count == 0
