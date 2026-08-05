from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.api.v1.endpoints.chat_helpers import StreamIdleTimeoutError
from app.llm.errors import QuotaExceededError
from app.models.agent import MessageRole, RAGMode
from app.schemas.agent import EditMessageRequest
from app.schemas.response import ResponseCode


class Query:
    def __init__(self, value=None, *, count=0, exists=True):
        self.value = value
        self.count_value = count
        self.exists_value = exists
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
        return self.value

    async def all(self):
        return []

    async def count(self):
        return self.count_value

    async def exists(self):
        return self.exists_value


@asynccontextmanager
async def transaction():
    yield object()


async def setup_edit(monkeypatch):
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
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="original",
        branch_parent_id=None,
        images=None,
        file_urls=None,
    )
    prefix = SimpleNamespace(id=uuid4())
    original_reply = SimpleNamespace(id=uuid4())
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created = iter([edited, assistant])
    version_query = Query(count=1)
    active_query = Query(exists=True)
    cleanup_query = Query()

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
        chat.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: Query(agent))
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(chat, "in_transaction", transaction)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(
        chat, "get_prefix_path_before", AsyncMock(return_value=[prefix])
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
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_args: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _inventory: text
    )
    monkeypatch.setattr(
        chat,
        "get_agent_chat_model",
        AsyncMock(
            return_value=SimpleNamespace(
                model=SimpleNamespace(
                    id=uuid4(),
                    is_enabled=True,
                    capabilities={},
                    provider="stub",
                    model_id="unit-model",
                    context_length=8192,
                    max_output_tokens=1024,
                )
            )
        ),
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(chat, "now_utc", lambda: "now")
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    response = await chat.edit_user_message_stream(
        agent.id,
        original.id,
        EditMessageRequest(content="edited"),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    return SimpleNamespace(
        response=response,
        assistant=assistant,
        cleanup_query=cleanup_query,
        conversation=conversation,
        prefix=prefix,
        original=original,
        original_reply=original_reply,
    )


async def collect(response):
    return "".join([event async for event in response.body_iterator])


@pytest.mark.anyio
async def test_edit_stream_stops_whole_loop_when_heartbeat_detects_disconnect(
    monkeypatch,
):
    state = await setup_edit(monkeypatch)
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(False, 0))
    )

    events = await collect(state.response)

    assert "event: message_start" in events
    assert "event: message_end" not in events
    assert state.assistant.is_manually_stopped is True
    state.assistant.save.assert_awaited_once()
    assert chat.activate_conversation_branch.await_count == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "preserved", "message", "code"),
    [
        (
            QuotaExceededError(quota_type="daily"),
            True,
            "model_quota_exceeded",
            ResponseCode.MODEL_QUOTA_EXCEEDED,
        ),
        (
            QuotaExceededError(quota_type="monthly"),
            False,
            "model_quota_exceeded",
            ResponseCode.MODEL_QUOTA_EXCEEDED,
        ),
        (
            StreamIdleTimeoutError(),
            True,
            "stream_timeout_exceeded",
            ResponseCode.UNKNOWN_ERROR,
        ),
        (
            StreamIdleTimeoutError(),
            False,
            "stream_timeout_exceeded",
            ResponseCode.UNKNOWN_ERROR,
        ),
        (TimeoutError(), False, "stream_timeout_exceeded", ResponseCode.UNKNOWN_ERROR),
        (RuntimeError("boom"), True, "unknown_error", ResponseCode.UNKNOWN_ERROR),
        (RuntimeError("boom"), False, "unknown_error", ResponseCode.UNKNOWN_ERROR),
    ],
)
async def test_edit_stream_error_handlers_preserve_or_restore_branch(
    monkeypatch, error, preserved, message, code
):
    state = await setup_edit(monkeypatch)
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(side_effect=error))
    persist = AsyncMock(return_value=preserved)
    monkeypatch.setattr(chat, "persist_partial_round_error", persist)

    events = await collect(state.response)

    assert f'"msg": "{message}"' in events
    assert f'"code": {code}' in events
    persist.assert_awaited_once()
    if preserved:
        state.cleanup_query.delete.assert_not_awaited()
    else:
        state.cleanup_query.delete.assert_awaited_once()
        state.cleanup_query.update.assert_awaited_once_with(is_active=False)
        assert chat.activate_conversation_branch.await_args_list[-1].args == (
            state.conversation.id,
            [state.prefix, state.original, state.original_reply],
        )
