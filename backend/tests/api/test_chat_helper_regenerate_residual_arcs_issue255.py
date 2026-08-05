import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.api.v1.endpoints.chat_helpers import StreamIdleTimeoutError
from app.llm.errors import LLMError, QuotaExceededError
from app.llm.types import ChatStreamChunk, ChatStreamDelta, FinishReason, Message
from app.models.agent import AgentVisibility, MessageRole, RAGMode
from app.schemas.agent import ChatRequest, RegenerateRequest
from app.schemas.response import BusinessError, ResponseCode


def _fake_chat_resolution():
    """Return a SimpleNamespace mimicking ChatModelResolution for tests."""
    from types import SimpleNamespace
    from uuid import uuid4

    return SimpleNamespace(
        model=SimpleNamespace(id=uuid4()),
        team_model=SimpleNamespace(),
        model_id=str(uuid4()),
        tokenizer_model_id="stub-model",
        provider="stub",
        context_length=8192,
        max_output_tokens=1024,
        supports_vision=False,
    )


class Query:
    def __init__(self, result=None):
        self.result = result
        self.delete = AsyncMock(return_value=1)
        self.update = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    async def exists(self):
        return bool(self.result)


@pytest.mark.anyio
async def test_access_and_conversation_helper_residual_arcs(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    team_id = uuid4()
    ownerless = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        visibility=AgentVisibility.PRIVATE,
        created_by=None,
    )
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=Query(ownerless)))
    monkeypatch.setattr(chat.TeamMember, "filter", Mock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await chat.check_agent_chat_access(ownerless.id, user)
    assert exc_info.value.code == ResponseCode.AGENT_ACCESS_DENIED

    ownerless.visibility = AgentVisibility.PUBLIC
    with pytest.raises(BusinessError):
        await chat.check_agent_chat_access(ownerless.id, user)

    ownerless.created_by = SimpleNamespace(id=user.id)
    ownerless.visibility = AgentVisibility.PRIVATE
    assert await chat.check_agent_chat_access(ownerless.id, user) is ownerless

    conversation_id = uuid4()
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc_info:
        await chat.get_or_create_conversation(ownerless, user, conversation_id, {})
    assert exc_info.value.code == ResponseCode.CONVERSATION_NOT_FOUND

    conversation = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat.Conversation, "create", AsyncMock(return_value=conversation)
    )
    agent_stats = Query()
    team_stats = Query()
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=agent_stats))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=team_stats))
    ownerless.team = SimpleNamespace(id=team_id)

    assert (
        await chat.get_or_create_conversation(ownerless, user, None, {"name": "Ada"})
        is conversation
    )
    agent_stats.update.assert_awaited_once()
    team_stats.update.assert_awaited_once()


@pytest.mark.anyio
async def test_round_model_stats_and_macro_helpers_cover_empty_boundaries(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    last = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat, "get_last_active_canonical_message", AsyncMock(return_value=last)
    )
    assert await chat.get_next_user_branch_parent_id(conversation) == last.id

    agent_stats = Query()
    team_stats = Query()
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=agent_stats))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=team_stats))
    agent = SimpleNamespace(id=uuid4(), team=SimpleNamespace(id=uuid4()))
    await chat.update_message_stats(agent, {"prompt": None, "completion": 3})
    assert agent_stats.update.await_args.kwargs["total_tokens"].right.value == 3

    agent.model_id = None
    assert await chat.get_model_identifier(agent) is None
    assert await chat.get_agent_chat_model(agent) is None

    assert not await chat.round_has_persisted_trace(None)
    assert not await chat.round_has_persisted_trace(SimpleNamespace(round_id=None))
    assert chat._first_token_ms(1.0, None) is None


@pytest.mark.anyio
async def test_message_payload_and_memory_enqueue_residual_arcs(monkeypatch):
    round_id = uuid4()
    regular = SimpleNamespace(round_id=None, round_role=None, is_round_canonical=True)
    final = SimpleNamespace(
        round_id=round_id,
        round_role=chat.MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    step = SimpleNamespace(round_id=round_id, is_round_canonical=False)
    monkeypatch.setattr(
        chat, "build_round_steps_map", AsyncMock(return_value={round_id: []})
    )
    validated = MagicMock()
    validated.model_dump.side_effect = [{"id": "regular"}, {"id": "final"}]
    monkeypatch.setattr(chat.MessageOut, "model_validate", Mock(return_value=validated))

    assert await chat.build_message_round_payloads([regular, step, final]) == [
        {"id": "regular"},
        {"id": "final", "steps": []},
    ]

    conversation = SimpleNamespace(id=uuid4())
    message = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        chat,
        "get_context_compression_config",
        lambda _agent: {
            "session_memory_enabled": True,
            "session_memory_async_extract": False,
        },
    )
    chat.enqueue_session_memory_extraction(SimpleNamespace(), conversation, message)


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
        id=uuid4(),
        role=MessageRole.USER,
        content="question",
        created_at=datetime.now(UTC),
    )
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="answer",
        created_at=datetime.now(UTC),
        parent_id=None,
        branch_parent_id=user_message.id,
    )
    created = SimpleNamespace(id=uuid4(), save=AsyncMock(), tool_calls=None)
    cleanup = Query()
    prefix = AsyncMock(side_effect=[[user_message], [user_message]])

    monkeypatch.setattr(chat.Message, "filter", Mock(return_value=Query(original)))
    monkeypatch.setattr(
        chat.Conversation, "filter", Mock(return_value=Query(conversation))
    )
    agent_queries = iter([Query(agent), Query()])
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: next(agent_queries))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))

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
        AsyncMock(return_value="sandbox"),
    )
    monkeypatch.setattr(
        chat, "collect_conversation_images", lambda *_args, **_kwargs: ([], [])
    )
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
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())

    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    return SimpleNamespace(
        response=response,
        conversation=conversation,
        user_message=user_message,
        original=original,
        created=created,
        cleanup=cleanup,
    )


