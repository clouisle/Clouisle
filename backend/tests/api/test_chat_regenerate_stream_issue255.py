from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.models.agent_run import AgentRunMode
from app.schemas.agent import RegenerateRequest


@pytest.mark.anyio
async def test_regenerate_stream_queues_new_version(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        locale="en",
    )
    user_message = SimpleNamespace(
        id=uuid4(),
        role=MessageRole.USER,
        content="original question",
        created_at=SimpleNamespace(),
        images=[],
        file_urls=[],
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=uuid4())
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="original answer",
        branch_parent_id=user_message.id,
        round_status=MessageRoundStatus.COMPLETED,
        version_number=1,
    )
    agent = SimpleNamespace(id=uuid4(), rag_mode=RAGMode.OFF)
    new_message = SimpleNamespace(id=uuid4())
    started = {"data": object()}
    stream_response = object()
    enqueue = AsyncMock(return_value=started)
    prefix = AsyncMock(return_value=[user_message])
    message_query = MagicMock()
    message_query.first = AsyncMock(return_value=original)
    conversation_query = MagicMock()
    conversation_query.first = AsyncMock(return_value=conversation)
    agent_query = MagicMock()
    agent_query.prefetch_related.return_value = agent_query
    agent_query.first = AsyncMock(return_value=agent)

    async def create_message(**values):
        for key, value in values.items():
            setattr(new_message, key, value)
        return new_message

    monkeypatch.setattr(chat.Message, "filter", lambda *_args, **_kwargs: message_query)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda *_args, **_kwargs: conversation_query
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: agent_query)
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _m: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))
    monkeypatch.setattr(chat.Message, "create", create_message)
    monkeypatch.setattr(chat, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(chat, "_stream_queued_run", lambda _started: stream_response)

    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(),
        SimpleNamespace(),
        user,
    )

    assert response is stream_response
    prefix.assert_awaited_once_with(original, trimmed=False)
    assert new_message.parent_id == original.id
    assert new_message.branch_parent_id == user_message.id
    assert new_message.version_number == 2
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.REGENERATE
    assert enqueue.await_args.kwargs["source_message_id"] == original.id
    assert enqueue.await_args.kwargs["canonical_message_id"] == new_message.id
    assert enqueue.await_args.kwargs["user_message"] is user_message
    assert enqueue.await_args.kwargs["message"] == user_message.content
    assert enqueue.await_args.kwargs["include_current_user_message"] is False
    assert enqueue.await_args.kwargs["created_message_count"] == 1
    assert enqueue.await_args.kwargs["message_start"] == {
        "version_number": 2,
        "version_count": 2,
        "parent_id": str(original.id),
    }
