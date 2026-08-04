from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1.endpoints.chat_sse import build_compression_events
from app.llm.types import Message, MessageRole
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context


@pytest.mark.anyio
async def test_prepare_model_context_reuses_session_memory_before_pressure_check(
    monkeypatch,
):
    conversation_id = uuid4()
    current_user_message_id = uuid4()
    snapshot_source_id = uuid4()

    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "recent_raw_turns": 1,
            "recent_tool_turns": 0,
            "output_token_reserve": 50,
            "safety_margin_tokens": 50,
        },
    )
    conversation = SimpleNamespace(id=conversation_id, variables={})

    history = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.USER,
            content="OLD_RAW_HISTORY " * 100,
            file_urls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="old answer",
            reasoning_content=None,
            tool_calls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.USER,
            content="recent turn",
            file_urls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=snapshot_source_id,
            role=ConversationMessageRole.ASSISTANT,
            content="recent answer",
            reasoning_content=None,
            tool_calls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=current_user_message_id,
            role=ConversationMessageRole.USER,
            content="continue",
            file_urls=None,
            round_id=None,
        ),
    ]

    async def fake_get_visible_conversation_messages(*args, **kwargs):
        return history

    async def fake_get_ready_session_memory(conversation_id):
        return SimpleNamespace(
            summary_text="COMPRESSED_SUMMARY",
            source_message_id=snapshot_source_id,
        )

    async def fake_is_message_on_active_branch(*args, **kwargs):
        return True

    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        fake_get_visible_conversation_messages,
    )
    monkeypatch.setattr(
        chat_context,
        "is_message_on_active_branch",
        fake_is_message_on_active_branch,
    )
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        fake_get_ready_session_memory,
    )
    monkeypatch.setattr(
        chat_context,
        "count_message_tokens",
        lambda payload, model_id, provider=None: sum(
            len(str(item.get("content", ""))) for item in payload
        ),
    )

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="continue",
        model_id="gpt-4",
        model_context_limit=2000,
        model_max_output_tokens=50,
        provider=None,
        current_user_message_id=current_user_message_id,
        include_current_user_message=True,
    )

    contents = [message.content for message in prepared.messages]

    assert "COMPRESSED_SUMMARY" in contents
    assert not any("OLD_RAW_HISTORY" in str(content) for content in contents)
    assert "continue" in contents
    assert prepared.compression.before_tokens < 2000
    assert prepared.compression.pressure_level == "normal"
    assert all(
        message.role in {MessageRole.SYSTEM, MessageRole.ASSISTANT, MessageRole.USER}
        for message in prepared.messages
    )


