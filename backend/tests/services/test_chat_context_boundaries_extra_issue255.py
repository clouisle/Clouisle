from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def _agent(**compression_config):
    return SimpleNamespace(
        id="agent-1",
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=compression_config,
    )


def _conversation():
    return SimpleNamespace(id="conversation-1", variables={})


def test_token_budget_clamps_reserves_and_input_floor():
    limited_output = chat_context._build_token_budget(
        context_limit=90,
        model_max_output_tokens=20,
        output_token_reserve=80,
        safety_margin_tokens=10,
    )
    tiny_context = chat_context._build_token_budget(
        context_limit=2,
        model_max_output_tokens=None,
        safety_margin_tokens=10,
    )

    assert limited_output.output_reserve == 20
    assert limited_output.input_budget == 60
    assert tiny_context.output_reserve == 1
    assert tiny_context.input_budget == 1


@pytest.mark.anyio
async def test_file_content_builder_skips_empty_inputs_and_unchanged_cache(monkeypatch):
    builder = AsyncMock(return_value=("parsed", [{"url": "same"}]))
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context", builder
    )
    source_message = SimpleNamespace(file_urls=[{"url": "same"}], save=AsyncMock())

    empty = await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=None,
        legacy_files=None,
        user_locale="en",
        tool_timeouts=None,
        user=None,
    )
    parsed = await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=source_message.file_urls,
        user_locale="en",
        tool_timeouts=None,
        user=None,
        source_message=source_message,
    )

    assert empty == ""
    assert parsed == "parsed"
    builder.assert_awaited_once()
    source_message.save.assert_not_awaited()


@pytest.mark.anyio
async def test_prepare_context_returns_uncompressed_history_when_guard_disabled(
    monkeypatch,
):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="history"),
    ]
    build_messages = AsyncMock(return_value=(messages, {1}))
    session_compaction = AsyncMock()
    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", session_compaction
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 75
    )

    prepared = await chat_context.prepare_model_context(
        agent=_agent(
            enabled=True,
            preflight_guard_enabled=False,
            output_token_reserve=10,
            safety_margin_tokens=10,
        ),
        conversation=_conversation(),
        user_message="history",
        model_id="model",
        model_context_limit=100,
        model_max_output_tokens=10,
    )

    assert prepared.messages == messages
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "none"
    assert prepared.compression.pressure_level == "blocking"
    session_compaction.assert_not_awaited()


def test_budget_compaction_keeps_messages_when_macro_has_nothing_to_summarize(
    monkeypatch,
):
    messages = [Message(role=MessageRole.USER, content="current")]
    compression = chat_context.CompressionMeta(
        stage="micro", before_tokens=20, after_tokens=20, input_budget=10
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_macro_compaction",
        lambda *args, **kwargs: (messages, 0, 1, 0, 0, {0}),
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 20
    )

    compacted, result, protected = chat_context._apply_budget_compaction(
        messages=messages,
        model_id="model",
        provider=None,
        token_budget=chat_context.TokenBudget(20, 5, 5, 10),
        compression=compression,
        file_content_trimmed=False,
        protected_indexes={0},
    )

    assert compacted == messages
    assert compacted is not messages
    assert result is compression
    assert protected == {0}


@pytest.mark.anyio
@pytest.mark.parametrize("emergency_tokens", [5, 20])
async def test_prepare_context_emergency_budget_edges(monkeypatch, emergency_tokens):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="current"),
    ]
    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        AsyncMock(return_value=(messages, {2})),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        AsyncMock(return_value=(messages, False, {2})),
    )
    token_counts = iter([20] * 5 + [emergency_tokens])
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda *args, **kwargs: next(token_counts, emergency_tokens),
    )

    call = chat_context.prepare_model_context(
        agent=_agent(
            micro_compaction_enabled=False,
            macro_compaction_enabled=False,
            checkpoint_summary_enabled=False,
            output_token_reserve=5,
            safety_margin_tokens=5,
        ),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=20,
        model_max_output_tokens=5,
    )
    if emergency_tokens > 10:
        with pytest.raises(ContextLengthError):
            await call
        return

    prepared = await call
    assert [message.content for message in prepared.messages] == ["system", "current"]
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "macro"
    assert "emergency_fallback" in prepared.compression.actions
