from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.services import chat_context


def _agent(**config):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=config,
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


@pytest.mark.anyio
async def test_history_override_inserts_protected_user_before_current_round_tool_step():
    round_id = uuid4()

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content="current file",
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "need tool",
                "round_id": round_id,
                "tool_calls": [
                    {"id": "call-ok", "name": "lookup", "arguments": {"q": "x"}}
                ],
            },
            {
                "role": "tool",
                "content": '{"kind":"media.video","status":"failed","error":"boom"}',
                "tool_name": "video",
                "tool_call_id": "call-ok",
                "round_id": round_id,
            },
            {
                "role": "tool",
                "content": "orphan result",
                "tool_call_id": "missing-call",
                "round_id": round_id,
            },
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=round_id,
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[1].content == (
        "current question\n\n<uploaded_files>\ncurrent file\n</uploaded_files>"
    )
    assert messages[3].content == "Video generation failed: boom"
    assert protected == {1, 2, 3}


@pytest.mark.anyio
async def test_session_memory_inactive_snapshot_returns_cloned_messages(monkeypatch):
    source_id = uuid4()
    before_created_at = object()
    calls = []
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
        Message(role=MessageRole.USER, content="current"),
    ]

    async def fake_get_ready_session_memory(conversation_id):
        calls.append(("snapshot", conversation_id))
        return SimpleNamespace(summary_text="summary", source_message_id=source_id)

    async def fake_is_message_on_active_branch(conversation_id, message_id, **kwargs):
        calls.append(
            ("branch", conversation_id, message_id, kwargs.get("before_created_at"))
        )
        return False

    conversation = _conversation()
    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        fake_get_ready_session_memory,
    )
    monkeypatch.setattr(
        chat_context,
        "is_message_on_active_branch",
        fake_is_message_on_active_branch,
    )

    (
        compacted,
        did_compact,
        protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
        recent_tool_turns=0,
        protected_indexes={3},
        before_created_at=before_created_at,
    )

    assert did_compact is False
    assert [message.content for message in compacted] == [
        "system",
        "old",
        "old answer",
        "current",
    ]
    assert compacted is not messages
    assert protected == {3}
    assert calls == [
        ("snapshot", conversation.id),
        ("branch", conversation.id, source_id, before_created_at),
    ]


def test_selective_tool_result_compaction_summarizes_only_old_unprotected_large_tools(
    monkeypatch,
):
    old_tool_json = '{"kind":"media.image","images":["a","b"],"model":"img-model"}'
    kept_historical_tool_text = "KEPT HISTORICAL RAW " * 200
    recent_tool_text = "RECENT RAW " * 200
    protected_tool_text = "PROTECTED RAW " * 200
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old tool turn"),
        Message(
            role=MessageRole.ASSISTANT,
            content="calling",
            tool_calls=[
                ToolCall(
                    id="old-call",
                    type="function",
                    function=FunctionCall(name="image", arguments="{}"),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content=old_tool_json, tool_call_id="old-call"),
        Message(role=MessageRole.USER, content="kept historical tool turn"),
        Message(
            role=MessageRole.TOOL,
            content=kept_historical_tool_text,
            tool_call_id="kept-historical",
        ),
        Message(role=MessageRole.USER, content="protected tool turn"),
        Message(
            role=MessageRole.TOOL, content=protected_tool_text, tool_call_id="protected"
        ),
        Message(role=MessageRole.USER, content="recent tool turn"),
        Message(role=MessageRole.TOOL, content=recent_tool_text, tool_call_id="recent"),
    ]

    monkeypatch.setattr(
        chat_context,
        "_estimate_single_message_tokens",
        lambda message, *, model_id, provider=None: len(str(message.content)),
    )

    compacted, trimmed, protected = (
        chat_context._apply_selective_tool_result_compaction(
            messages,
            model_id="gpt-4",
            provider=None,
            keep_recent_tool_results=1,
            tool_result_compact_min_tokens=1,
            recent_raw_turns=1,
            recent_tool_turns=0,
            protected_indexes={7},
        )
    )

    assert trimmed is True
    assert compacted[3].content == (
        "Image generation succeeded. Generated 2 images using model img-model."
    )
    assert compacted[5].content == kept_historical_tool_text
    assert compacted[7].content == protected_tool_text
    assert compacted[9].content == recent_tool_text
    assert protected == {7}