@pytest.mark.anyio
async def test_session_memory_compaction_is_not_reapplied_in_micro_after_file_trim(
    monkeypatch,
):
    """Rebuilt file context gets one fresh snapshot pass; micro skips a third."""

    call_order = {"index": 0}
    file_rebuild_calls = {"count": 0}
    session_memory_calls: list[int] = []

    async def fake_rebuild(*args, **kwargs):
        file_rebuild_calls["count"] += 1
        rebuilt = [
            Message(role=MessageRole.SYSTEM, content="SYSTEM"),
            Message(
                role=MessageRole.USER,
                content="OLD_RAW_HISTORY " * 30,
            ),
            Message(role=MessageRole.USER, content="continue"),
        ]
        return rebuilt, {len(rebuilt) - 1}

    def _apply_session_memory(messages, **kwargs):
        # First call = preflight. Second call = rebuilt file context.
        # Micro compaction must not query or apply the same snapshot a third time.
        call_order["index"] += 1
        phase = 1 + call_order["index"]
        session_memory_calls.append(phase)
        # Include enough content that the post-rebuild token estimate still
        # exceeds the trigger budget, forcing file_content_trimmed=True and
        # therefore a second rebuild that re-invokes session memory.
        filler = "OLD_RAW_HISTORY " * 200
        rebuilt = [
            messages[0],
            Message(
                role=MessageRole.ASSISTANT,
                content=f"COMPRESSED_SUMMARY phase={phase} {filler}",
            ),
            messages[-1],
        ]
        return rebuilt, True, {len(rebuilt) - 1}

    async def _async_apply_session_memory(messages, **kwargs):
        return _apply_session_memory(messages, **kwargs)

    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "recent_raw_turns": 1,
            "recent_tool_turns": 0,
            "output_token_reserve": 50,
            "safety_margin_tokens": 50,
        },
    )
    conversation = SimpleNamespace(id=uuid4(), variables={})

    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        fake_rebuild,
    )
    monkeypatch.setattr(
        "app.services.chat_context._apply_session_memory_compaction",
        _async_apply_session_memory,
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider=None: sum(
            len(str(getattr(message, "content", "") or "")) for message in messages
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "count_message_tokens",
        lambda payload, model_id, provider=None: sum(
            len(str(item.get("content", ""))) for item in payload
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "_trim_file_content",
        lambda content, aggressive: (content, True),
    )

    await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="continue",
        model_id="gpt-4",
        model_context_limit=4000,
        model_max_output_tokens=50,
        provider=None,
        file_content="FILE_CONTENT " * 600,
        current_user_message_id=uuid4(),
        include_current_user_message=True,
    )

    assert file_rebuild_calls["count"] >= 1
    assert session_memory_calls == [2, 3]


@pytest.mark.anyio
async def test_session_memory_compaction_is_idempotent_when_summary_is_protected(
    monkeypatch,
):
    source_message_id = uuid4()
    conversation = SimpleNamespace(id=uuid4())
    snapshot = SimpleNamespace(
        summary_text="MODEL_SUMMARY",
        source_message_id=source_message_id,
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old request " * 100),
        Message(role=MessageRole.ASSISTANT, content="old answer " * 100),
        Message(role=MessageRole.USER, content="recent request"),
        Message(role=MessageRole.ASSISTANT, content="recent answer"),
        Message(role=MessageRole.USER, content="current request"),
    ]

    async def get_snapshot(_conversation_id):
        return snapshot

    async def is_active(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", get_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", is_active)
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )

    (
        first,
        first_changed,
        first_protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=2,
    )
    second, second_changed, _ = await chat_context._apply_session_memory_compaction(
        first,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=2,
        protected_indexes=first_protected,
    )

    assert first_changed is True
    assert second_changed is False
    assert 1 in first_protected
    assert [message.content for message in second] == [
        message.content for message in first
    ]


@pytest.mark.anyio
async def test_session_memory_compaction_reverts_when_summary_does_not_save_tokens(
    monkeypatch,
):
    source_message_id = uuid4()
    conversation = SimpleNamespace(id=uuid4())
    snapshot = SimpleNamespace(
        summary_text="oversized summary " * 1000,
        source_message_id=source_message_id,
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="short request"),
        Message(role=MessageRole.ASSISTANT, content="short answer"),
        Message(role=MessageRole.USER, content="current request"),
    ]

    async def get_snapshot(_conversation_id):
        return snapshot

    async def is_active(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", get_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", is_active)
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
    )

    assert changed is False
    assert [message.content for message in compacted] == [
        message.content for message in messages
    ]
    assert not protected


@pytest.mark.anyio
async def test_prepare_model_context_omits_events_for_no_benefit_snapshot(
    monkeypatch,
):
    source_message_id = uuid4()
    conversation = SimpleNamespace(id=uuid4(), variables={})
    agent = SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "recent_raw_turns": 1,
            "recent_tool_turns": 0,
            "output_token_reserve": 50,
            "safety_margin_tokens": 50,
        },
    )
    snapshot = SimpleNamespace(
        summary_text="oversized summary " * 1000,
        source_message_id=source_message_id,
    )
    history = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.USER,
            content="old history " * 200,
            file_urls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=source_message_id,
            role=ConversationMessageRole.ASSISTANT,
            content="old answer",
            reasoning_content=None,
            tool_calls=None,
            round_id=None,
        ),
    ]

    async def get_history(*args, **kwargs):
        return history

    async def get_snapshot(_conversation_id):
        return snapshot

    async def is_active(*args, **kwargs):
        return True

    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        get_history,
    )
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", get_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", is_active)
    monkeypatch.setattr(
        chat_context,
        "_build_system_prompt",
        lambda **_kwargs: "SYSTEM",
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="continue",
        model_id="gpt-4",
        model_context_limit=3000,
        model_max_output_tokens=50,
    )

    assert prepared.compression.stage == "none"
    assert build_compression_events(
        agent=agent,
        compression=prepared.compression,
        trigger="proactive_threshold",
    ) == (None, None)


