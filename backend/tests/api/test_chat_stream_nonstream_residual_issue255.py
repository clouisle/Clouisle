from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request
from unittest.mock import AsyncMock

from app.api.v1.endpoints import chat as chat_module
from app.llm.errors import ContextLengthError
from app.llm.types import (
    ChatResponse as LLMChatResponse,
    FinishReason,
    Message as LLMMessage,
    Usage,
)
from app.models.agent import MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest


class _AsyncFilter:
    def prefetch_related(self, *args):
        return self

    async def first(self):
        return None

    async def update(self, **kwargs):
        return 1


class _ModelQuery:
    @staticmethod
    def filter(*args, **kwargs):
        return _AsyncFilter()


class _Stream:
    def __init__(self, chunks=()):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        item = self._chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _SavedMessage(SimpleNamespace):
    async def save(self, *args, **kwargs):
        return None

    async def delete(self):
        return None


class _Request:
    async def is_disconnected(self):
        return False


async def _collect(response):
    events = []
    async for chunk in response.body_iterator:
        events.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(events)


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "team": SimpleNamespace(id=uuid4()),
        "rag_mode": RAGMode.AGENTIC,
        "max_iterations": 5,
        "enable_vision": False,
        "enable_user_input_request": False,
        "streaming_config": {},
        "tools_config": [],
        "enable_image_generation": False,
        "enable_video_generation": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _team_model():
    return SimpleNamespace(
        model=SimpleNamespace(
            provider="test-provider",
            model_id="test-model",
            context_length=1000,
            max_output_tokens=100,
            capabilities={},
        )
    )


def _install_common(monkeypatch, agent, conversation, user):
    monkeypatch.setattr(chat_module.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat_module, "check_agent_chat_access", AsyncMock(return_value=agent)
    )
    monkeypatch.setattr(
        chat_module, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat_module, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(chat_module, "update_message_stats", AsyncMock())
    monkeypatch.setattr(
        chat_module, "get_agent_chat_model", AsyncMock(return_value=_team_model())
    )
    monkeypatch.setattr(
        chat_module,
        "get_streaming_config",
        lambda agent: {
            "global_timeout": 30,
            "heartbeat_interval": 999,
            "idle_timeout": 30,
            "tool_timeouts": {},
        },
    )
    monkeypatch.setattr(chat_module, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        chat_module, "get_tool_display_names", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        chat_module,
        "build_file_content_for_context",
        AsyncMock(return_value=("file context", [{"url": "updated"}])),
    )
    monkeypatch.setattr(
        chat_module, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        chat_module, "collect_conversation_images", lambda *a, **k: ([], [])
    )
    monkeypatch.setattr(
        chat_module,
        "append_conversation_image_inventory",
        lambda message, inventory: message,
    )
    monkeypatch.setattr(
        chat_module, "get_prefix_path_before", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat_module, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(chat_module, "persist_macro_summary_best_effort", AsyncMock())
    monkeypatch.setattr(
        chat_module, "enqueue_session_memory_extraction", lambda *a, **k: None
    )
    monkeypatch.setattr(chat_module, "Conversation", _ModelQuery)
    monkeypatch.setattr(chat_module, "Agent", _ModelQuery)
    monkeypatch.setattr(chat_module, "Team", _ModelQuery)

    from app.services.sandbox.gateway import sandbox_gateway

    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="sandbox-1")
    )
    return user


def _install_message_create(monkeypatch):
    created = []

    async def create(**kwargs):
        values = {**kwargs, "id": uuid4()}
        message = _SavedMessage(**values)
        created.append(message)
        return message

    monkeypatch.setattr(chat_module, "Message", SimpleNamespace(create=create))
    return created


