from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.models.agent_run import AgentRunMode
from app.schemas.agent import RegenerateRequest


class Query:
    def __init__(self, result=None):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


@pytest.mark.anyio
async def test_regenerate_errored_message_retries_in_place_without_new_version(
    monkeypatch,
):
    """An errored assistant is reset and retried on the same durable row."""
    user_message = SimpleNamespace(
        id=uuid4(),
        role=MessageRole.USER,
        content="question",
        created_at=SimpleNamespace(),
        images=[],
        file_urls=[],
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=uuid4())
    agent = SimpleNamespace(id=uuid4(), rag_mode=RAGMode.OFF)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="old answer",
        reasoning_content="old reasoning",
        tool_calls=[{"id": "old"}],
        token_usage={"prompt": 1},
        duration_ms=12,
        first_token_ms=3,
        round_status=MessageRoundStatus.ERROR,
        round_id=None,
        round_index=4,
        branch_parent_id=user_message.id,
        version_number=1,
        created_at=SimpleNamespace(),
        save=AsyncMock(),
    )
    query = Query(original)
    started = {"data": object()}
    stream_response = object()
    enqueue = AsyncMock(return_value=started)
    create = AsyncMock()
    prefix = AsyncMock(return_value=[user_message])

    monkeypatch.setattr(chat.Message, "filter", lambda *_args, **_kwargs: query)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda *_args, **_kwargs: Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: Query(agent))
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))
    monkeypatch.setattr(chat.Message, "create", create)
    monkeypatch.setattr(chat, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(chat, "_stream_queued_run", lambda _started: stream_response)
    monkeypatch.setattr(chat, "now_utc", lambda: "retry-at")

    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(variables={"attempt": 2}),
        SimpleNamespace(),
        SimpleNamespace(id=uuid4(), locale="en"),
    )

    assert response is stream_response
    prefix.assert_awaited_once_with(original, trimmed=False)
    original.save.assert_awaited_once()
    assert original.content == ""
    assert original.reasoning_content is None
    assert original.tool_calls is None
    assert original.token_usage is None
    assert original.round_status is None
    assert original.version_number == 1
    assert original.created_at == "retry-at"
    create.assert_not_awaited()
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.REGENERATE
    assert enqueue.await_args.kwargs["source_message_id"] == original.id
    assert enqueue.await_args.kwargs["canonical_message_id"] == original.id
    assert enqueue.await_args.kwargs["user_message"] is user_message
    assert enqueue.await_args.kwargs["created_message_count"] == 0
    assert enqueue.await_args.kwargs["in_place_retry"] is True
    assert enqueue.await_args.kwargs["include_current_user_message"] is False
    assert enqueue.await_args.kwargs["history_before_message_created_at"] == (
        user_message.created_at
    )
    assert enqueue.await_args.kwargs["message_start"] == {
        "version_number": 1,
        "version_count": 1,
    }
