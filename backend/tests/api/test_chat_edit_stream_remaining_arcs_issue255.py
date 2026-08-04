import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.types import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    ToolCall,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import EditMessageRequest


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
    def __init__(self, value=None, *, count=0, exists=True):
        self.value = value
        self.count_value = count
        self.exists_value = exists
        self.update = AsyncMock(return_value=1)
        self.delete = AsyncMock(return_value=1)

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


async def collect(response):
    return "".join([event async for event in response.body_iterator])


async def setup_edit(monkeypatch, *, max_iterations=2, active=True):
    user = SimpleNamespace(id=uuid4(), locale="en")
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        team=None,
        rag_mode=RAGMode.OFF,
        max_iterations=max_iterations,
    )
    conversation = SimpleNamespace(id=uuid4(), agent_id=agent.id)
    original = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="original",
        branch_parent_id=uuid4(),
        images=None,
        file_urls=None,
    )
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created_steps = []
    active_query = Query(exists=active)
    cleanup_query = Query()
    agent_query = Query(agent)
    conversation_query = Query(conversation)

    def message_filter(*_args, **kwargs):
        if kwargs == {"id": original.id}:
            return Query(original)
        if "is_active" in kwargs:
            return active_query
        if "id" in kwargs and len(kwargs) == 1:
            return cleanup_query
        return Query(count=1)

    monkeypatch.setattr(chat.Message, "filter", message_filter)
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: conversation_query
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: agent_query)
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(chat, "in_transaction", transaction)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        chat, "find_descendant_branch_from", AsyncMock(return_value=[original])
    )

    async def create_message(**values):
        if not hasattr(edited, "content"):
            item = edited
        elif not hasattr(assistant, "content"):
            item = assistant
        else:
            item = SimpleNamespace(id=uuid4(), **values)
            created_steps.append(item)
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
        "resolve_agent_chat_model",
        AsyncMock(return_value=_fake_chat_resolution()),
    )
    monkeypatch.setattr(
        chat,
        "get_agent_tools",
        AsyncMock(
            return_value=[
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup",
                        "parameters": {"type": "object"},
                    },
                }
            ]
        ),
    )
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))

    async def heartbeat(last_event_time, *_args):
        return True, last_event_time + 1

    monkeypatch.setattr(chat, "send_heartbeat_if_needed", heartbeat)
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat, "now_utc", lambda: "now")
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    response = await chat.edit_user_message_stream(
        agent.id,
        original.id,
        EditMessageRequest(content="edited"),
        request,
        user,
    )
    return SimpleNamespace(
        response=response,
        request=request,
        agent=agent,
        assistant=assistant,
        edited=edited,
        cleanup_query=cleanup_query,
        active_query=active_query,
        created_steps=created_steps,
    )


@pytest.mark.anyio
async def test_edit_stream_remaining_arcs_runs_tool_round_then_terminal_round(
    monkeypatch,
):
    state = await setup_edit(monkeypatch)
    prepared = SimpleNamespace(
        messages=[
            LLMMessage(role="user", content="12345678"),
            LLMMessage(role="assistant", content=None),
        ],
        compression=object(),
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        lambda **_kwargs: ("compress-start", "compress-end"),
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _compression: "budget")

    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments='{"query": "x"}'),
    )
    streams = iter(["tool-round", "terminal-round"])
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: next(streams)
    )

    async def chunks(stream, **_kwargs):
        if stream == "tool-round":
            yield ChatStreamChunk(
                id="reasoning",
                model="stub",
                delta=ChatStreamDelta(reasoning_content="think"),
            )
            yield ChatStreamChunk(
                id="content",
                model="stub",
                delta=ChatStreamDelta(content="draft"),
            )
            yield ChatStreamChunk(
                id="tool",
                model="stub",
                delta=ChatStreamDelta(tool_calls=[tool_call]),
                finish_reason=FinishReason.TOOL_CALLS,
            )
        else:
            yield ChatStreamChunk(
                id="reasoning-only",
                model="stub",
                delta=ChatStreamDelta(reasoning_content="final thought"),
                finish_reason=FinishReason.STOP,
            )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(chat, "execute_tool_call", AsyncMock(return_value="raw"))
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda _result: ("display", "llm result")
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())
    monkeypatch.setattr(chat, "build_media_result_sse_event", lambda _result: None)
    monkeypatch.setattr(
        chat.AuditLogService, "log", AsyncMock(side_effect=RuntimeError("audit down"))
    )

    events = await collect(state.response)

    assert events.count(": heartbeat") == 2
    assert events.count("compress-start") == 2
    assert events.count("compress-end") == 2
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: content_delta" in events
    assert "event: tool_call" in events
    assert "event: tool_result" in events
    assert "event: message_end" in events
    assert "event: iteration_cap_reached" not in events
    assert [item.role for item in state.created_steps] == [
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert state.assistant.content == ""
    assert state.assistant.reasoning_content == "final thought"
    assert state.assistant.round_status == MessageRoundStatus.COMPLETED
    state.assistant.save.assert_awaited_once()
    chat.execute_tool_call.assert_awaited_once()
    chat.AuditLogService.log.assert_awaited_once()


@pytest.mark.anyio
async def test_edit_stream_remaining_arcs_cancellation_removes_empty_inactive_branch(
    monkeypatch,
):
    state = await setup_edit(monkeypatch, active=False)
    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="prepared")], compression=None
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )

    async def cancelled(_stream, **_kwargs):
        raise asyncio.CancelledError
        yield

    monkeypatch.setattr(chat, "iter_with_idle_timeout", cancelled)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert "event: message_start" in events
    assert "event: message_end" not in events
    state.assistant.save.assert_not_awaited()
    state.cleanup_query.delete.assert_awaited_once()
    state.cleanup_query.update.assert_awaited_once_with(is_active=False)
    assert state.active_query.exists_value is False
