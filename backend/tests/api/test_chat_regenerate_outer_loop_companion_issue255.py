import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import ContextLengthError
from app.llm.types import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message,
    ToolCall,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import RegenerateRequest


def _fake_chat_resolution():
    """Return a SimpleNamespace mimicking ChatModelResolution for tests."""
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


async def setup_regeneration(
    monkeypatch, *, max_iterations=2, disconnect=None, error_retry=False
):
    user = SimpleNamespace(id=uuid4(), locale="en")
    team_id = uuid4()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=RAGMode.OFF,
        max_iterations=max_iterations,
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    user_message = SimpleNamespace(
        id=uuid4(),
        role=MessageRole.USER,
        content="question",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="old answer",
        created_at=datetime.now(timezone.utc),
        parent_id=None,
        branch_parent_id=user_message.id,
        round_status=(chat.MessageRoundStatus.ERROR if error_retry else None),
        round_id=None,
        tool_calls=None,
        token_usage=None,
        duration_ms=None,
        first_token_ms=None,
        reasoning_content=None,
        model_used=None,
        is_manually_stopped=False,
        version_number=1,
    )
    if error_retry:
        original.save = AsyncMock()
    created = SimpleNamespace(id=uuid4(), save=AsyncMock(), tool_calls=None)
    cleanup = Query()
    message_filter = Mock(side_effect=[Query(original)])
    monkeypatch.setattr(chat.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    agent_queries = iter([Query(agent), Query()])
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: next(agent_queries))
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: Query())
    prefix = AsyncMock(side_effect=[[user_message], [user_message]])
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))

    async def create_message(**values):
        if values.get("round_role") == chat.MessageRoundRole.ASSISTANT_FINAL:
            for key, value in values.items():
                setattr(created, key, value)
            return created
        return SimpleNamespace(id=uuid4(), **values)

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
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _compression: None)
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[original])
    )
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat, "now_utc", lambda: "stopped-at")

    request = SimpleNamespace(
        is_disconnected=disconnect or AsyncMock(return_value=False)
    )
    response = await chat.regenerate_message(
        agent.id,
        original.id,
        RegenerateRequest(),
        request,
        user,
    )
    message_filter.side_effect = lambda **_kwargs: cleanup
    return SimpleNamespace(
        response=response,
        agent=agent,
        conversation=conversation,
        original=original,
        created=created,
        cleanup=cleanup,
    )


async def collect(response):
    return "".join([event async for event in response.body_iterator])


def prepared(content="prompt"):
    return SimpleNamespace(
        messages=[Message(role="user", content=content)], compression=None
    )


@pytest.mark.anyio
async def test_regenerate_outer_loop_stops_when_heartbeat_detects_disconnect(
    monkeypatch,
):
    state = await setup_regeneration(monkeypatch)
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(False, 0))
    )

    events = await collect(state.response)

    assert "event: message_start" in events
    assert "event: message_end" not in events
    assert state.created.is_manually_stopped is True
    assert state.created.round_status == MessageRoundStatus.MANUALLY_STOPPED
    state.created.save.assert_awaited_once()


@pytest.mark.anyio
async def test_regenerate_outer_loop_retries_stream_context_then_disconnects(
    monkeypatch,
):
    disconnect = AsyncMock(return_value=True)
    state = await setup_regeneration(monkeypatch, disconnect=disconnect)
    retry = AsyncMock(return_value=prepared("retried"))
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(return_value=prepared())
    )
    monkeypatch.setattr(chat, "retry_prepare_model_context", retry)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    calls = 0

    async def chunks(_stream, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ContextLengthError
        yield ChatStreamChunk(
            id="partial",
            model="unit",
            delta=ChatStreamDelta(content="retried answer"),
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )
    events = await collect(state.response)

    assert "event: message_end" not in events
    retry.assert_awaited_once()
    assert state.created.is_manually_stopped is True


@pytest.mark.anyio
async def test_regenerate_outer_loop_executes_tool_then_hits_iteration_cap(monkeypatch):
    state = await setup_regeneration(monkeypatch, max_iterations=1)
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(return_value=prepared())
    )
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )

    async def chunks(_stream, **_kwargs):
        yield ChatStreamChunk(
            id="tool",
            model="unit",
            delta=ChatStreamDelta(tool_calls=[tool_call]),
            finish_reason=FinishReason.TOOL_CALLS,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )
    execute = AsyncMock(return_value="tool result")
    monkeypatch.setattr(chat, "execute_tool_call", execute)
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())
    monkeypatch.setattr(chat, "build_media_result_sse_event", lambda _result: None)

    events = await collect(state.response)

    assert "event: tool_call" in events
    assert '"arguments": {}' in events
    assert "event: iteration_cap_reached" in events
    assert state.created.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    execute.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("with_partial", [False, True])
async def test_regenerate_outer_loop_cancellation_restores_or_preserves_partial(
    monkeypatch, with_partial
):
    state = await setup_regeneration(monkeypatch)
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(return_value=prepared())
    )

    async def chunks(_stream, **_kwargs):
        if with_partial:
            yield ChatStreamChunk(
                id="partial", model="unit", delta=ChatStreamDelta(content="partial")
            )
        raise asyncio.CancelledError
        yield  # pragma: no cover

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert "event: message_end" not in events
    if with_partial:
        state.created.save.assert_awaited_once()
        state.cleanup.delete.assert_not_awaited()
    else:
        state.created.save.assert_not_awaited()
        state.cleanup.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_regenerate_errored_message_retries_in_place_without_new_version(
    monkeypatch,
):
    """Retrying an ERROR message must reuse the existing row: same message id,
    no version increment, no new branch/version created."""
    state = await setup_regeneration(monkeypatch, error_retry=True)
    monkeypatch.setattr(
        chat, "prepare_model_context", AsyncMock(return_value=prepared())
    )

    async def chunks(_stream, **_kwargs):
        yield ChatStreamChunk(
            id="content",
            model="unit",
            delta=ChatStreamDelta(content="retried answer"),
            finish_reason=FinishReason.STOP,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    blocks = [block for block in events.split("\n\n") if block.strip()]
    start = next(
        json.loads(block.split("data: ", 1)[1])
        for block in blocks
        if "event: message_start" in block
    )
    end = next(
        json.loads(block.split("data: ", 1)[1])
        for block in blocks
        if "event: message_end" in block
    )

    # Same message id, no version bump, no parent_id (no new version group).
    assert start["message_id"] == str(state.original.id)
    assert start["version_number"] == 1
    assert start["version_count"] == 1
    assert "parent_id" not in start
    assert end["version_number"] == 1
    assert end["version_count"] == 1
    # The errored row was cleared and persisted before streaming (a second
    # save writes the regenerated content at message_end), and the retry
    # completed in place on the SAME row.
    state.original.save.assert_awaited()
    assert state.original.round_status == chat.MessageRoundStatus.COMPLETED
    assert state.original.content == "retried answer"
