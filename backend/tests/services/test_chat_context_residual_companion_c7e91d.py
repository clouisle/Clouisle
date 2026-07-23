from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.types import Message, MessageRole
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context


def _conversation():
    return SimpleNamespace(id="conversation-1", variables={})


def _agent():
    return SimpleNamespace(
        id="agent-1",
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={},
    )


def test_content_and_turn_helpers_cover_empty_residual_boundaries(monkeypatch):
    monkeypatch.setattr(
        chat_context, "build_uploaded_image_reference_text", lambda images: ""
    )

    assert (
        chat_context._build_current_user_content("question", [{}], False) == "question"
    )
    assert (
        chat_context._split_turn_blocks(
            [Message(role=MessageRole.SYSTEM, content="system")]
        )[2]
        == []
    )

    summary = chat_context._summarize_block(
        [
            Message(role=MessageRole.ASSISTANT, content=""),
            Message(role=MessageRole.TOOL, content="", tool_call_id=None),
        ]
    )
    assert summary == "Conversation turn preserved in compact summary."


def test_selective_compaction_keeps_media_and_multiple_recent_tool_turns(monkeypatch):
    messages = [
        Message(role=MessageRole.USER, content="image"),
        Message(role=MessageRole.USER, content="tool one"),
        Message(role=MessageRole.TOOL, content="one", tool_call_id="one"),
        Message(role=MessageRole.USER, content="tool two"),
        Message(role=MessageRole.TOOL, content="two", tool_call_id="two"),
    ]
    analyses = iter(
        [
            {"contains_media": True, "contains_tool": False},
            {"contains_media": False, "contains_tool": True},
            {"contains_media": False, "contains_tool": True},
        ]
    )
    monkeypatch.setattr(
        chat_context, "_analyze_turn_block", lambda *a, **k: next(analyses)
    )

    compacted, changed, _ = chat_context._apply_selective_tool_result_compaction(
        messages,
        model_id="model",
        provider=None,
        keep_recent_tool_results=0,
        tool_result_compact_min_tokens=1,
        recent_raw_turns=0,
        recent_tool_turns=2,
    )

    assert compacted == messages
    assert changed is False


def test_macro_compaction_returns_clone_when_every_block_is_protected():
    messages = [
        Message(role=MessageRole.USER, content="one"),
        Message(role=MessageRole.USER, content="two"),
    ]

    compacted, summary_turns, retained_turns, _, _, protected = (
        chat_context._apply_macro_compaction(
            messages,
            model_id="model",
            provider=None,
            recent_raw_turns=0,
            recent_tool_turns=0,
            protected_indexes={0, 1},
        )
    )

    assert compacted == messages and compacted is not messages
    assert summary_turns == 0
    assert retained_turns == 2
    assert protected == {0, 1}


@pytest.mark.anyio
async def test_history_paths_skip_unknown_override_and_stored_current_user(monkeypatch):
    override_messages, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        file_content=None,
        user_locale="en",
        history_override=[{"role": "unknown", "content": "ignored"}],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )
    assert [message.content for message in override_messages] == [
        override_messages[0].content,
        "current",
    ]

    current_id = "current-id"
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=current_id,
                    role=ConversationMessageRole.USER,
                    content="stored",
                    file_urls=None,
                    round_id=None,
                )
            ]
        ),
    )
    history_messages, _ = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="fresh",
        file_content=None,
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=current_id,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )
    assert history_messages[-1].content == "fresh"


@pytest.mark.anyio
async def test_micro_compaction_runs_at_exact_trigger_without_actions(monkeypatch):
    messages = [Message(role=MessageRole.USER, content="current")]
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", lambda *a, **k: 10)
    monkeypatch.setattr(
        chat_context,
        "_compact_message_reasoning",
        lambda *a, **k: (messages, False, set()),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_selective_tool_result_compaction",
        lambda *a, **k: (messages, False, set()),
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        AsyncMock(return_value=(messages, False, set())),
    )

    compacted, compression, _ = await chat_context._apply_micro_compaction(
        messages=messages,
        conversation=_conversation(),
        model_id="model",
        provider=None,
        token_budget=chat_context.TokenBudget(10, 0, 0, 10),
        trigger_budget=10,
    )

    assert compacted == messages
    assert compression.stage == "none"
    assert compression.actions == []


def test_budget_compaction_does_not_duplicate_macro_action(monkeypatch):
    messages = [Message(role=MessageRole.USER, content="old")]
    compression = chat_context.CompressionMeta(
        stage="micro",
        before_tokens=20,
        after_tokens=20,
        input_budget=10,
        actions=["macro_summary"],
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_macro_compaction",
        lambda *a, **k: (messages, 1, 0, 0, 1, set()),
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", lambda *a, **k: 5)

    _, result, _ = chat_context._apply_budget_compaction(
        messages=messages,
        model_id="model",
        provider=None,
        token_budget=chat_context.TokenBudget(10, 0, 0, 10),
        compression=compression,
        file_content_trimmed=False,
    )

    assert result.actions == ["macro_summary"]
