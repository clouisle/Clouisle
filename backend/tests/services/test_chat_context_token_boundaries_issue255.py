from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def test_token_budget_and_pressure_boundaries():
    default_budget = chat_context._build_token_budget(
        context_limit=None,
        model_max_output_tokens=None,
    )
    assert default_budget.context_limit == chat_context.DEFAULT_CONTEXT_LIMIT
    assert default_budget.output_reserve == chat_context.DEFAULT_OUTPUT_TOKEN_RESERVE

    constrained_budget = chat_context._build_token_budget(
        context_limit=9,
        model_max_output_tokens=100,
        output_token_reserve=100,
        safety_margin_tokens=20,
    )
    assert constrained_budget.output_reserve == 3
    assert constrained_budget.input_budget == 1

    budget = chat_context.TokenBudget(100, 0, 0, 100)
    thresholds = chat_context._build_compression_thresholds(
        token_budget=budget,
        warning_ratio=-1,
        trigger_ratio=0.8,
        blocking_ratio=2,
    )
    assert thresholds == chat_context.CompressionThresholds(1, 80, 100)
    assert (
        chat_context._assess_context_pressure(
            before_tokens=0, token_budget=budget, thresholds=thresholds
        )
        == "normal"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=1, token_budget=budget, thresholds=thresholds
        )
        == "warning"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=80, token_budget=budget, thresholds=thresholds
        )
        == "auto_compact"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=100, token_budget=budget, thresholds=thresholds
        )
        == "blocking"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=101, token_budget=budget, thresholds=thresholds
        )
        == "over_budget"
    )


def _agent(config):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=config,
    )


@pytest.mark.anyio
async def test_prepare_context_disabled_preserves_provider_model_and_pressure(
    monkeypatch,
):
    messages = [Message(role=MessageRole.USER, content="request")]

    async def build_messages(**_kwargs):
        return messages, {0}

    token_calls = []

    def estimate(_messages, model_id, provider):
        token_calls.append((model_id, provider))
        return 75

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)

    prepared = await chat_context.prepare_model_context(
        agent=_agent(
            {
                "enabled": False,
                "output_token_reserve": 0,
                "safety_margin_tokens": 0,
                "warning_ratio": 0.7,
            }
        ),
        conversation=SimpleNamespace(id=uuid4(), variables={}),
        user_message="request",
        model_id="model-uuid",
        tokenizer_model_id="claude-opus-4-8",
        model_context_limit=100,
        model_max_output_tokens=10,
        provider="anthropic",
    )

    assert token_calls == [("claude-opus-4-8", "anthropic")]
    assert prepared.messages is messages
    assert prepared.protected_indexes == {0}
    assert prepared.compression.pressure_level == "warning"
    assert prepared.compression.utilization_before == 0.75


@pytest.mark.anyio
@pytest.mark.parametrize("emergency_tokens,raises", [(50, False), (101, True)])
async def test_prepare_context_emergency_fallback_boundary(
    monkeypatch, emergency_tokens, raises
):
    source_messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="current"),
    ]

    async def build_messages(**_kwargs):
        return source_messages, {2}

    async def no_session_memory(messages, protected_indexes, **_kwargs):
        return list(messages), False, set(protected_indexes)

    estimates = iter([101] * 5 + [emergency_tokens])
    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", no_session_memory
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda *_args, **_kwargs: next(estimates, emergency_tokens),
    )

    call = chat_context.prepare_model_context(
        agent=_agent(
            {
                "micro_compaction_enabled": False,
                "macro_compaction_enabled": False,
                "checkpoint_summary_enabled": False,
                "output_token_reserve": 0,
                "safety_margin_tokens": 0,
            }
        ),
        conversation=SimpleNamespace(id=uuid4(), variables={}),
        user_message="current",
        model_id="boundary-model",
        model_context_limit=100,
        model_max_output_tokens=0,
        provider="boundary-provider",
        protected_round_id=uuid4(),
    )

    if raises:
        with pytest.raises(ContextLengthError) as exc_info:
            await call
        assert exc_info.value.max_tokens == 100
        assert exc_info.value.actual_tokens == 101
        assert exc_info.value.provider == "boundary-provider"
        assert exc_info.value.model == "boundary-model"
    else:
        prepared = await call
        assert [message.content for message in prepared.messages] == [
            "system",
            "current",
        ]
        assert prepared.protected_indexes == {1}
        assert prepared.compression.actions == ["emergency_fallback"]
        assert prepared.compression.after_tokens == 50