async def collect(response):
    return "".join([event async for event in response.body_iterator])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "preserved", "message"),
    [
        (QuotaExceededError(quota_type="daily"), True, "model_quota_exceeded"),
        (QuotaExceededError(quota_type="daily"), False, "model_quota_exceeded"),
        (LLMError("provider"), True, "provider failure"),
        (LLMError("provider"), False, "provider failure"),
        (StreamIdleTimeoutError(), True, "stream_timeout_exceeded"),
        (StreamIdleTimeoutError(), False, "stream_timeout_exceeded"),
        (RuntimeError("boom"), True, "unknown_error"),
        (RuntimeError("boom"), False, "unknown_error"),
    ],
)
async def test_regenerate_inner_error_cleanup_arcs(
    monkeypatch, error, preserved, message
):
    state = await setup_regeneration(monkeypatch)
    cleanup = Query()
    monkeypatch.setattr(chat.Message, "filter", Mock(return_value=cleanup))
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(side_effect=error))
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=preserved)
    )
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[state.original])
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat, "_format_llm_error_message", lambda _error: "provider failure"
    )

    events = await collect(state.response)

    assert f'"msg": "{message}"' in events
    if preserved:
        cleanup.delete.assert_not_awaited()
    else:
        cleanup.delete.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("outer")])
@pytest.mark.parametrize("preserved", [False, True])
async def test_regenerate_outer_error_cleanup_arcs(monkeypatch, error, preserved):
    state = await setup_regeneration(monkeypatch)
    cleanup = Query()
    monkeypatch.setattr(chat.Message, "filter", Mock(return_value=cleanup))
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=preserved)
    )
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[state.original])
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    class FailingTimeout:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            raise error

    monkeypatch.setattr(asyncio, "timeout", lambda _seconds: FailingTimeout())
    monkeypatch.setattr(
        chat,
        "send_heartbeat_if_needed",
        AsyncMock(side_effect=asyncio.CancelledError),
    )

    events = await collect(state.response)

    assert (
        "stream_timeout_exceeded" in events
        if isinstance(error, TimeoutError)
        else ("unknown_error" in events)
    )
    if preserved:
        cleanup.delete.assert_not_awaited()
    else:
        cleanup.delete.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("with_progress", [False, True])
async def test_regenerate_cancelled_cleanup_arcs(monkeypatch, with_progress):
    state = await setup_regeneration(monkeypatch)
    cleanup = Query()
    monkeypatch.setattr(chat.Message, "filter", Mock(return_value=cleanup))

    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))

    async def cancel(_stream, **_kwargs):
        if with_progress:
            yield ChatStreamChunk(
                id="partial",
                model="stub",
                delta=ChatStreamDelta(content="partial"),
            )
        raise asyncio.CancelledError

    monkeypatch.setattr(chat, "iter_with_idle_timeout", cancel)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[state.original])
    )

    assert "event: message_start" in await collect(state.response)
    if with_progress:
        state.created.save.assert_awaited_once()
        cleanup.delete.assert_not_awaited()
    else:
        cleanup.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_chat_stream_auto_rag_emits_context(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team.id,
        team=team,
        rag_mode=RAGMode.AUTO,
        enable_attachments=False,
        enable_user_input_request=False,
        max_iterations=1,
    )
    conversation = SimpleNamespace(id=uuid4(), title="existing")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    created = []

    async def create_message(**values):
        message = SimpleNamespace(
            id=uuid4(),
            conversation_id=conversation.id,
            created_at=datetime.now(UTC),
            save=AsyncMock(),
            content=values.get("content", ""),
            reasoning_content=None,
            tool_calls=None,
            model_used=None,
            token_usage=None,
            duration_ms=None,
            first_token_ms=None,
            is_manually_stopped=False,
            round_status=None,
            **{key: value for key, value in values.items() if key != "content"},
        )
        created.append(message)
        return message

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
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
        AsyncMock(return_value="sandbox"),
    )
    monkeypatch.setattr(chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=True))
    contexts = [{"document_id": "doc", "content": "answer"}]
    monkeypatch.setattr(chat, "perform_rag_retrieval", AsyncMock(return_value=contexts))
    monkeypatch.setattr(chat, "aggregate_rag_contexts", lambda values: values)
    monkeypatch.setattr(
        chat,
        "build_rag_prompt",
        lambda values, message: f"{message}:{values[0]['content']}",
    )
    monkeypatch.setattr(
        chat, "build_file_content_for_context", AsyncMock(return_value=("", None))
    )
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        chat, "collect_conversation_images", lambda *_args, **_kwargs: ([], [])
    )
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
    prepared = SimpleNamespace(
        messages=[Message(role="user", content="prepared")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )

    async def chunks(**_kwargs):
        yield ChatStreamChunk(
            id="done",
            model="stub",
            delta=ChatStreamDelta(content="answer"),
            finish_reason=FinishReason.STOP,
        )

    monkeypatch.setattr("app.llm.model_manager.team_chat_stream", chunks)
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", AsyncMock())
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat, "now_utc", lambda: datetime.now(UTC))

    response = await chat.chat_stream(
        agent.id,
        ChatRequest(message="question"),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        (user, None),
    )
    events = await collect(response)

    assert "event: rag_start" in events
    assert "event: rag_context" in events
    assert '"content": "answer"' in events
    assert chat.prepare_model_context.await_args.kwargs["user_message"] == (
        "question:answer"
    )
