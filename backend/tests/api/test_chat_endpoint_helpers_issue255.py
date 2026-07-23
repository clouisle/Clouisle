from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.llm.errors import LLMError
from app.llm.types.chat import (
    ChatStreamChunk,
    ChatStreamDelta,
    FinishReason,
    FunctionCall,
    ToolCall,
)
from app.models.agent import MessageRoundStatus


def _chunk(**kwargs):
    return ChatStreamChunk(
        id="chunk-1",
        model="test-model",
        delta=ChatStreamDelta(**kwargs.pop("delta", {})),
        **kwargs,
    )


def test_stream_activity_detects_keepalive_and_model_output_boundaries():
    assert not chat._is_model_stream_activity(_chunk())
    assert chat._is_model_stream_activity(_chunk(delta={"stream_activity": True}))
    assert chat._is_model_stream_activity(_chunk(delta={"content": "hello"}))
    assert chat._is_model_stream_activity(
        _chunk(delta={"reasoning_content": "thinking"})
    )
    assert chat._is_model_stream_activity(
        _chunk(
            delta={
                "tool_calls": [
                    ToolCall(
                        id="tool-1",
                        function=FunctionCall(name="lookup", arguments="{}"),
                    )
                ]
            }
        )
    )
    assert chat._is_model_stream_activity(_chunk(finish_reason=FinishReason.STOP))


def test_format_llm_error_prefers_provider_payload_message(monkeypatch):
    monkeypatch.setattr(
        chat,
        "t",
        lambda key, **kwargs: f"{key}:{kwargs.get('message', '')}",
    )
    error = LLMError("provider failed - {'error': {'message': 'Input too large'}}")

    assert (
        chat._format_llm_error_message(error)
        == "model_service_request_failed:Input too large"
    )


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"completed": True}, MessageRoundStatus.COMPLETED),
        ({"completed": False}, MessageRoundStatus.ERROR),
        (
            {"completed": True, "manually_stopped": True},
            MessageRoundStatus.MANUALLY_STOPPED,
        ),
        (
            {"completed": True, "max_iterations_reached": True},
            MessageRoundStatus.MAX_ITERATIONS_REACHED,
        ),
        ({"completed": True, "errored": True}, MessageRoundStatus.ERROR),
    ],
)
def test_round_terminal_status_prioritizes_error_boundaries(flags, expected):
    assert chat.get_round_terminal_status(**flags) == expected


class SavedMessage:
    def __init__(self):
        self.id = uuid4()
        self.conversation_id = uuid4()
        self.save_calls = 0

    async def save(self):
        self.save_calls += 1


@pytest.mark.asyncio
async def test_persist_partial_round_error_skips_empty_unstarted_message(monkeypatch):
    message = SavedMessage()

    async def no_persisted_trace(_message):
        return False

    monkeypatch.setattr(chat, "round_has_persisted_trace", no_persisted_trace)

    persisted = await chat.persist_partial_round_error(
        message,
        content="",
        reasoning="",
        model_id="test/model",
        start_time=1.0,
    )

    assert persisted is False
    assert message.save_calls == 0


@pytest.mark.asyncio
async def test_persist_partial_round_error_uses_fallback_and_marks_error(monkeypatch):
    message = SavedMessage()

    async def no_persisted_trace(_message):
        return False

    monkeypatch.setattr(chat, "round_has_persisted_trace", no_persisted_trace)
    monkeypatch.setattr(chat.time, "time", lambda: 3.0)

    persisted = await chat.persist_partial_round_error(
        message,
        content="",
        reasoning="",
        model_id="test/model",
        start_time=1.0,
        first_token_time=2.0,
        fallback_content="stream failed",
    )

    assert persisted is True
    assert message.content == "stream failed"
    assert message.reasoning_content is None
    assert message.model_used == "test/model"
    assert message.duration_ms == 2000
    assert message.first_token_ms == 1000
    assert message.is_manually_stopped is False
    assert message.round_status == MessageRoundStatus.ERROR
    assert message.save_calls == 1


@pytest.mark.asyncio
async def test_get_version_count_counts_children_from_root(monkeypatch):
    root_id = uuid4()
    requested_filters = []

    class Query:
        async def count(self):
            return 2

    def fake_filter(**kwargs):
        requested_filters.append(kwargs)
        return Query()

    monkeypatch.setattr(chat.Message, "filter", fake_filter)

    count = await chat.get_version_count(SimpleNamespace(id=root_id, parent_id=None))

    assert count == 3
    assert requested_filters == [{"parent_id": root_id}]


@pytest.mark.asyncio
async def test_get_version_count_counts_siblings_from_child_parent(monkeypatch):
    root_id = uuid4()
    child_id = uuid4()
    requested_filters = []

    class Query:
        async def count(self):
            return 4

    def fake_filter(**kwargs):
        requested_filters.append(kwargs)
        return Query()

    monkeypatch.setattr(chat.Message, "filter", fake_filter)

    count = await chat.get_version_count(
        SimpleNamespace(id=child_id, parent_id=root_id)
    )

    assert count == 5
    assert requested_filters == [{"parent_id": root_id}]
