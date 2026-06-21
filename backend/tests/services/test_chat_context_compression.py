from types import SimpleNamespace
from uuid import uuid4

import pytest

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
async def test_session_memory_compaction_runs_again_after_file_trim(monkeypatch):
    """After file-content trim rebuilds base_messages, the session-memory
    compaction must be re-applied so the rebuilt list does not silently
    revert to the original raw history.
    """

    rebuild_calls = {"count": 0}
    session_memory_calls: list[int] = []

    async def fake_rebuild(*args, **kwargs):
        rebuild_calls["count"] += 1
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
        phase = rebuild_calls["count"]
        session_memory_calls.append(phase)
        rebuilt = [
            messages[0],
            Message(
                role=MessageRole.ASSISTANT,
                content=f"COMPRESSED_SUMMARY phase={phase}",
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

    assert rebuild_calls["count"] >= 1
    assert session_memory_calls, session_memory_calls
    assert 1 in session_memory_calls, session_memory_calls
