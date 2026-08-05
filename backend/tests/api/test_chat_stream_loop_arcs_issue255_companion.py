from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import ContextLengthError
from app.llm.types import (
    ChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    ToolCall,
    Usage,
)
from app.models.agent import MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest


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
    def __init__(self):
        self.update = AsyncMock(return_value=1)


class StoredMessage:
    def __init__(self, **values):
        self.id = uuid4()
        self.conversation_id = values["conversation"].id
        self.created_at = datetime.now(UTC)
        self.save = AsyncMock()
        for name, default in {
            "content": "",
            "role": None,
            "images": None,
            "file_urls": None,
            "reasoning_content": None,
            "tool_calls": None,
            "tool_call_id": None,
            "tool_name": None,
            "model_used": None,
            "token_usage": None,
            "duration_ms": None,
            "first_token_ms": None,
            "is_manually_stopped": False,
            "round_status": None,
            "parent_id": None,
            "branch_parent_id": None,
            "version_number": 1,
            "is_active": True,
        }.items():
            setattr(self, name, values.get(name, default))


async def collect(response):
    return "".join(
        [
            item.decode() if isinstance(item, bytes) else item
            async for item in response.body_iterator
        ]
    )


async def setup_stream(monkeypatch, *, max_iterations=1, disconnected=False):
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team.id,
        team=team,
        rag_mode=RAGMode.OFF,
        enable_attachments=False,
        enable_user_input_request=False,
        max_iterations=max_iterations,
    )
    conversation = SimpleNamespace(id=uuid4(), title="existing")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    created = []

    async def create_message(**values):
        message = StoredMessage(**values)
        created.append(message)
        return message

    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="hello")], compression=None
    )
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
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat, "build_file_content_for_context", AsyncMock(return_value=("", None))
    )
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a, **_k: ([], []))
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
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", AsyncMock())
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(chat, "now_utc", lambda: datetime.now(UTC))
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=disconnected))
    response = await chat.chat_stream(
        agent.id, ChatRequest(message="hello"), request, (user, None)
    )
    return SimpleNamespace(
        response=response,
        agent=agent,
        conversation=conversation,
        user=user,
        request=request,
        created=created,
        prepared=prepared,
    )


async def chunks(*items):
    for item in items:
        if isinstance(item, BaseException):
            raise item
        yield item


@pytest.mark.anyio
async def test_stream_loop_can_be_skipped(monkeypatch):
    state = await setup_stream(monkeypatch, max_iterations=-1)

    events = await collect(state.response)

    assert "event: message_end" in events
    assert state.created[1].round_status == MessageRoundStatus.COMPLETED


@pytest.mark.anyio
async def test_stream_emits_compression_reasoning_content_and_length(monkeypatch):
    state = await setup_stream(monkeypatch)
    state.prepared.compression = SimpleNamespace()
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: ("start", "end")
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _value: "budget")
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream",
        lambda **_kwargs: chunks(
            ChatStreamChunk(
                id="reason",
                model="stub",
                delta=ChatStreamDelta(reasoning_content="think"),
            ),
            ChatStreamChunk(
                id="content",
                model="stub",
                delta=ChatStreamDelta(content="answer"),
            ),
            ChatStreamChunk(
                id="done",
                model="stub",
                delta=ChatStreamDelta(),
                finish_reason=FinishReason.LENGTH,
            ),
        ),
    )

    events = await collect(state.response)

    assert "startend" in events
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: content_delta" in events
    assert "event: output_truncated" in events


@pytest.mark.anyio
async def test_stream_retries_context_error_from_prepare(monkeypatch):
    state = await setup_stream(monkeypatch)
    chat.prepare_model_context.side_effect = ContextLengthError()
    retried = SimpleNamespace(
        messages=[LLMMessage(role="user", content="retried")],
        compression=SimpleNamespace(),
    )
    monkeypatch.setattr(
        chat, "retry_prepare_model_context", AsyncMock(return_value=retried)
    )
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: ("retry-start", "retry-end")
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream",
        lambda **_kwargs: chunks(
            ChatStreamChunk(
                id="done",
                model="stub",
                delta=ChatStreamDelta(content="ok"),
                finish_reason=FinishReason.STOP,
            )
        ),
    )

    events = await collect(state.response)

    assert "retry-startretry-end" in events
    chat.retry_prepare_model_context.assert_awaited_once()


