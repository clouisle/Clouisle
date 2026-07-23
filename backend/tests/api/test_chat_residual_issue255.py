from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.api.v1.endpoints import chat as chat_endpoint
from app.llm.errors import ContextLengthError, InsufficientQuotaError, LLMError
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    FinishReason,
    FunctionCall,
    Message as LLMMessage,
    MessageRole as LLMMessageRole,
    ToolCall,
)
from app.llm.types.base import Usage
from app.models.agent import MessageRoundRole, MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import BusinessError, ResponseCode


class _AsyncCallable:
    def __init__(self, result=None, side_effect=None):
        self.result = result
        self.side_effect = side_effect
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.side_effect:
            if isinstance(self.side_effect, list):
                effect = self.side_effect.pop(0)
            else:
                effect = self.side_effect
            if isinstance(effect, BaseException):
                raise effect
            return effect
        return self.result


class _Query:
    def __init__(self):
        self.updates = []

    def prefetch_related(self, *args):
        return self

    async def first(self):
        return None

    async def update(self, **kwargs):
        self.updates.append(kwargs)
        return 1


class _Model:
    @classmethod
    def filter(cls, *args, **kwargs):
        query = _Query()
        cls.last_query = query
        return query


class _FakeMessage(_Model):
    created = []

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id", uuid4())
        self.conversation_id = kwargs.get("conversation_id", uuid4())
        self.created_at = kwargs.get("created_at", datetime.now(UTC))
        self.is_active = kwargs.get("is_active", True)
        self.version_number = kwargs.get("version_number", 1)
        self.version_count = kwargs.get("version_count", 1)
        self.versions = kwargs.get("versions")
        self.steps = kwargs.get("steps")

    @classmethod
    async def create(cls, **kwargs):
        message = cls(**kwargs)
        message.conversation_id = kwargs["conversation"].id
        cls.created.append(message)
        return message

    async def save(self, *args, **kwargs):
        self.saved = (args, kwargs)


class _FakeConversation(_Model):
    last_query = None


class _FakeAgentModel(_Model):
    last_query = None


@pytest.fixture
def chat_harness(monkeypatch):
    _FakeMessage.created = []
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        team=SimpleNamespace(id=uuid4()),
        rag_mode=RAGMode.AGENTIC,
        enable_vision=True,
        enable_user_input_request=False,
        max_iterations=2,
        context_compression_config={},
    )
    conversation = SimpleNamespace(id=uuid4(), title=None)
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en", is_superuser=False)
    team_model = SimpleNamespace(
        model=SimpleNamespace(
            provider="fake",
            model_id="chat",
            context_length=4096,
            max_output_tokens=1024,
            capabilities={"vision": True},
        )
    )
    prepared_context = SimpleNamespace(
        messages=[LLMMessage(role=LLMMessageRole.USER, content="prepared")]
    )
    model_manager = SimpleNamespace(team_chat=_AsyncCallable())

    monkeypatch.setattr(
        chat_endpoint.deps, "check_api_key_agent_access", _AsyncCallable()
    )
    monkeypatch.setattr(chat_endpoint, "check_agent_chat_access", _AsyncCallable(agent))
    monkeypatch.setattr(
        chat_endpoint, "get_or_create_conversation", _AsyncCallable(conversation)
    )
    monkeypatch.setattr(
        chat_endpoint, "get_next_user_branch_parent_id", _AsyncCallable(None)
    )
    monkeypatch.setattr(chat_endpoint, "update_message_stats", _AsyncCallable())
    monkeypatch.setattr(
        chat_endpoint, "get_agent_chat_model", _AsyncCallable(team_model)
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_streaming_config",
        lambda agent: {"tool_timeouts": {"default": 1}},
    )
    monkeypatch.setattr(
        "app.services.sandbox.gateway.sandbox_gateway.create_session",
        _AsyncCallable("session-1"),
    )
    monkeypatch.setattr(
        chat_endpoint, "build_file_content_for_context", _AsyncCallable((None, None))
    )
    monkeypatch.setattr(
        chat_endpoint, "get_visible_conversation_messages", _AsyncCallable([])
    )
    monkeypatch.setattr(
        chat_endpoint, "collect_conversation_images", lambda *a, **k: ({}, [])
    )
    monkeypatch.setattr(
        chat_endpoint,
        "append_conversation_image_inventory",
        lambda message, inventory: message,
    )
    monkeypatch.setattr(chat_endpoint, "get_agent_tools", _AsyncCallable([]))
    monkeypatch.setattr(chat_endpoint, "get_tool_display_names", _AsyncCallable({}))
    monkeypatch.setattr(
        chat_endpoint, "prepare_model_context", _AsyncCallable(prepared_context)
    )
    monkeypatch.setattr(
        chat_endpoint, "retry_prepare_model_context", _AsyncCallable(prepared_context)
    )
    monkeypatch.setattr(
        chat_endpoint, "should_retry_context_length", lambda agent: True
    )
    monkeypatch.setattr(
        chat_endpoint, "execute_tool_call", _AsyncCallable("tool display")
    )
    monkeypatch.setattr(
        chat_endpoint,
        "get_tool_execution_payloads",
        lambda result: (result, "tool llm"),
    )
    monkeypatch.setattr(chat_endpoint, "append_generated_images", lambda *a, **k: None)
    monkeypatch.setattr(chat_endpoint, "get_prefix_path_before", _AsyncCallable([]))
    monkeypatch.setattr(chat_endpoint, "activate_conversation_branch", _AsyncCallable())
    monkeypatch.setattr(
        chat_endpoint, "persist_macro_summary_best_effort", _AsyncCallable()
    )
    monkeypatch.setattr(
        chat_endpoint, "enqueue_session_memory_extraction", lambda *a: None
    )
    monkeypatch.setattr(chat_endpoint, "Message", _FakeMessage)
    monkeypatch.setattr(chat_endpoint, "Conversation", _FakeConversation)
    monkeypatch.setattr(chat_endpoint, "Agent", _FakeAgentModel)
    import app.llm as llm_module

    monkeypatch.setattr(llm_module, "model_manager", model_manager)

    return SimpleNamespace(
        agent=agent,
        user=user,
        model_manager=model_manager,
        prepared_context=prepared_context,
    )


