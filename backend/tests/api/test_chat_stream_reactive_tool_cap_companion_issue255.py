from datetime import UTC, datetime
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
from app.schemas.agent import ChatRequest


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
            "file_urls": None,
            "reasoning_content": None,
            "tool_calls": None,
            "model_used": None,
            "token_usage": None,
            "duration_ms": None,
            "first_token_ms": None,
            "is_manually_stopped": False,
            "round_status": None,
        }.items():
            setattr(self, name, values.get(name, default))


async def collect(response):
    items = [
        item.decode() if isinstance(item, bytes) else item
        async for item in response.body_iterator
    ]
    return "".join(items)


@pytest.mark.anyio
async def test_stream_retries_context_then_persists_tool_cap(monkeypatch):
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
    conversation = SimpleNamespace(id=uuid4(), title="")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    created = []

    async def create_message(**values):
        message = StoredMessage(**values)
        created.append(message)
        return message

    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="prepared context")],
        compression=SimpleNamespace(),
    )
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments="not-json"),
    )
    updates = Query()

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=True))
    monkeypatch.setattr(
        chat, "perform_rag_retrieval", AsyncMock(return_value=[{"content": "source"}])
    )
    monkeypatch.setattr(chat, "aggregate_rag_contexts", lambda contexts: contexts)
    monkeypatch.setattr(
        chat, "build_rag_prompt", lambda contexts, text: f"{contexts}:{text}"
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(side_effect=create_message))
    monkeypatch.setattr(chat, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat,
        "get_streaming_config",
        lambda _agent: {
            "global_timeout": 10,
            "heartbeat_interval": 1,
            "idle_timeout": 3,
            "tool_timeouts": {},
        },
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        AsyncMock(return_value="session"),
    )
    monkeypatch.setattr(
        chat, "build_file_content_for_context", AsyncMock(return_value=("files", None))
    )
    model = SimpleNamespace(
        id=uuid4(),
        is_enabled=True,
        provider="stub",
        model_id="unit",
        context_length=4096,
        max_output_tokens=512,
        capabilities={},
    )
    model_resolution = SimpleNamespace(
        model=model,
        team_model=SimpleNamespace(model=model, is_enabled=True),
        model_id=str(model.id),
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
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _images: text
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
    prepare = AsyncMock(return_value=prepared)
    retry = AsyncMock(return_value=prepared)
    monkeypatch.setattr(chat, "prepare_model_context", prepare)
    monkeypatch.setattr(chat, "retry_prepare_model_context", retry)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        lambda **kwargs: (
            (
                "event: compression_start\ndata: {}\n\n",
                "event: compression_end\ndata: {}\n\n",
            )
            if kwargs.get("stage_override")
            else (None, None)
        ),
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _value: None)
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 2**62))
    )

    streams = iter(["first", "retry"])
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: next(streams)
    )

    async def chunks(stream, **_kwargs):
        if stream == "first":
            raise ContextLengthError()
        yield ChatStreamChunk(
            id="reason",
            model="stub/unit",
            delta=ChatStreamDelta(reasoning_content="thinking"),
        )
        yield ChatStreamChunk(
            id="answer",
            model="stub/unit",
            delta=ChatStreamDelta(content="partial"),
        )
        yield ChatStreamChunk(
            id="tool",
            model="stub/unit",
            delta=ChatStreamDelta(tool_calls=[tool_call]),
        )
        yield ChatStreamChunk(
            id="done",
            model="stub/unit",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.LENGTH,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    record_usage = AsyncMock()
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", record_usage)
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
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=updates))
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=updates))
    monkeypatch.setattr(chat.Team, "filter", Mock(return_value=updates))

    response = await chat.chat_stream(
        agent.id,
        ChatRequest(message="x" * 60),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        (user, None),
    )
    events = await collect(response)

    assert "event: rag_start" in events
    assert "event: rag_context" in events
    assert ": heartbeat" in events
    assert "event: compression_start" in events
    assert "event: reasoning_start" in events
    assert 'data: {"delta": "thinking"}' in events
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
        session_id="session",
        current_images=[],
        conversation_id=conversation.id,
    )
    assert [message.role for message in created] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assistant = created[1]
    assert assistant.reasoning_content is None
    assert assistant.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    assert assistant.token_usage["prompt"] > 0
    assistant.save.assert_awaited_once()
    record_usage.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once()
    assert updates.update.await_count == 3