@pytest.mark.anyio
async def test_message_builder_uses_checkpoint_tail_instead_of_full_history(
    monkeypatch,
):
    conversation = SimpleNamespace(id=uuid4(), variables={})
    agent = SimpleNamespace(
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
    )
    checkpoint = SimpleNamespace(
        covered_through_message_id=uuid4(),
        summary_text="CHECKPOINT_SUMMARY",
    )
    tail = [
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.USER,
            content="TAIL_USER",
            file_urls=None,
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="TAIL_ASSISTANT",
            reasoning_content=None,
            tool_calls=None,
            round_id=None,
        ),
    ]
    tail_loader = AsyncMock(return_value=tail)

    async def fail_full_history(*args, **kwargs):
        raise AssertionError("full history must not be loaded with a checkpoint")

    monkeypatch.setattr(
        chat_context, "get_visible_conversation_messages_after", tail_loader
    )
    monkeypatch.setattr(
        chat_context, "get_visible_conversation_messages", fail_full_history
    )
    monkeypatch.setattr(
        chat_context, "_build_system_prompt", lambda **_kwargs: "SYSTEM"
    )

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=agent,
        conversation=conversation,
        user_message="CURRENT_USER",
        file_content=None,
        user_locale=None,
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        tool_timeouts=None,
        user=None,
        protected_round_id=None,
        context_checkpoint=checkpoint,
    )

    contents = [message.content for message in messages]
    assert contents == [
        "SYSTEM",
        "CHECKPOINT_SUMMARY",
        "TAIL_USER",
        "TAIL_ASSISTANT",
        "CURRENT_USER",
    ]
    assert 1 in protected
    tail_loader.assert_awaited_once()


@pytest.mark.anyio
async def test_prepare_model_context_rebuilds_with_new_checkpoint(monkeypatch):
    from app.services.context_checkpoint import ContextCheckpointResult

    conversation = SimpleNamespace(id=uuid4(), variables={})
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "recent_raw_turns": 1,
            "recent_tool_turns": 0,
            "output_token_reserve": 50,
            "safety_margin_tokens": 50,
            "checkpoint_min_new_turns": 1,
            "checkpoint_target_ratio": 0.6,
        },
    )
    checkpoint = SimpleNamespace(
        covered_through_message_id=uuid4(),
        summary_text="MODEL_CHECKPOINT",
    )
    raw_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.USER, content="OLD_HISTORY " * 220),
        Message(role=MessageRole.USER, content="CURRENT_USER"),
    ]
    checkpoint_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.ASSISTANT, content="MODEL_CHECKPOINT"),
        Message(role=MessageRole.USER, content="RECENT_TAIL"),
        Message(role=MessageRole.USER, content="CURRENT_USER"),
    ]
    raw_history = [
        SimpleNamespace(id=uuid4(), role=ConversationMessageRole.USER),
        SimpleNamespace(id=uuid4(), role=ConversationMessageRole.ASSISTANT),
    ]
    builder_checkpoints = []

    async def build_messages(**kwargs):
        active_checkpoint = kwargs.get("context_checkpoint")
        builder_checkpoints.append(active_checkpoint)
        if active_checkpoint:
            return checkpoint_messages, {1}
        return raw_messages, {len(raw_messages) - 1}

    async def no_session_compaction(messages, **kwargs):
        return list(messages), False, set(kwargs.get("protected_indexes") or ())

    create_checkpoint = AsyncMock(
        return_value=ContextCheckpointResult(
            checkpoint=checkpoint,
            created=True,
            covered_turns=2,
            retained_turns=1,
        )
    )

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        no_session_compaction,
    )
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(return_value=raw_history),
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.get_valid_context_checkpoint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.create_context_checkpoint",
        create_checkpoint,
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="CURRENT_USER",
        model_id="provider/test-model",
        model_context_limit=3000,
        model_max_output_tokens=50,
        provider="provider",
    )

    assert create_checkpoint.await_count == 1
    assert builder_checkpoints == [None, checkpoint]
    assert prepared.compression.stage == "macro"
    assert "checkpoint_summary" in (prepared.compression.actions or [])
    assert prepared.compression.after_tokens <= 2900 * 0.6


