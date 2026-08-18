from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def _agent(config=None):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=config or {},
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (69, "normal"),
        (70, "warning"),
        (80, "auto_compact"),
        (92, "blocking"),
        (101, "over_budget"),
    ],
)
def test_pressure_boundaries_are_inclusive(tokens, expected):
    budget = chat_context._build_token_budget(
        context_limit=120,
        model_max_output_tokens=10,
        output_token_reserve=10,
        safety_margin_tokens=10,
    )
    thresholds = chat_context._build_compression_thresholds(
        token_budget=budget,
        warning_ratio=0.7,
        trigger_ratio=0.8,
        blocking_ratio=0.92,
    )

    assert budget.input_budget == 100
    assert (
        chat_context._assess_context_pressure(
            before_tokens=tokens,
            token_budget=budget,
            thresholds=thresholds,
        )
        == expected
    )


@pytest.mark.anyio
async def test_history_override_injects_and_protects_current_round(monkeypatch):
    round_id = uuid4()
    file_builder = AsyncMock(return_value=("legacy text", None))
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        file_builder,
    )

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content="current file",
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "calling tool",
                "round_id": round_id,
                "tool_calls": [
                    {"id": "call-1", "name": "lookup", "arguments": {"q": 1}}
                ],
            },
            {
                "role": "tool",
                "content": "tool result",
                "tool_call_id": "call-1",
                "round_id": round_id,
            },
            {"role": "tool", "content": "orphan", "tool_call_id": "missing"},
            {"role": "user", "content": "old question", "files": [{"name": "old.txt"}]},
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=round_id,
    )

    assert messages[1].role == MessageRole.USER
    assert "current question" in messages[1].content
    assert "current file" in messages[1].content
    assert messages[2].tool_calls[0].function.arguments == '{"q": 1}'
    assert messages[3].tool_call_id == "call-1"
    assert all(message.content != "orphan" for message in messages)
    assert "legacy text" in messages[4].content
    assert protected == {1, 2, 3}
    assert file_builder.await_args.kwargs["legacy_files"] == [{"name": "old.txt"}]


@pytest.mark.anyio
async def test_file_cache_is_not_saved_when_metadata_is_unchanged(monkeypatch):
    file_urls = [{"url": "/files/a.txt"}]
    source_message = SimpleNamespace(file_urls=file_urls, save=AsyncMock())
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("parsed", file_urls.copy())),
    )

    content = await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=file_urls,
        user_locale="en",
        tool_timeouts=None,
        user=None,
        source_message=source_message,
    )

    assert content == "parsed"
    source_message.save.assert_not_awaited()


@pytest.mark.anyio
async def test_session_memory_storage_error_keeps_original_context(monkeypatch, caplog):
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    messages = [Message(role=MessageRole.USER, content="keep me")]

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="mock-model",
        provider="mock-provider",
        protected_indexes={0},
    )

    assert not changed
    assert compacted[0] is not messages[0]
    assert compacted[0].content == "keep me"
    assert protected == {0}
    assert "storage unavailable" in caplog.text


def test_blocking_pressure_builds_macro_summary(monkeypatch):
    messages = [Message(role=MessageRole.SYSTEM, content="system")]
    for index in range(4):
        messages.extend(
            [
                Message(role=MessageRole.USER, content=f"question {index}"),
                Message(role=MessageRole.ASSISTANT, content=f"answer {index}"),
            ]
        )
    budget = chat_context.TokenBudget(120, 10, 10, 100)
    compression = chat_context.CompressionMeta(
        stage="micro",
        before_tokens=95,
        after_tokens=95,
        input_budget=100,
        actions=["trim_reasoning"],
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider=None: len(messages) * 5,
    )

    compacted, meta, _ = chat_context._apply_budget_compaction(
        messages=messages,
        model_id="mock-model",
        provider="mock-provider",
        token_budget=budget,
        compression=compression,
        file_content_trimmed=False,
        pressure_level="blocking",
        recent_raw_turns=1,
        recent_tool_turns=0,
    )

    assert meta.stage == "macro"
    assert meta.summary_turns == 3
    assert meta.actions == ["trim_reasoning", "macro_summary"]
    assert any(
        message.role == MessageRole.ASSISTANT
        and str(message.content).startswith(chat_context.MACRO_SUMMARY_PREFIX)
        for message in compacted
    )
    assert compacted[-2].content == "question 3"


