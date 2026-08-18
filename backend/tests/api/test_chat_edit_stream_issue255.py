import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import LLMError
from app.llm.types import ChatStreamChunk, ChatStreamDelta, FinishReason, Message, Usage
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import EditMessageRequest
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, *, count=0, exists=True):
        self.result = result
        self.count_result = count
        self.exists_result = exists
        self.update = AsyncMock(return_value=1)
        self.delete = AsyncMock(return_value=1)

    def filter(self, *_args, **_kwargs):
        return self

    def prefetch_related(self, *_args):
        return self

    def using_db(self, *_args):
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


async def setup_edit(monkeypatch, *, rag_mode=RAGMode.OFF):
    user = SimpleNamespace(id=uuid4(), locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=rag_mode,
        max_iterations=1,
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="original question",
        branch_parent_id=None,
        images=[{"url": "upload.png"}],
        file_urls=["notes.txt"],
    )
    prefix_message = SimpleNamespace(id=uuid4())
    original_reply = SimpleNamespace(id=uuid4())
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created = iter([edited, assistant])
    version_query = Query(count=2)
    active_query = Query(exists=True)
    cleanup_query = Query()
    agent_stats = Query(agent)
    team_stats = Query()
    conversation_stats = Query(conversation)

    def message_filter(*_args, **kwargs):
        if kwargs == {"id": original.id}:
            return Query(original)
        if "is_active" in kwargs:
            return active_query
        if "id" in kwargs and len(kwargs) == 1:
            return cleanup_query
        return version_query

    monkeypatch.setattr(chat.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: conversation_stats
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_stats)
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: team_stats)
    monkeypatch.setattr(chat, "in_transaction", transaction)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(
        chat,
        "get_prefix_path_before",
        AsyncMock(return_value=[prefix_message]),
    )
    monkeypatch.setattr(
        chat,
        "find_descendant_branch_from",
        AsyncMock(return_value=[original, original_reply]),
    )

    async def create_message(**values):
        item = next(created)
        for key, value in values.items():
            setattr(item, key, value)
        return item

    monkeypatch.setattr(chat.Message, "create", AsyncMock(side_effect=create_message))
    monkeypatch.setattr(
        chat,
        "get_streaming_config",
        lambda _agent: {
            "global_timeout": 10,
            "heartbeat_interval": 1,
            "tool_timeouts": {},
            "idle_timeout": 3,
        },
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="sandbox-session"),
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_args: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _inventory: text
    )
    model_uuid = uuid4()
    model = SimpleNamespace(
        id=model_uuid,
        is_enabled=True,
        capabilities={},
        provider="stub",
        model_id="unit-model",
        context_length=8192,
        max_output_tokens=1024,
    )
    model_resolution = SimpleNamespace(
        model=model,
        team_model=SimpleNamespace(model=model, is_enabled=True),
        model_id=str(model_uuid),
        tokenizer_model_id=model.model_id,
        provider=model.provider,
        context_length=model.context_length,
        max_output_tokens=model.max_output_tokens,
        supports_vision=False,
    )
    monkeypatch.setattr(
        chat,
        "resolve_agent_chat_model",
        AsyncMock(return_value=model_resolution),
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _compression: None)
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(chat, "now_utc", lambda: "completed-at")
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    response = await chat.edit_user_message_stream(
        agent.id,
        original.id,
        EditMessageRequest(content="  edited question  "),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    return SimpleNamespace(
        response=response,
        user=user,
        agent=agent,
        conversation=conversation,
        original=original,
        original_reply=original_reply,
        prefix_message=prefix_message,
        edited=edited,
        assistant=assistant,
        cleanup_query=cleanup_query,
        agent_stats=agent_stats,
        team_stats=team_stats,
        conversation_stats=conversation_stats,
        model_id=str(model_uuid),
    )


def event_payload(events, event_name):
    event = next(item for item in events if f"event: {event_name}" in item)
    return json.loads(event.split("data: ", 1)[1])


@pytest.mark.anyio
async def test_edit_stream_creates_version_and_persists_regenerated_reply(monkeypatch):
    state = await setup_edit(monkeypatch, rag_mode=RAGMode.AUTO)
    monkeypatch.setattr(chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=True))
    monkeypatch.setattr(
        chat,
        "perform_rag_retrieval",
        AsyncMock(return_value=[{"content": "source", "score": 0.9}]),
    )
    monkeypatch.setattr(chat, "aggregate_rag_contexts", lambda contexts: contexts)
    monkeypatch.setattr(chat, "build_rag_prompt", lambda contexts, text: f"rag:{text}")
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared prompt")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))

    chunks = [
        ChatStreamChunk(
            id="reasoning",
            model="stub/unit-model",
            delta=ChatStreamDelta(reasoning_content="thinking"),
        ),
        ChatStreamChunk(
            id="content",
            model="stub/unit-model",
            delta=ChatStreamDelta(content="new answer"),
            usage=Usage(prompt_tokens=31, completion_tokens=17, total_tokens=48),
            finish_reason=FinishReason.LENGTH,
        ),
    ]

    async def stream_chunks(_stream, **_kwargs):
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(chat, "iter_with_idle_timeout", stream_chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = [event async for event in state.response.body_iterator]

    start = event_payload(events, chat.SSEEventType.MESSAGE_START)
    end = event_payload(events, chat.SSEEventType.MESSAGE_END)
    assert any(f"event: {chat.SSEEventType.RAG_START}" in item for item in events)
    assert any(f"event: {chat.SSEEventType.RAG_CONTEXT}" in item for item in events)
    assert any(f"event: {chat.SSEEventType.REASONING_START}" in item for item in events)
    assert any(f"event: {chat.SSEEventType.REASONING_END}" in item for item in events)
    assert any(
        f"event: {chat.SSEEventType.OUTPUT_TRUNCATED}" in item for item in events
    )
    assert start["edited_message_id"] == str(state.edited.id)
    assert start["edited_version_number"] == 3
    assert state.edited.content == "edited question"
    assert state.edited.version_number == 3
    assert state.edited.parent_id == state.original.id
    assert state.edited.images == state.original.images
    assert state.assistant.content == "new answer"
    assert state.assistant.reasoning_content == "thinking"
    assert state.assistant.model_used == state.model_id
    assert state.assistant.round_status == MessageRoundStatus.COMPLETED
    assert state.assistant.created_at == "completed-at"
    assert state.assistant.token_usage == {"prompt": 31, "completion": 17}
    state.assistant.save.assert_awaited_once()
    assert chat.activate_conversation_branch.await_count == 2
    chat.stale_session_memory_if_source_outside_active_branch.assert_awaited_once_with(
        state.conversation.id
    )

    chat.enqueue_session_memory_extraction.assert_called_once_with(
        state.agent, state.conversation, state.assistant
    )
    chat.AuditLogService.log.assert_awaited_once()
    assert end["usage"] == {
        "prompt_tokens": 31,
        "completion_tokens": 17,
        "total_tokens": 48,
    }
    state.agent_stats.update.assert_awaited_once()
    state.team_stats.update.assert_awaited_once()
    state.conversation_stats.update.assert_awaited_once()


@pytest.mark.anyio
async def test_edit_stream_failure_removes_branch_and_restores_original(monkeypatch):
    state = await setup_edit(monkeypatch)
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(side_effect=LLMError("unavailable"))
    )
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(chat, "_format_llm_error_message", lambda _error: "failed")

    events = [event async for event in state.response.body_iterator]

    error = event_payload(events, chat.SSEEventType.ERROR)
    assert error == {"code": ResponseCode.UNKNOWN_ERROR, "msg": "failed"}
    state.cleanup_query.delete.assert_awaited_once()
    state.cleanup_query.update.assert_awaited_once_with(is_active=False)
    assert chat.activate_conversation_branch.await_args_list[-1].args == (
        state.conversation.id,
        [state.prefix_message, state.original, state.original_reply],
    )
    state.assistant.save.assert_not_awaited()


@pytest.mark.anyio
async def test_edit_stream_preserves_model_resolution_business_error(monkeypatch):
    state = await setup_edit(monkeypatch)
    monkeypatch.setattr(
        chat,
        "resolve_agent_chat_model",
        AsyncMock(
            side_effect=BusinessError(
                code=ResponseCode.MODEL_NOT_FOUND,
                msg_key="model_not_found",
            )
        ),
    )
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=False)
    )

    events = [event async for event in state.response.body_iterator]

    assert event_payload(events, chat.SSEEventType.ERROR) == {
        "code": ResponseCode.MODEL_NOT_FOUND,
        "msg": "model_not_found",
    }
    state.cleanup_query.delete.assert_awaited_once()
    state.cleanup_query.update.assert_awaited_once_with(is_active=False)
    assert chat.activate_conversation_branch.await_args_list[-1].args == (
        state.conversation.id,
        [state.prefix_message, state.original, state.original_reply],
    )
