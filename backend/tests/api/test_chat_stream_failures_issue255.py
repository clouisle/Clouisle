import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import (
    AuthenticationError,
    LLMError,
    ModelNotFoundError,
    RateLimitError,
)
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.schemas.agent import ChatRequest
from app.schemas.response import ResponseCode


def _user():
    return SimpleNamespace(id=uuid4(), is_active=True, locale="en")


def _agent():
    team_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        team=SimpleNamespace(id=team_id),
        rag_mode=RAGMode.OFF,
        max_iterations=1,
        enable_vision=False,
    )


def _message(role, content=""):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        content=content,
        file_urls=None,
        reasoning_content=None,
        tool_calls=None,
        save=AsyncMock(),
        delete=AsyncMock(),
    )


async def _start_stream(monkeypatch):
    current_agent = _agent()
    conversation = SimpleNamespace(id=uuid4(), title=None)
    user_message = _message(MessageRole.USER, "hello")
    assistant_message = _message(MessageRole.ASSISTANT)
    created = iter([user_message, assistant_message])

    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(
        chat, "check_agent_chat_access", AsyncMock(return_value=current_agent)
    )
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    monkeypatch.setattr(
        chat.Message, "create", AsyncMock(side_effect=lambda **_kwargs: next(created))
    )
    monkeypatch.setattr(
        chat, "get_next_user_branch_parent_id", AsyncMock(return_value=None)
    )
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
        chat, "build_file_content_for_context", AsyncMock(return_value=(None, None))
    )
    monkeypatch.setattr(chat, "get_agent_chat_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        chat, "get_visible_conversation_messages", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(chat, "collect_conversation_images", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(
        chat, "append_conversation_image_inventory", lambda text, _inventory: text
    )
    monkeypatch.setattr(chat, "get_agent_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "get_tool_display_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        chat, "send_heartbeat_if_needed", AsyncMock(return_value=(True, 0))
    )

    response = await chat.chat_stream(
        current_agent.id,
        ChatRequest(message="hello"),
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        (_user(), None),
    )
    return response, assistant_message


def _error_event(events):
    event = next(item for item in events if "event: error" in item)
    return json.loads(event.split("data: ", 1)[1])


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_code", "expected_message"),
    [
        (ModelNotFoundError(), ResponseCode.MODEL_NOT_FOUND, "model_not_found"),
        (AuthenticationError(), ResponseCode.UNAUTHORIZED, "unauthorized"),
        (RateLimitError(), ResponseCode.UNKNOWN_ERROR, "rate_limit_exceeded"),
        (LLMError("provider failed"), ResponseCode.UNKNOWN_ERROR, "formatted failure"),
        (
            chat.StreamIdleTimeoutError(),
            ResponseCode.UNKNOWN_ERROR,
            "stream_timeout_exceeded",
        ),
    ],
)
async def test_stream_maps_provider_and_idle_failures(
    monkeypatch, error, expected_code, expected_message
):
    response, assistant_message = await _start_stream(monkeypatch)
    persist = AsyncMock(return_value=True)
    monkeypatch.setattr(chat, "persist_partial_round_error", persist)
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(side_effect=error))
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)
    monkeypatch.setattr(
        chat, "_format_llm_error_message", lambda _error: "formatted failure"
    )

    events = [event async for event in response.body_iterator]
    payload = _error_event(events)

    assert payload["code"] == expected_code
    assert payload["msg"] == expected_message
    if isinstance(error, chat.StreamIdleTimeoutError):
        assert payload["timeout"] == 3
    persist.assert_awaited_once()
    assert persist.await_args.args[0] is assistant_message


@pytest.mark.anyio
async def test_empty_stream_falls_back_to_non_stream_provider_call(monkeypatch):
    response, _assistant_message = await _start_stream(monkeypatch)
    prepared = SimpleNamespace(
        messages=[SimpleNamespace(model_dump=lambda **_kwargs: {"content": "hello"})],
        compression=None,
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )

    async def empty_stream(_stream, **_kwargs):
        if False:
            yield None

    monkeypatch.setattr(chat, "iter_with_idle_timeout", empty_stream)
    fallback = AsyncMock(side_effect=RateLimitError())
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )
    monkeypatch.setattr("app.llm.model_manager.team_chat", fallback)
    monkeypatch.setattr(
        chat, "persist_partial_round_error", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(chat, "t", lambda key, **_kwargs: key)

    events = [event async for event in response.body_iterator]

    assert _error_event(events)["msg"] == "rate_limit_exceeded"
    fallback.assert_awaited_once()


@pytest.mark.anyio
async def test_cancelled_empty_stream_deletes_placeholder(monkeypatch):
    response, assistant_message = await _start_stream(monkeypatch)
    prepared = SimpleNamespace(
        messages=[SimpleNamespace(model_dump=lambda **_kwargs: {"content": "hello"})],
        compression=None,
    )
    monkeypatch.setattr(chat, "prepare_model_context", AsyncMock(return_value=prepared))
    monkeypatch.setattr(
        chat, "build_compression_events", lambda **_kwargs: (None, None)
    )

    async def cancelled_stream(_stream, **_kwargs):
        raise asyncio.CancelledError
        yield

    monkeypatch.setattr(chat, "iter_with_idle_timeout", cancelled_stream)
    monkeypatch.setattr(
        "app.llm.model_manager.team_chat_stream", lambda **_kwargs: object()
    )

    events = [event async for event in response.body_iterator]

    assert len(events) == 1
    assert "event: message_start" in events[0]
    assistant_message.delete.assert_awaited_once()
    assistant_message.save.assert_not_awaited()
    assert assistant_message.round_status == MessageRoundStatus.MANUALLY_STOPPED
