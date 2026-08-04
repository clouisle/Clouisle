import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import LLMError
from app.llm.types import ChatStreamChunk, ChatStreamDelta, FinishReason, Message
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import RegenerateRequest
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None):
        self.result = result
        self.delete = AsyncMock(return_value=1)
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


async def setup_regeneration(monkeypatch):
    user = SimpleNamespace(id=uuid4(), locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=RAGMode.OFF,
        max_iterations=1,
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    user_message = SimpleNamespace(
        id=uuid4(), role=MessageRole.USER, content="original question"
    )
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="original answer",
        created_at=datetime.now(timezone.utc),
        parent_id=None,
        branch_parent_id=user_message.id,
    )
    created = SimpleNamespace(id=uuid4(), save=AsyncMock(), tool_calls=None)
    deleted = Query()
    agent_stats = Query()
    team_stats = Query()
    prefix = AsyncMock(side_effect=[[user_message], [user_message]])

    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: Query(original))
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    agent_queries = iter([Query(agent), agent_stats])
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: next(agent_queries))
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: team_stats)
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=2))

    async def create_message(**values):
        for key, value in values.items():
            setattr(created, key, value)
        return created

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
        chat,
        "build_compression_events",
        lambda **_kwargs: (None, None),
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _compression: None)
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat,
        "stale_session_memory_if_source_outside_active_branch",
        AsyncMock(),
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat, "now_utc", lambda: "completed-at")

    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    return SimpleNamespace(
        response=response,
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        original=original,
        created=created,
        deleted=deleted,
        agent_stats=agent_stats,
        team_stats=team_stats,
        prefix=prefix,
        model_id=str(model_uuid),
    )


def event_payload(events, event_name):
    event = next(item for item in events if f"event: {event_name}" in item)
    return json.loads(event.split("data: ", 1)[1])


@pytest.mark.anyio
async def test_regenerate_stream_persists_and_activates_new_version(monkeypatch):
    state = await setup_regeneration(monkeypatch)
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared prompt")], compression=None
    )
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(chat, "prepare_model_context", prepare)

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
            finish_reason=FinishReason.STOP,
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
    assert start["message_id"] == str(state.created.id)
    assert start["version_number"] == 3
    assert state.created.content == "new answer"
    assert state.created.reasoning_content == "thinking"
    assert state.created.model_used == state.model_id
    assert state.created.version_number == 3
    assert state.created.round_status == MessageRoundStatus.COMPLETED
    assert state.created.created_at == "completed-at"
    assert state.created.token_usage == {"prompt": 3, "completion": 2}
    state.created.save.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once_with(
        state.conversation.id, [state.user_message, state.created]
    )
    chat.stale_session_memory_if_source_outside_active_branch.assert_awaited_once_with(
        state.conversation.id
    )

    chat.enqueue_session_memory_extraction.assert_called_once_with(
        state.agent, state.conversation, state.created
    )
    assert end["usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert prepare.await_count == 2
    state.agent_stats.update.assert_awaited_once()
    state.team_stats.update.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_message", "timeout"),
    [
        (LLMError("provider unavailable"), "provider failure", None),
        (chat.StreamIdleTimeoutError(), "stream_timeout_exceeded", 3),
    ],
)
async def test_regenerate_stream_failure_deletes_new_version_and_restores_original(
    monkeypatch, error, expected_message, timeout
):
    state = await setup_regeneration(monkeypatch)
    deleted = Query()
    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: deleted)
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(side_effect=error))
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[state.original])
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat, "_format_llm_error_message", lambda _error: "provider failure"
    )

    events = [event async for event in state.response.body_iterator]

    payload = event_payload(events, chat.SSEEventType.ERROR)
    assert payload["code"] == ResponseCode.UNKNOWN_ERROR
    assert payload["msg"] == expected_message
    if timeout is not None:
        assert payload["timeout"] == timeout
    deleted.delete.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once_with(
        state.conversation.id, [state.user_message, state.original]
    )
    chat.persist_partial_round_error.assert_awaited_once()
    state.created.save.assert_not_awaited()


@pytest.mark.anyio
async def test_regenerate_stream_preserves_model_resolution_business_error(
    monkeypatch,
):
    state = await setup_regeneration(monkeypatch)
    deleted = Query()
    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: deleted)
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
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[state.original])
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    events = [event async for event in state.response.body_iterator]

    assert event_payload(events, chat.SSEEventType.ERROR) == {
        "code": ResponseCode.MODEL_NOT_FOUND,
        "msg": "model_not_found",
    }
    deleted.delete.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once_with(
        state.conversation.id, [state.user_message, state.original]
    )
    chat.persist_partial_round_error.assert_awaited_once()
    state.created.save.assert_not_awaited()
