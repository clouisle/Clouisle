"""Endpoint contract tests for the durable edit-user-message stream entry.

Loop-level persistence, retry, and RAG-stream details moved to the AgentLoop
worker (covered by test_agent_run_durable / test_agent_loop_behavioral_smoke /
characterization). This file asserts the surviving route responsibilities:
validation, branch preparation, and durable-run enqueue metadata.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_api
from app.models.agent import MessageRole, MessageRoundRole, RAGMode
from app.models.agent_run import AgentRunMode
from app.schemas.agent import EditMessageRequest, RunStartOut
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    """Small chainable queryset double for edit route preparation."""

    def __init__(self, result=None, *, count=0, exists=True):
        self.result = result
        self.count_result = count
        self.exists_result = exists

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

    async def all(self):
        return []

    async def count(self):
        return self.count_result

    async def exists(self):
        return self.exists_result


@asynccontextmanager
async def transaction():
    yield object()


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


def _edit_env(monkeypatch, *, rag_mode=RAGMode.OFF, original_role=MessageRole.USER):
    user = SimpleNamespace(id=uuid4(), locale="en")
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), rag_mode=rag_mode)
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=original_role,
        content="original question",
        branch_parent_id=None,
        images=[{"url": "upload.png"}],
        file_urls=["notes.txt"],
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
    started = _started()
    enqueue = AsyncMock(return_value=started)
    monkeypatch.setattr(chat_api, "_enqueue_existing_message_run", enqueue)

    return SimpleNamespace(
        user=user,
        agent=agent,
        conversation=conversation,
        original=original,
        created=created,
        activate=activate,
        enqueue=enqueue,
    )


@pytest.mark.anyio
async def test_edit_queues_durable_run_with_branch_metadata(monkeypatch):
    env = _edit_env(monkeypatch)
    from app.services import agent_run_stream

    async def events(run_id, from_sequence=0):
        assert run_id == env.enqueue.return_value["data"].run_id
        assert from_sequence == 0
        yield "event: run_start\ndata: {}\n\n"
        yield "event: run_end\ndata: {}\n\n"

    monkeypatch.setattr(agent_run_stream, "sse_events", events)

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="  edited question  "),
        SimpleNamespace(),
        env.user,
    )

    edited, assistant = env.created
    body = await _collect_stream(response)
    assert "event: run_start" in body
    assert "event: run_end" in body
    kwargs = env.enqueue.await_args.kwargs
    assert kwargs["mode"] == AgentRunMode.EDIT
    assert kwargs["source_message_id"] == env.original.id
    assert kwargs["branch_parent_id"] == edited.id
    assert edited.parent_id == env.original.id
    assert edited.content == "edited question"
    assert edited.version_number == 3
    assert edited.images == env.original.images
    assert edited.file_urls == env.original.file_urls
    assert edited.round_role == MessageRoundRole.USER_INPUT
    assert assistant.round_role == MessageRoundRole.ASSISTANT_FINAL
    assert assistant.branch_parent_id == edited.id
    assert env.activate.await_count == 1


@pytest.mark.anyio
async def test_edit_rag_auto_supplies_context_payloads(monkeypatch):
    env = _edit_env(monkeypatch, rag_mode=RAGMode.AUTO)
    monkeypatch.setattr(
        chat_api.AgentKnowledgeBase, "exists", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        chat_api,
        "perform_rag_retrieval",
        AsyncMock(return_value=[{"content": "source", "score": 0.9}]),
    )
    monkeypatch.setattr(chat_api, "aggregate_rag_contexts", lambda contexts: contexts)

    await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="edited question"),
        SimpleNamespace(),
        env.user,
    )

    kwargs = env.enqueue.await_args.kwargs
    assert kwargs["rag_contexts"] == [{"content": "source", "score": 0.9}]


@pytest.mark.anyio
async def test_edit_validation_rejects_non_user_message(monkeypatch):
    env = _edit_env(monkeypatch, original_role=MessageRole.ASSISTANT)

    with pytest.raises(BusinessError) as exc_info:
        await chat_api.edit_user_message_stream(
            env.agent.id,
            env.original.id,
            EditMessageRequest(content="edited question"),
            SimpleNamespace(),
            env.user,
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "can_only_edit_user_message"
    env.enqueue.assert_not_awaited()


@pytest.mark.anyio
async def test_edit_validation_accepts_unchanged_nonempty_content(monkeypatch):
    env = _edit_env(monkeypatch)

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content=" original question "),
        SimpleNamespace(),
        env.user,
    )

    edited, _assistant = env.created
    assert response.media_type == "text/event-stream"
    assert edited.content == "original question"
    assert env.enqueue.await_count == 1


@pytest.mark.anyio
async def test_edit_stream_passes_through_terminal_error_events(monkeypatch):
    env = _edit_env(monkeypatch)
    from app.services import agent_run_stream

    async def events(run_id, from_sequence=0):
        yield "event: run_start\ndata: {}\n\n"
        yield 'event: error\ndata: {"code": "run_failed", "msg": "boom"}\n\n'

    monkeypatch.setattr(agent_run_stream, "sse_events", events)

    response = await chat_api.edit_user_message_stream(
        env.agent.id,
        env.original.id,
        EditMessageRequest(content="edited question"),
        SimpleNamespace(),
        env.user,
    )

    body = await _collect_stream(response)
    assert "event: run_start" in body
    assert "event: error" in body
    assert '"code": "run_failed"' in body