@pytest.mark.asyncio
async def test_chat_retries_context_length_from_initial_prepare(chat_harness):
    chat_endpoint.prepare_model_context.side_effect = ContextLengthError("too long")
    chat_harness.model_manager.team_chat.result = LLMChatResponse(
        id="r1",
        model="fake/chat",
        content="ok",
        finish_reason=FinishReason.STOP,
        usage=Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
    )

    result = await chat_endpoint.chat(
        uuid4(), ChatRequest(message="hello"), (chat_harness.user, None)
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert len(chat_endpoint.retry_prepare_model_context.calls) == 1
    assert result["data"].usage == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


@pytest.mark.asyncio
async def test_chat_retries_context_length_from_provider_once(chat_harness):
    chat_harness.model_manager.team_chat.side_effect = [
        ContextLengthError("provider too long"),
        LLMChatResponse(
            id="r2",
            model="fake/chat",
            content="after retry",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        ),
    ]

    result = await chat_endpoint.chat(
        uuid4(), ChatRequest(message="hello"), (chat_harness.user, None)
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert len(chat_harness.model_manager.team_chat.calls) == 2
    assert len(chat_endpoint.retry_prepare_model_context.calls) == 1


@pytest.mark.asyncio
async def test_chat_tool_iteration_cap_uses_terminal_content_and_invalid_args(
    chat_harness,
):
    chat_harness.agent.max_iterations = 1
    chat_harness.model_manager.team_chat.result = LLMChatResponse(
        id="r3",
        model="fake/chat",
        content="tool please",
        tool_calls=[
            ToolCall(
                id="tc1",
                function=FunctionCall(name="broken_args", arguments="not json"),
            )
        ],
        finish_reason=FinishReason.TOOL_CALLS,
        usage=Usage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
    )

    result = await chat_endpoint.chat(
        uuid4(), ChatRequest(message="hello"), (chat_harness.user, None)
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert chat_endpoint.execute_tool_call.calls[0][0][1] == {}
    final_message = _FakeMessage.created[-1]
    assert final_message.round_status == MessageRoundStatus.MAX_ITERATIONS_REACHED
    assert final_message.reasoning_content is None
    assert final_message.tool_calls is None
    assert final_message.round_role == MessageRoundRole.ASSISTANT_FINAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (InsufficientQuotaError("tokens"), ResponseCode.MODEL_QUOTA_EXCEEDED),
        (LLMError("boom"), ResponseCode.UNKNOWN_ERROR),
    ],
)
async def test_chat_maps_provider_errors(chat_harness, error, expected_code):
    chat_harness.model_manager.team_chat.side_effect = error

    with pytest.raises(BusinessError) as exc_info:
        await chat_endpoint.chat(
            uuid4(), ChatRequest(message="hello"), (chat_harness.user, None)
        )

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_chat_inactive_user_exits_before_api_key_access(chat_harness):
    chat_harness.user.is_active = False

    with pytest.raises(BusinessError) as exc_info:
        await chat_endpoint.chat(
            UUID("00000000-0000-0000-0000-000000000001"),
            ChatRequest(message="hello"),
            (chat_harness.user, SimpleNamespace()),
        )

    assert exc_info.value.code == ResponseCode.INACTIVE_USER
    assert chat_endpoint.deps.check_api_key_agent_access.calls == []
