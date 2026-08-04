from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_api
from app.llm.errors import LLMError, ModelNotFoundError, QuotaExceededError
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    Message as LLMMessage,
    MessageRole as LLMMessageRole,
    Usage,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError, ResponseCode


class StoredMessage:
    def __init__(self, **values):
        self.id = uuid4()
        self.conversation_id = values["conversation"].id
        self.created_at = datetime.now(UTC)
        self.parent_id = None
        self.is_active = True
        self.version_number = 1
        self.save = AsyncMock()
        self.delete = AsyncMock()
        for name, default in {
            "content": "",
            "images": None,
            "file_urls": None,
            "tool_calls": None,
            "tool_call_id": None,
            "tool_name": None,
            "reasoning_content": None,
            "model_used": None,
            "token_usage": None,
            "duration_ms": None,
            "first_token_ms": None,
            "is_manually_stopped": False,
            "rag_context": None,
            "round_id": None,
            "round_index": 0,
            "round_role": None,
            "is_round_canonical": False,
            "iteration_index": None,
            "round_status": None,
            "branch_parent_id": None,
        }.items():
            setattr(self, name, values.get(name, default))
        self.role = values["role"]


@pytest.fixture
def core_chat(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
        rag_mode=RAGMode.AGENTIC,
        enable_vision=False,
        enable_user_input_request=False,
        max_iterations=1,
    )
    conversation = SimpleNamespace(id=uuid4(), title=None)
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    created = []

    async def create_message(**values):
        message = StoredMessage(**values)
        created.append(message)
        return message

    prepared = SimpleNamespace(
        messages=[LLMMessage(role=LLMMessageRole.USER, content="hello")],
        compression=None,
    )
    team_model = SimpleNamespace(
        model=SimpleNamespace(
            id=uuid4(),
            is_enabled=True,
            provider="mock",
            model_id="unit",
            capabilities={},
            context_length=4096,
            max_output_tokens=512,
        )
    )
    update_query = SimpleNamespace(update=AsyncMock())

    monkeypatch.setattr(chat_api.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat_api, "check_agent_chat_access", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        chat_api, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat_api, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat_api.Message, "create", create_message)
    monkeypatch.setattr(chat_api, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat_api, "get_agent_chat_model", AsyncMock(return_value=team_model)
    )
    monkeypatch.setattr(
        chat_api,
        "get_streaming_config",
        lambda _agent: {
            "global_timeout": 30,
            "heartbeat_interval": 30,
            "idle_timeout": 30,
            "tool_timeouts": {},
        },
    )
    monkeypatch.setattr(
        chat_api, "build_file_content_for_context", AsyncMock(return_value=("", None))
    )
    monkeypatch.setattr(
        chat_api, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat_api, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat_api, "prepare_model_context", AsyncMock(return_value=prepared)
    )
    monkeypatch.setattr(
        chat_api, "build_compression_events", Mock(return_value=(None, None))
    )
    monkeypatch.setattr(
        chat_api, "round_has_persisted_trace", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        chat_api, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(chat_api, "get_prefix_path_before", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_api, "activate_conversation_branch", AsyncMock())

    monkeypatch.setattr(chat_api, "enqueue_session_memory_extraction", Mock())
    monkeypatch.setattr(
        chat_api.Conversation, "filter", Mock(return_value=update_query)
    )
    monkeypatch.setattr(chat_api.Agent, "filter", Mock(return_value=update_query))
    monkeypatch.setattr(chat_api.Team, "filter", Mock(return_value=update_query))
    monkeypatch.setattr(chat_api, "t", lambda key, **kwargs: key)

    from app.llm import model_manager
    from app.services.sandbox.gateway import sandbox_gateway

    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="session")
    )
    monkeypatch.setattr(model_manager, "record_stream_usage", AsyncMock())

    return SimpleNamespace(
        agent=agent,
        conversation=conversation,
        user=user,
        created=created,
        prepared=prepared,
        model_manager=model_manager,
    )


