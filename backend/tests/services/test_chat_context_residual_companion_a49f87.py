from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.llm.types import Message, MessageRole
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "system_prompt": "",
        "enable_memory": False,
        "enable_user_input_request": False,
        "tools_config": [],
        "context_compression_config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


@pytest.mark.anyio
async def test_history_override_inserts_protected_user_before_tool_round_and_skips_orphans(
    monkeypatch,
):
    file_builder = AsyncMock(return_value="file text")
    monkeypatch.setattr(
        chat_context, "_build_file_content_for_user_message", file_builder
    )

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "needs tool",
                "round_id": "round-1",
                "tool_calls": [{"id": "call-1", "name": "lookup", "arguments": {}}],
            },
            {"role": "tool", "content": "kept", "tool_call_id": "call-1"},
            {"role": "tool", "content": "orphan", "tool_call_id": "missing"},
            {"role": "user", "content": "old", "file_urls": [{"url": "u"}]},
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id="round-1",
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.USER,
    ]
    assert messages[1].content == "current"
    assert messages[-1].content.endswith("file text\n</uploaded_files>")
    assert protected == {1, 2}


@pytest.mark.anyio
async def test_visible_history_current_user_and_valid_tool_paths(monkeypatch):
    current_id = uuid4()
    history = [
        SimpleNamespace(
            id=current_id,
            role=ConversationMessageRole.USER,
            content="stored current",
            file_urls=None,
            round_id="round-1",
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.ASSISTANT,
            content="assistant",
            reasoning_content="why",
            tool_calls=[{"id": "call-1", "name": "lookup", "arguments": "{}"}],
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.TOOL,
            content='{"kind":"media.image","images":[{},{}]}',
            tool_call_id="call-1",
            tool_name="image",
            round_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=ConversationMessageRole.TOOL,
            content="orphan",
            tool_call_id="missing",
            tool_name="missing",
            round_id=None,
        ),
    ]
    monkeypatch.setattr(
        chat_context,
        "get_visible_conversation_messages",
        AsyncMock(return_value=history),
    )

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="fresh current",
        file_content="uploaded",
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=current_id,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id="round-1",
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert "fresh current" in str(messages[1].content)
    assert "uploaded" in str(messages[1].content)
    assert messages[3].content == "Image generation succeeded. Generated 2 images."
    assert protected == {1}


@pytest.mark.anyio
async def test_file_builder_updates_changed_cached_file_urls(monkeypatch):
    source = SimpleNamespace(file_urls=[{"url": "old"}], save=AsyncMock())
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        AsyncMock(return_value=("content", [{"url": "new"}])),
    )

    content = await chat_context._build_file_content_for_user_message(
        agent=_agent(),
        file_urls=source.file_urls,
        legacy_files=[{"name": "legacy"}],
        user_locale="en",
        tool_timeouts={"read": 1},
        user=SimpleNamespace(id="user-1"),
        source_message=source,
    )

    assert content == "content"
    assert source.file_urls == [{"url": "new"}]
    source.save.assert_awaited_once_with(update_fields=["file_urls"])


def test_tool_result_compaction_summarizes_json_truncates_plain_and_preserves_protected(
    monkeypatch,
):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(
            role=MessageRole.TOOL,
            content='{"kind":"media.video","status":"failed"}',
            tool_call_id="v",
        ),
        Message(role=MessageRole.USER, content="older"),
        Message(role=MessageRole.TOOL, content="x" * 1300, tool_call_id="plain"),
        Message(role=MessageRole.USER, content="kept raw"),
        Message(role=MessageRole.TOOL, content="recent", tool_call_id="recent"),
        Message(role=MessageRole.USER, content="protected"),
    ]
    monkeypatch.setattr(
        chat_context, "_estimate_single_message_tokens", lambda *a, **k: 999
    )

    compacted, changed, protected = (
        chat_context._apply_selective_tool_result_compaction(
            messages,
            model_id="model",
            provider=None,
            keep_recent_tool_results=0,
            tool_result_compact_min_tokens=1,
            recent_raw_turns=0,
            recent_tool_turns=0,
            protected_indexes={7},
        )
    )

    assert changed is True
    assert compacted[2].content == "Video generation failed: unknown error"
    assert len(compacted[4].content) == 1200
    assert compacted[6].content == "recent"
    assert compacted[7].content == "protected"
    assert protected == {7}


@pytest.mark.anyio
async def test_session_memory_compaction_respects_active_branch_and_compacts_when_ready(
    monkeypatch,
):
    snapshot = SimpleNamespace(summary_text="memory summary", source_message_id=uuid4())
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        AsyncMock(return_value=snapshot),
    )
    active_branch = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", active_branch)
    monkeypatch.setattr(
        chat_context, "_estimate_single_message_tokens", lambda *a, **k: 1
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="one"),
        Message(role=MessageRole.ASSISTANT, content="two"),
        Message(role=MessageRole.USER, content="three"),
        Message(role=MessageRole.ASSISTANT, content="four"),
        Message(role=MessageRole.USER, content="five"),
    ]

    unchanged, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="model",
        provider=None,
        recent_raw_turns=1,
        recent_tool_turns=0,
        protected_indexes={5},
    )
    (
        compacted,
        compacted_changed,
        compacted_protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="model",
        provider=None,
        recent_raw_turns=1,
        recent_tool_turns=0,
        protected_indexes={5},
    )

    assert changed is False
    assert unchanged == messages and protected == {5}
    assert compacted_changed is True
    assert [message.content for message in compacted] == [
        "system",
        "memory summary",
        "five",
    ]
    assert compacted_protected == {1, 2}


@pytest.mark.anyio
async def test_prepare_context_macro_on_trigger_without_micro_runs_budget_compaction(
    monkeypatch,
):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="current"),
    ]
    budget_compaction = Mock(
        return_value=(
            [messages[0], messages[-1]],
            chat_context.CompressionMeta(
                stage="macro",
                before_tokens=80,
                after_tokens=40,
                input_budget=100,
                actions=["macro_summary"],
            ),
            {1},
        )
    )
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
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", lambda *a, **k: 80)
    monkeypatch.setattr(chat_context, "_apply_budget_compaction", budget_compaction)

    prepared = await chat_context.prepare_model_context(
        agent=_agent(
            context_compression_config={
                "micro_compaction_enabled": False,
                "macro_on_trigger": True,
                "checkpoint_summary_enabled": False,
                "output_token_reserve": 0,
                "safety_margin_tokens": 0,
                "warning_ratio": 0.5,
                "auto_compact_trigger_ratio": 0.7,
                "blocking_ratio": 0.9,
            }
        ),
        conversation=_conversation(),
        user_message="current",
        model_id="model",
        model_context_limit=100,
        model_max_output_tokens=0,
    )

    assert prepared.compression.stage == "macro"
    assert prepared.protected_indexes == {1}
    assert budget_compaction.called