@pytest.mark.anyio
async def test_prepare_model_context_uses_macro_fallback_after_checkpoint_error(
    monkeypatch,
):
    from app.services.context_checkpoint import ContextCheckpointResult

    conversation = SimpleNamespace(id=uuid4(), variables={})
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "micro_compaction_enabled": False,
            "output_token_reserve": 50,
            "safety_margin_tokens": 50,
        },
    )
    source_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.USER, content="OLD_HISTORY " * 500),
        Message(role=MessageRole.USER, content="CURRENT_USER"),
    ]
    fallback_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.USER, content="CURRENT_USER"),
    ]
    fallback_meta = chat_context.CompressionMeta(
        stage="macro",
        before_tokens=6_000,
        after_tokens=10,
        input_budget=3_900,
        actions=["macro_summary"],
    )
    macro_fallback = Mock(return_value=(fallback_messages, fallback_meta, {1}))

    async def build_messages(**_kwargs):
        return source_messages, {2}

    async def no_session_compaction(messages, **kwargs):
        return list(messages), False, set(kwargs.get("protected_indexes") or ())

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        no_session_compaction,
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(
            return_value=[
                SimpleNamespace(id=uuid4(), role=ConversationMessageRole.USER),
                SimpleNamespace(id=uuid4(), role=ConversationMessageRole.ASSISTANT),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.get_valid_context_checkpoint",
        AsyncMock(return_value=None),
    )
    create_checkpoint = AsyncMock(
        return_value=ContextCheckpointResult(error="summary model unavailable")
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.create_context_checkpoint", create_checkpoint
    )
    monkeypatch.setattr(chat_context, "_apply_budget_compaction", macro_fallback)

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="CURRENT_USER",
        model_id="provider/test-model",
        model_context_limit=4_000,
        model_max_output_tokens=50,
        provider="provider",
    )

    create_checkpoint.assert_awaited_once()
    macro_fallback.assert_called_once()
    assert prepared.messages == fallback_messages
    assert prepared.compression.actions == ["macro_summary"]


@pytest.mark.anyio
async def test_checkpoint_failure_at_auto_trigger_uses_macro_fallback(
    monkeypatch,
):
    from app.services.context_checkpoint import ContextCheckpointResult

    conversation = SimpleNamespace(id=uuid4(), variables={})
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "micro_compaction_enabled": False,
            "macro_compaction_enabled": True,
            "macro_on_trigger": False,
            "warning_ratio": 0.5,
            "auto_compact_trigger_ratio": 0.8,
            "blocking_ratio": 0.95,
            "output_token_reserve": 0,
            "safety_margin_tokens": 0,
        },
    )
    source_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.USER, content="old history " * 6),
        Message(role=MessageRole.USER, content="CURRENT"),
    ]
    fallback_messages = [
        Message(role=MessageRole.SYSTEM, content="SYSTEM"),
        Message(role=MessageRole.USER, content="CURRENT"),
    ]
    fallback_meta = chat_context.CompressionMeta(
        stage="macro",
        before_tokens=90,
        after_tokens=10,
        input_budget=100,
        actions=["macro_summary"],
    )

    async def build_messages(**_kwargs):
        return source_messages, {2}

    async def no_session_compaction(messages, **kwargs):
        return list(messages), False, set(kwargs.get("protected_indexes") or ())

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", no_session_compaction
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda values, model_id, provider=None: sum(
            len(str(message.content or "")) for message in values
        ),
    )
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(
            return_value=[
                SimpleNamespace(id=uuid4(), role=ConversationMessageRole.USER),
                SimpleNamespace(id=uuid4(), role=ConversationMessageRole.ASSISTANT),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.get_valid_context_checkpoint",
        AsyncMock(return_value=None),
    )
    create_checkpoint = AsyncMock(
        return_value=ContextCheckpointResult(error="summary model unavailable")
    )
    monkeypatch.setattr(
        "app.services.context_checkpoint.create_context_checkpoint", create_checkpoint
    )
    macro_fallback = Mock(return_value=(fallback_messages, fallback_meta, {1}))
    monkeypatch.setattr(chat_context, "_apply_budget_compaction", macro_fallback)

    prepared = await chat_context.prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message="CURRENT",
        model_id="provider/test-model",
        model_context_limit=100,
        model_max_output_tokens=0,
        provider="provider",
    )

    create_checkpoint.assert_awaited_once()
    macro_fallback.assert_called_once()
    assert prepared.messages == fallback_messages
    assert prepared.compression.actions == ["macro_summary"]