@pytest.mark.asyncio
async def test_chat_success_persists_round_and_usage(core_chat, monkeypatch):
    response = LLMChatResponse(
        id="response",
        model="mock/unit",
        content="answer",
        reasoning_content="reason",
        finish_reason=FinishReason.STOP,
        usage=Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
    )
    monkeypatch.setattr(
        core_chat.model_manager, "team_chat", AsyncMock(return_value=response)
    )

    result = await chat_api.chat(
        core_chat.agent.id,
        ChatRequest(message="hello"),
        (core_chat.user, None),
    )

    user_message, assistant_message = core_chat.created
    assert result["data"].message.content == "answer"
    assert result["data"].usage["total_tokens"] == 10
    assert user_message.role == MessageRole.USER
    assert assistant_message.branch_parent_id == user_message.id
    assert assistant_message.token_usage == {"prompt": 7, "completion": 3}
    assert assistant_message.round_status == MessageRoundStatus.COMPLETED
    chat_api.activate_conversation_branch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_error", "expected_code", "expected_status"),
    [
        (
            QuotaExceededError(quota_type="tokens"),
            ResponseCode.MODEL_QUOTA_EXCEEDED,
            429,
        ),
        (LLMError("provider failed"), ResponseCode.UNKNOWN_ERROR, 500),
    ],
)
async def test_chat_maps_model_failures(
    core_chat, monkeypatch, model_error, expected_code, expected_status
):
    monkeypatch.setattr(
        core_chat.model_manager, "team_chat", AsyncMock(side_effect=model_error)
    )

    with pytest.raises(BusinessError) as exc_info:
        await chat_api.chat(
            core_chat.agent.id,
            ChatRequest(message="hello"),
            (core_chat.user, None),
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.status_code == expected_status
    assert len(core_chat.created) == 1


async def _collect_stream(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_chat_stream_generator_persists_completed_assistant(
    core_chat, monkeypatch
):
    async def stream(**_kwargs):
        yield ChatStreamChunk(
            id="chunk",
            model="mock/unit",
            delta=ChatStreamDelta(reasoning_content="think"),
        )
        yield ChatStreamChunk(
            id="chunk",
            model="mock/unit",
            delta=ChatStreamDelta(content="answer"),
            finish_reason=FinishReason.STOP,
        )

    monkeypatch.setattr(core_chat.model_manager, "team_chat_stream", stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.chat_stream(
        core_chat.agent.id,
        ChatRequest(message="hello"),
        request,
        (core_chat.user, None),
    )
    events = await _collect_stream(response)

    user_message, assistant_message = core_chat.created
    assert "event: message_start" in events
    assert 'data: {"delta": "think"}' in events
    assert 'data: {"delta": "answer"}' in events
    assert "event: message_end" in events
    assert assistant_message.content == "answer"
    assert assistant_message.reasoning_content == "think"
    assert assistant_message.branch_parent_id == user_message.id
    assert assistant_message.round_status == MessageRoundStatus.COMPLETED
    assistant_message.save.assert_awaited_once()
    chat_api.activate_conversation_branch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_error", "expected_code"),
    [
        (QuotaExceededError(quota_type="tokens"), ResponseCode.MODEL_QUOTA_EXCEEDED),
        (ModelNotFoundError(), ResponseCode.MODEL_NOT_FOUND),
        (LLMError("provider failed"), ResponseCode.UNKNOWN_ERROR),
    ],
)
async def test_chat_stream_generator_persists_model_failures(
    core_chat, monkeypatch, model_error, expected_code
):
    async def failing_stream(**_kwargs):
        raise model_error
        yield

    monkeypatch.setattr(core_chat.model_manager, "team_chat_stream", failing_stream)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))

    response = await chat_api.chat_stream(
        core_chat.agent.id,
        ChatRequest(message="hello"),
        request,
        (core_chat.user, None),
    )
    events = await _collect_stream(response)

    assistant_message = core_chat.created[1]
    assert f'"code": {expected_code}' in events
    assert assistant_message.content
    assert assistant_message.round_status == MessageRoundStatus.ERROR
    assistant_message.save.assert_awaited_once()