@pytest.mark.anyio
async def test_nonstream_retries_prepare_context_and_cleans_user_input_request(
    monkeypatch,
):
    agent = _agent(enable_user_input_request=True)
    conversation = SimpleNamespace(id=uuid4(), title="")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    _install_common(monkeypatch, agent, conversation, user)
    created = _install_message_create(monkeypatch)

    retry_context = SimpleNamespace(messages=[LLMMessage(role="user", content="hello")])
    monkeypatch.setattr(
        chat_module,
        "prepare_model_context",
        AsyncMock(side_effect=ContextLengthError("too long")),
    )
    monkeypatch.setattr(
        chat_module,
        "retry_prepare_model_context",
        AsyncMock(return_value=retry_context),
    )
    monkeypatch.setattr(chat_module, "should_retry_context_length", lambda agent: True)
    monkeypatch.setattr(
        chat_module,
        "parse_user_input_request",
        lambda content: (None, "clean answer"),
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(
            return_value=LLMChatResponse(
                id="r1",
                model="test-model",
                content="ASK_USER: dirty answer",
                reasoning_content="reason",
                tool_calls=None,
                finish_reason=FinishReason.STOP,
                usage=Usage(prompt_tokens=8, completion_tokens=4, total_tokens=12),
            )
        ),
    )
    monkeypatch.setattr(
        chat_module.MessageOut,
        "model_validate",
        classmethod(lambda cls, value: SimpleNamespace(id=value.id)),
    )
    monkeypatch.setattr(
        chat_module, "ChatResponse", lambda **kwargs: SimpleNamespace(**kwargs)
    )

    result = await chat_module.chat(
        uuid4(), ChatRequest(message="hello"), auth_result=(user, None)
    )

    assert result["data"].usage == {
        "prompt_tokens": 8,
        "completion_tokens": 4,
        "total_tokens": 12,
    }
    assert created[0].file_urls == [{"url": "updated"}]
    assert created[-1].content == "clean answer"
    assert created[-1].reasoning_content == "reason"


@pytest.mark.anyio
async def test_stream_empty_upstream_falls_back_to_nonstream_reasoning_and_content(
    monkeypatch,
):
    agent = _agent()
    conversation = SimpleNamespace(id=uuid4(), title="")
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    _install_common(monkeypatch, agent, conversation, user)
    created = _install_message_create(monkeypatch)

    contexts = [
        SimpleNamespace(
            messages=[LLMMessage(role="user", content="hello")], compression=None
        ),
        SimpleNamespace(
            messages=[LLMMessage(role="assistant", content="fallback")],
            compression=None,
        ),
    ]
    monkeypatch.setattr(
        chat_module, "prepare_model_context", AsyncMock(side_effect=contexts)
    )
    monkeypatch.setattr(
        chat_module, "build_compression_events", lambda **kwargs: (None, None)
    )
    monkeypatch.setattr(
        chat_module, "get_compression_trigger", lambda compression: None
    )
    monkeypatch.setattr(
        chat_module, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        chat_module, "iter_with_idle_timeout", lambda stream, **kwargs: stream
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **kwargs: _Stream()
    )
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat",
        AsyncMock(
            return_value=LLMChatResponse(
                id="fallback",
                model="test-model",
                content="fallback content",
                reasoning_content="fallback reasoning",
                tool_calls=None,
                finish_reason=FinishReason.STOP,
                usage=Usage(),
            )
        ),
    )
    record_usage = AsyncMock()
    monkeypatch.setattr("app.llm.model_manager.record_stream_usage", record_usage)

    response = await chat_module.chat_stream(
        uuid4(), ChatRequest(message="hello"), Request({"type": "http"}), (user, None)
    )
    body = await _collect(response)

    assert "event: reasoning_start" in body
    assert '"delta": "fallback reasoning"' in body
    assert '"delta": "fallback content"' in body
    assert "event: message_end" in body
    assert created[-1].content == "fallback content"
    assert created[-1].reasoning_content == "fallback reasoning"
    assert created[-1].round_status == MessageRoundStatus.COMPLETED
    record_usage.assert_awaited_once()