@pytest.mark.anyio
async def test_stream_retries_context_error_from_model(monkeypatch):
    state = await setup_stream(monkeypatch)
    retried = SimpleNamespace(
        messages=[LLMMessage(role="user", content="retry")],
        compression=SimpleNamespace(),
    )
    monkeypatch.setattr(
        chat, "retry_prepare_model_context", AsyncMock(return_value=retried)
    )
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        lambda **_kwargs: ("reactive-start", "reactive-end"),
    )
    streams = iter(
        [
            chunks(ContextLengthError()),
            chunks(
                ChatStreamChunk(
                    id="reason",
                    model="stub",
                    delta=ChatStreamDelta(reasoning_content="think"),
                ),
                ChatStreamChunk(
                    id="tool",
                    model="stub",
                    delta=ChatStreamDelta(
                        tool_calls=[
                            ToolCall(
                                id="empty",
                                type="function",
                                function=FunctionCall(name="", arguments="{}"),
                            )
                        ]
                    ),
                    finish_reason=FinishReason.LENGTH,
                ),
            ),
        ]
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: next(streams)
    )

    events = await collect(state.response)

    assert "reactive-startreactive-end" in events
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: output_truncated" in events


@pytest.mark.anyio
async def test_stream_falls_back_when_stream_is_empty(monkeypatch):
    state = await setup_stream(monkeypatch)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: chunks()
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(
            return_value=ChatResponse(
                id="fallback",
                model="stub",
                content="answer",
                reasoning_content="think",
                finish_reason=FinishReason.STOP,
                usage=Usage(),
            )
        ),
    )

    events = await collect(state.response)

    assert "event: reasoning_delta" in events
    assert "event: content_delta" in events
    assert state.created[1].round_status == MessageRoundStatus.COMPLETED


@pytest.mark.anyio
@pytest.mark.parametrize("disconnect_after_tool", [False, True])
async def test_stream_tool_disconnect_boundaries(monkeypatch, disconnect_after_tool):
    state = await setup_stream(monkeypatch)
    state.request.is_disconnected.side_effect = (
        [False, False, True] if disconnect_after_tool else [False, True]
    )
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream",
        lambda **_kwargs: chunks(
            ChatStreamChunk(
                id="tool",
                model="stub",
                delta=ChatStreamDelta(tool_calls=[tool_call]),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        ),
    )
    execute = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(chat, "execute_tool_call", execute)
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())

    await collect(state.response)

    if disconnect_after_tool:
        execute.assert_awaited_once()
    else:
        execute.assert_not_awaited()
    assert state.created[1].round_status == MessageRoundStatus.MANUALLY_STOPPED


@pytest.mark.anyio
async def test_stream_tool_emits_media_result(monkeypatch):
    state = await setup_stream(monkeypatch)
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments='{"query": "x"}'),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream",
        lambda **_kwargs: chunks(
            ChatStreamChunk(
                id="tool-start",
                model="stub",
                delta=ChatStreamDelta(tool_call_starts=[tool_call]),
            ),
            ChatStreamChunk(
                id="tool",
                model="stub",
                delta=ChatStreamDelta(tool_calls=[tool_call]),
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        ),
    )
    monkeypatch.setattr(
        chat, "execute_tool_call", AsyncMock(return_value={"image": "x"})
    )
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())
    monkeypatch.setattr(chat, "build_media_result_sse_event", lambda _result: "media")

    events = await collect(state.response)

    assert "event: tool_call" in events
    assert events.count("event: tool_call\n") == 2
    assert events.index('"arguments": {}') < events.index('"arguments": {"query": "x"}')
    assert "event: tool_result" in events
    assert "media" in events
    assert "event: iteration_cap_reached" in events
