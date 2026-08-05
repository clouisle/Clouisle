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
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest, RegenerateRequest


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
    def __init__(self, value=None):
        self.value = value
        self.update = AsyncMock(return_value=1)
        self.delete = AsyncMock(return_value=1)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value


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
    items = [
        item.decode() if isinstance(item, bytes) else item
        async for item in response.body_iterator
    ]
    return "".join(items)


@pytest.mark.anyio
async def test_send_retries_context_and_caps_tool_iterations(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
        rag_mode=RAGMode.OFF,
        enable_attachments=False,
        enable_user_input_request=False,
        max_iterations=1,
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
    tool_call = ToolCall(
        id="tool-1",
        type="function",
        function=FunctionCall(name="lookup", arguments=""),
    )
    response = ChatResponse(
        id="response",
        model="stub/unit",
        content=None,
        tool_calls=[tool_call],
        finish_reason=FinishReason.TOOL_CALLS,
        usage=Usage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
    )
    update_query = Query()

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(side_effect=create_message))
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
        chat, "build_file_content_for_context", AsyncMock(return_value=("", ["new"]))
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
                        "description": "lookup",
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
        chat, "prepare_model_context", AsyncMock(side_effect=ContextLengthError())
    )
    retry = AsyncMock(return_value=prepared)
    monkeypatch.setattr(chat, "retry_prepare_model_context", retry)
    monkeypatch.setattr(chat, "should_retry_context_length", lambda _agent: True)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat", AsyncMock(return_value=response)
    )
    monkeypatch.setattr(chat, "execute_tool_call", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(
        chat, "get_tool_execution_payloads", lambda result: (result, result)
    )
    monkeypatch.setattr(chat, "append_generated_images", Mock())
    monkeypatch.setattr(chat, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat.Conversation, "filter", Mock(return_value=update_query))
    monkeypatch.setattr(chat.Agent, "filter", Mock(return_value=update_query))

    result = await chat.chat(agent.id, ChatRequest(message="hello"), (user, None))

    assert (
        result["data"].message.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    )
    assert created[0].file_urls == ["new"]
    created[0].save.assert_awaited_once_with(update_fields=["file_urls"])
    assert created[1].tool_calls[0]["arguments"] == {}
    assert created[-1].content
    retry.assert_awaited_once()
    chat.execute_tool_call.assert_awaited_once_with(
        "lookup",
        {},
        agent=agent,
        tool_timeouts={},
        user=user,
        session_id="session",
        current_images=[],
        conversation_id=conversation.id,
    )


async def setup_regenerate(monkeypatch, *, rag_mode=RAGMode.OFF, branch_parent_id=None):
    user = SimpleNamespace(id=uuid4(), locale="en")
    team = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(), team_id=team.id, team=team, rag_mode=rag_mode, max_iterations=1
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
        content="old",
        created_at=datetime.now(UTC),
        parent_id=None,
        branch_parent_id=branch_parent_id,
    )
    created = StoredMessage(conversation=conversation, role=MessageRole.ASSISTANT)
    prefix = AsyncMock(return_value=[user_message])

    monkeypatch.setattr(chat.Message, "filter", lambda **_kwargs: Query(original))
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda **_kwargs: Query(conversation)
    )
    agent_queries = iter([Query(agent), Query()])
    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: next(agent_queries))
    monkeypatch.setattr(chat.Team, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(chat, "get_prefix_path_before", prefix)
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: original.id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))

    async def create_message(**values):
        for name, value in values.items():
            setattr(created, name, value)
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
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(
        chat, "stale_session_memory_if_source_outside_active_branch", AsyncMock()
    )

    monkeypatch.setattr(chat, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(chat, "now_utc", lambda: "now")

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
        original=original,
        created=created,
        user_message=user_message,
    )


@pytest.mark.anyio
async def test_regenerate_generator_handles_rag_compression_and_length(monkeypatch):
    state = await setup_regenerate(monkeypatch, rag_mode=RAGMode.AUTO)
    monkeypatch.setattr(chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=True))
    monkeypatch.setattr(
        chat, "perform_rag_retrieval", AsyncMock(return_value=[{"content": "context"}])
    )
    monkeypatch.setattr(chat, "aggregate_rag_contexts", lambda contexts: contexts)
    monkeypatch.setattr(chat, "build_rag_prompt", lambda _contexts, text: f"rag:{text}")
    prepared = SimpleNamespace(
        messages=[LLMMessage(role="user", content="prepared")],
        compression=SimpleNamespace(),
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat,
        "build_compression_events",
        lambda **_kwargs: ("compression-start", "compression-end"),
    )
    monkeypatch.setattr(chat, "get_compression_trigger", lambda _value: "budget")
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 2**62))
    )

    async def chunks(_stream, **_kwargs):
        yield ChatStreamChunk(
            id="reason",
            model="stub",
            delta=ChatStreamDelta(reasoning_content="thinking"),
        )
        yield ChatStreamChunk(
            id="done",
            model="stub",
            delta=ChatStreamDelta(),
            finish_reason=FinishReason.LENGTH,
        )

    monkeypatch.setattr(chat, "iter_with_idle_timeout", chunks)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = await collect(state.response)

    assert "event: rag_start" in events
    assert "event: rag_context" in events
    assert ": heartbeat" in events
    assert "compression-startcompression-end" in events
    assert "event: reasoning_start" in events
    assert "event: reasoning_end" in events
    assert "event: output_truncated" in events
    assert "event: message_end" in events
    assert state.created.branch_parent_id == state.user_message.id
    assert state.created.reasoning_content == "thinking"
    assert state.created.round_status == MessageRoundStatus.COMPLETED


@pytest.mark.anyio
async def test_regenerate_generator_stops_before_generation(monkeypatch):
    state = await setup_regenerate(monkeypatch, branch_parent_id=uuid4())
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(False, 0))
    )

    events = await collect(state.response)

    assert "event: message_start" in events
    assert "event: message_end" not in events
    assert state.created.is_manually_stopped is True
    assert state.created.round_status == MessageRoundStatus.MANUALLY_STOPPED
    state.created.save.assert_awaited_once()
    chat.activate_conversation_branch.assert_awaited_once()
