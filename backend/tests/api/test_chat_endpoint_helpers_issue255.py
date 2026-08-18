from types import SimpleNamespace
from unittest.mock import Mock
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


def test_calculate_model_usage_prefers_provider_totals(monkeypatch):
    monkeypatch.setattr(
        chat,
        "count_message_tokens",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    monkeypatch.setattr(
        chat,
        "count_tokens",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()),
    )

    assert chat._calculate_model_usage(
        messages=[{"role": "user", "content": "question"}],
        content="answer",
        reasoning_content=None,
        tool_calls=None,
        tools=None,
        usage=SimpleNamespace(prompt_tokens=13, completion_tokens=5),
        model_id="unit-model",
        provider="stub",
    ) == (13, 5)


def test_calculate_model_usage_counts_messages_and_output_without_provider_totals(
    monkeypatch,
):
    monkeypatch.setattr(chat, "count_message_tokens", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(chat, "count_tokens", lambda text, *_args: len(text))

    assert chat._calculate_model_usage(
        messages=[{"role": "user", "content": "question"}],
        content="answer",
        reasoning_content="think",
        tool_calls=None,
        tools=None,
        usage=None,
        model_id="unit-model",
        provider="stub",
    ) == (11, 11)


def test_calculate_model_usage_counts_tool_request_payloads(monkeypatch):
    message_tokens = Mock(return_value=11)
    tool_definition_tokens = Mock(return_value=7)
    monkeypatch.setattr(chat, "count_message_tokens", message_tokens)
    monkeypatch.setattr(chat, "count_tool_definition_tokens", tool_definition_tokens)
    monkeypatch.setattr(chat, "count_tokens", lambda text, *_args: len(text))
    tools = [{"type": "function", "function": {"name": "lookup"}}]

    assert chat._calculate_model_usage(
        messages=[{"role": "user", "content": "question"}],
        content="answer",
        reasoning_content=None,
        tool_calls=None,
        tools=tools,
        usage=None,
        model_id="unit-model",
        provider="stub",
    ) == (18, 6)
    message_tokens.assert_called_once_with(
        [{"role": "user", "content": "question"}],
        "unit-model",
        "stub",
        include_tool_calls=True,
    )
    tool_definition_tokens.assert_called_once_with(tools, "unit-model", "stub")


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
        model_used="test/model",
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
        model_used="test/model",
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

        def filter(self, *args, **kwargs):
            requested_filters.append((args, kwargs))
            return self

    def fake_filter(*args, **kwargs):
        requested_filters.append((args, kwargs))
        return Query()

    monkeypatch.setattr(chat.Message, "filter", fake_filter)

    count = await chat.get_version_count(SimpleNamespace(id=root_id, parent_id=None))

    assert count == 3
    # Version count must exclude round steps (tool calls/results) that carry
    # parent_id=root, so the query chains a canonical filter.
    assert len(requested_filters) == 2
    assert requested_filters[0] == ((), {"parent_id": root_id})
    canonical_q = requested_filters[1][0][0]
    leaf_filters: dict = {}
    for child in canonical_q.children:
        leaf_filters.update(child.filters)
    assert leaf_filters == {
        "round_id__isnull": True,
        "is_round_canonical": True,
    }


@pytest.mark.asyncio
async def test_get_version_count_counts_siblings_from_child_parent(monkeypatch):
    root_id = uuid4()
    child_id = uuid4()
    requested_filters = []

    class Query:
        async def count(self):
            return 4

        def filter(self, *args, **kwargs):
            requested_filters.append((args, kwargs))
            return self

    def fake_filter(*args, **kwargs):
        requested_filters.append((args, kwargs))
        return Query()

    monkeypatch.setattr(chat.Message, "filter", fake_filter)

    count = await chat.get_version_count(
        SimpleNamespace(id=child_id, parent_id=root_id)
    )

    assert count == 5
    assert len(requested_filters) == 2
    assert requested_filters[0] == ((), {"parent_id": root_id})
    canonical_q = requested_filters[1][0][0]
    leaf_filters: dict = {}
    for child in canonical_q.children:
        leaf_filters.update(child.filters)
    assert leaf_filters == {
        "round_id__isnull": True,
        "is_round_canonical": True,
    }