@pytest.mark.anyio
async def test_disabled_preflight_reports_over_budget_without_compacting(monkeypatch):
    agent = _agent(
        {
            "enabled": False,
            "output_token_reserve": 10,
            "safety_margin_tokens": 10,
        }
    )
    built = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="question"),
    ]
    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        AsyncMock(return_value=(built, {1})),
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 101
    )

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=_conversation(),
        user_message="question",
        model_id="mock-model",
        model_context_limit=120,
        model_max_output_tokens=10,
        provider="mock-provider",
    )

    assert prepared.messages == built
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "none"
    assert prepared.compression.pressure_level == "over_budget"
    assert prepared.compression.after_tokens == 101


@pytest.mark.anyio
async def test_emergency_fallback_keeps_system_and_current_user(monkeypatch):
    built = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="current"),
        Message(role=MessageRole.ASSISTANT, content="current partial"),
    ]
    agent = _agent(
        {
            "micro_compaction_enabled": False,
            "macro_compaction_enabled": False,
            "checkpoint_summary_enabled": False,
            "output_token_reserve": 10,
            "safety_margin_tokens": 10,
        }
    )
    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        AsyncMock(return_value=(built, {2, 3})),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        AsyncMock(
            side_effect=lambda messages, **kwargs: (
                list(messages),
                False,
                kwargs["protected_indexes"],
            )
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider=None: 150 if len(messages) > 3 else 30,
    )

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=_conversation(),
        user_message="current",
        model_id="mock-model",
        model_context_limit=120,
        model_max_output_tokens=10,
        provider="mock-provider",
    )

    assert [message.content for message in prepared.messages] == [
        "system",
        "current",
    ]
    assert prepared.protected_indexes == {1}
    assert prepared.compression.actions == ["emergency_fallback"]
    assert prepared.compression.pressure_level == "over_budget"


@pytest.mark.anyio
async def test_emergency_fallback_raises_when_current_round_cannot_fit(monkeypatch):
    built = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="oversized current question"),
    ]
    agent = _agent(
        {
            "micro_compaction_enabled": False,
            "macro_compaction_enabled": False,
            "checkpoint_summary_enabled": False,
            "output_token_reserve": 10,
            "safety_margin_tokens": 10,
        }
    )
    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        AsyncMock(return_value=(built, {1})),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        AsyncMock(
            side_effect=lambda messages, **kwargs: (
                list(messages),
                False,
                kwargs["protected_indexes"],
            )
        ),
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 150
    )

    with pytest.raises(ContextLengthError) as exc_info:
        await chat_context.prepare_model_context(
            agent=agent,
            conversation=_conversation(),
            user_message="oversized current question",
            model_id="mock-model",
            model_context_limit=120,
            model_max_output_tokens=10,
            provider="mock-provider",
        )

    assert exc_info.value.max_tokens == 100
    assert exc_info.value.actual_tokens == 150
    assert exc_info.value.details["retryable"] is False
    assert exc_info.value.details["reason"] == "system_and_user_exceed_input_budget"


@pytest.mark.anyio
async def test_retry_preparation_forwards_aggressive_mode(monkeypatch):
    expected = SimpleNamespace(messages=[])
    prepare = AsyncMock(return_value=expected)
    monkeypatch.setattr(chat_context, "prepare_model_context", prepare)

    result = await chat_context.retry_prepare_model_context(
        agent=_agent(),
        conversation=_conversation(),
        user_message="retry",
        model_id="mock-model",
        model_context_limit=100,
        model_max_output_tokens=10,
        provider="mock-provider",
        protected_round_id="round-1",
    )

    assert result is expected
    assert prepare.await_args.kwargs["aggressive"] is True
    assert prepare.await_args.kwargs["protected_round_id"] == "round-1"
