import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import LLMError, QuotaExceededError
from app.models.agent import MessageRole, RAGMode
from app.schemas.agent import ChatRequest, RegenerateRequest
from app.schemas.response import ResponseCode


def _fake_chat_resolution():
    """Return a SimpleNamespace mimicking ChatModelResolution for tests."""
    from types import SimpleNamespace
    from uuid import uuid4

    model_uuid = uuid4()
    return SimpleNamespace(
        model=SimpleNamespace(id=model_uuid),
        team_model=SimpleNamespace(),
        model_id=str(model_uuid),
        tokenizer_model_id="stub-model",
        provider="stub",
        context_length=8192,
        max_output_tokens=1024,
        supports_vision=False,
    )


class Query:
    def __init__(self, value=None):
        self.value = value
        self.delete = AsyncMock(return_value=1)
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


class StoredMessage:
    def __init__(self, conversation, role, **values):
        self.id = uuid4()
        self.conversation_id = conversation.id
        self.role = role
        self.content = values.get("content", "")
        self.parent_id = values.get("parent_id")
        self.branch_parent_id = values.get("branch_parent_id")
        self.reasoning_content = None
        self.tool_calls = None
        self.file_urls = None
        self.save = AsyncMock()
        self.delete = AsyncMock()


async def collect(response):
    items = [
        item.decode() if isinstance(item, bytes) else item
        async for item in response.body_iterator
    ]
    return "".join(items)


async def setup_send_until_prepare(monkeypatch, prepare_error):
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team.id,
        team=team,
        rag_mode=RAGMode.OFF,
        enable_attachments=False,
        enable_user_input_request=False,
        max_iterations=1,
    )
    conversation = SimpleNamespace(id=uuid4(), title="existing")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    user_message = StoredMessage(conversation, MessageRole.USER)

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(return_value=user_message))
    monkeypatch.setattr(chat, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_fake_chat_resolution()),
    )
    monkeypatch.setattr(
        chat, "get_streaming_config", lambda _agent: {"tool_timeouts": {}}
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat, "build_file_content_for_context", AsyncMock(return_value=(None, None))
    )
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _inventory: text
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(side_effect=prepare_error)
    )
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: False)
    return agent, conversation, user


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_error", "code", "msg_key", "status", "data"),
    [
        (
            QuotaExceededError(quota_type="daily"),
            ResponseCode.MODEL_QUOTA_EXCEEDED,
            "model_quota_exceeded",
            429,
            {"quota_type": "daily"},
        ),
        (
            LLMError("bad provider"),
            ResponseCode.UNKNOWN_ERROR,
            "llm_processing_failed",
            500,
            None,
        ),
    ],
)
async def test_send_maps_generator_boundary_errors(
    monkeypatch, provider_error, code, msg_key, status, data
):
    agent, _conversation, user = await setup_send_until_prepare(
        monkeypatch, provider_error
    )

    with pytest.raises(chat.BusinessError) as caught:
        await chat.chat(agent.id, ChatRequest(message="hello"), (user, None))

    assert caught.value.code == code
    assert caught.value.msg_key == msg_key
    assert caught.value.status_code == status
    assert caught.value.data == data


@pytest.mark.anyio
async def test_stream_outer_setup_exception_emits_generic_error(monkeypatch):
    agent, conversation, user = await setup_send_until_prepare(
        monkeypatch, RuntimeError("unused")
    )

    class BrokenTimeout:
        async def __aenter__(self):
            raise RuntimeError("configuration boundary failed")

        async def __aexit__(self, *_args):
            return False

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
    monkeypatch.setattr(asyncio, "timeout", lambda _seconds: BrokenTimeout())
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    response = await chat.chat_stream(
        agent.id,
        ChatRequest(message="hello"),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        (user, None),
    )
    events = await collect(response)

    assert "event: error" in events
    assert str(ResponseCode.UNKNOWN_ERROR) in events
    assert "unknown_error" in events
    assert str(conversation.id) not in events


async def setup_regenerate(monkeypatch, generator_error, *, preserved):
    user = SimpleNamespace(id=uuid4(), locale="en")
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(), team_id=team.id, team=team, rag_mode=RAGMode.OFF, max_iterations=1
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    user_message = SimpleNamespace(
        id=uuid4(), role=MessageRole.USER, content="question"
    )
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="old",
        created_at=datetime.now(UTC),
        parent_id=None,
        branch_parent_id=user_message.id,
    )
    new_message = StoredMessage(
        conversation,
        MessageRole.ASSISTANT,
        parent_id=original.id,
        branch_parent_id=user_message.id,
    )
    message_queries = []

    def message_filter(**_kwargs):
        query = Query(original)
        message_queries.append(query)
        return query

    monkeypatch.setattr(chat.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: Query(agent))
    monkeypatch.setattr(
        chat, "get_prefix_path_before", AsyncMock(return_value=[user_message])
    )
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[original])
    )
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))
    monkeypatch.setattr(chat.Message, "create", AsyncMock(return_value=new_message))
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
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _images: text
    )
    monkeypatch.setattr(
        chat,
        "resolve_agent_chat_model",
        AsyncMock(return_value=_fake_chat_resolution()),
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(side_effect=generator_error)
    )
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: False)
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=preserved)
    )
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(chat, "_format_llm_error_message", lambda _error: "formatted")

    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    return SimpleNamespace(
        response=response,
        new_message=new_message,
        original=original,
        conversation=conversation,
        message_queries=message_queries,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "preserved", "expected_code", "expected_message", "quota_type"),
    [
        (
            QuotaExceededError(quota_type="monthly"),
            True,
            ResponseCode.MODEL_QUOTA_EXCEEDED,
            "model_quota_exceeded",
            "monthly",
        ),
        (LLMError("failed"), False, ResponseCode.UNKNOWN_ERROR, "formatted", None),
        (
            chat.StreamIdleTimeoutError(),
            False,
            ResponseCode.UNKNOWN_ERROR,
            "stream_timeout_exceeded",
            None,
        ),
        (
            ValueError("unexpected"),
            True,
            ResponseCode.UNKNOWN_ERROR,
            "unknown_error",
            None,
        ),
    ],
)
async def test_regenerate_generator_error_matrix(
    monkeypatch, error, preserved, expected_code, expected_message, quota_type
):
    state = await setup_regenerate(monkeypatch, error, preserved=preserved)

    events = await collect(state.response)

    assert "event: message_start" in events
    assert f'"code": {expected_code}' in events
    assert expected_message in events
    if quota_type:
        assert f'"quota_type": "{quota_type}"' in events
    chat.persist_partial_round_error.assert_awaited_once()
    if preserved:
        chat.stale_session_memory_if_source_outside_active_branch.assert_awaited_once_with(
            state.conversation.id
        )
    else:
        assert any(query.delete.await_count for query in state.message_queries[1:])
        assert chat.activate_conversation_branch.await_count == 1
