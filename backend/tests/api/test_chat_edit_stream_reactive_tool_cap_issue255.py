from contextlib import asynccontextmanager
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
    Message as LLMMessage,
    ToolCall,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import EditMessageRequest


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


@pytest.mark.anyio
async def test_edit_stream_reactive_retry_executes_tool_and_caps_iteration(monkeypatch):
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
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4(), save=AsyncMock())
    created_steps = []
    version_query = Query(count=1)
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
        AsyncMock(return_value="sandbox-session"),
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
    monkeypatch.setattr(
        chat, "get_tool_display_names", AsyncMock(return_value={"lookup": "Lookup"})
    )
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(chat, "build_compression_events", lambda **kwargs: (None, None))
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _compression: None)

    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="prepared context")],
        compression=None,
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    retry = AsyncMock(return_value=prepared)
    monkeypatch.setattr(chat, "retry_prepare_model_context", retry)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)

    streams = iter(["initial", "retry"])
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: next(streams)
    )
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )

    async def chunks(stream, **_kwargs):
        if stream == "initial":
            raise ContextLengthError()
        yield ChatStreamChunk(
            id="reasoning",
            model="stub/unit-model",
            delta=ChatStreamDelta(reasoning_content="thinking"),
        )
        yield ChatStreamChunk(
            id="content",
            model="stub/unit-model",
            delta=ChatStreamDelta(content="partial"),
        )
        yield ChatStreamChunk(
            id="tool",
            model="stub/unit-model",
            delta=ChatStreamDelta(tool_calls=[tool_call]),
        )
        yield ChatStreamChunk(
            id="done",
            model="stub/unit-model",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.LENGTH,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    execute = AsyncMock(return_value={"media": "result"})
    monkeypatch.setattr(chat, "execute_tool_call", execute)
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda _result: ("display", "llm")
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())
    monkeypatch.setattr(
        chat,
        "build_media_result_sse_event",
        lambda _result: "event: media\ndata: {}\n\n",
    )
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", AsyncMock())
    monkeypatch.setattr(chat.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(chat, "now_utc", lambda: "completed-at")

    response = await chat.edit_user_message_stream(
        agent.id,
        original.id,
        EditMessageRequest(content="edited"),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        user,
    )
    events = "".join([item async for item in response.body_iterator])

    assert "event: reasoning_start" in events
    assert 'data: {"delta": "thinking"}' in events
    assert "event: reasoning_end" in events
    assert 'data: {"delta": "partial"}' in events
    assert "event: output_truncated" in events
    assert '"arguments": {}' in events
    assert "event: tool_result" in events
    assert "event: media" in events
    assert "event: iteration_cap_reached" in events
    assert "event: message_end" in events
    retry.assert_awaited_once()
    execute.assert_awaited_once_with(
        "lookup",
        {},
        agent=agent,
        tool_timeouts={},
        user=user,
        session_id="sandbox-session",
        current_images=[],
        conversation_id=conversation.id,
    )
    assert [item.role for item in created_steps] == [
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert assistant.content
    assert assistant.reasoning_content is None
    assert assistant.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    assistant.save.assert_awaited_once()
