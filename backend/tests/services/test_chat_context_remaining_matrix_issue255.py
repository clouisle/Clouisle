from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def _agent(*, context_config=None):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="Hello {{name}} {{query}}",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=context_config or {},
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={"name": "Ada"})


def test_tool_result_summary_matrix_covers_media_skill_and_fallbacks():
    assert chat_context.summarize_tool_result_for_llm(None, "not json") == "not json"
    assert (
        chat_context.summarize_tool_result_for_llm(None, '["not", "dict"]')
        == '["not", "dict"]'
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"kind":"media.image","error":"bad prompt"}',
        )
        == "Image generation failed: bad prompt"
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"kind":"media.image","images":[{},{}],"model":"img"}',
        )
        == "Image generation succeeded. Generated 2 images using model img."
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"kind":"media.video","status":"processing","task_id":"task-1"}',
        )
        == "Video generation started. Task task-1 is processing."
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"kind":"media.video","status":"failed"}',
        )
        == "Video generation failed: unknown error"
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"kind":"media.video","status":"complete","model":"vid"}',
        )
        == "Video generation succeeded using model vid."
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            None,
            '{"result":{"type":"skill_instructions","status":"loaded","skill":{"name":"Shell"}}}',
        )
        == "Skill instructions for Shell were loaded."
    )


@pytest.mark.anyio
async def test_history_override_inserts_protected_user_before_assistant_and_filters_tools(
    monkeypatch,
):
    protected_round_id = uuid4()

    async def no_history(*_args, **_kwargs):
        return []

    monkeypatch.setattr(chat_context, "get_visible_conversation_messages", no_history)

    messages, protected_indexes = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content=None,
        user_locale="zh",
        history_override=[
            SimpleNamespace(
                role="assistant",
                content="assistant with call",
                reasoning_content="private chain",
                tool_calls=[
                    {"id": "call-1", "name": "lookup", "arguments": {"q": "x"}}
                ],
                round_id=protected_round_id,
            ),
            {"role": "tool", "content": "kept", "tool_call_id": "call-1"},
            {"role": "tool", "content": "dropped", "tool_call_id": "missing"},
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=protected_round_id,
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[0].content.startswith("Hello Ada current question")
    assert "## 回复语言" in messages[0].content
    assert messages[1].content == "current question"
    assert messages[2].tool_calls[0].function.arguments == '{"q": "x"}'
    assert messages[3].content == "kept"
    assert protected_indexes == {1, 2}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("snapshot", "active", "raises"),
    [
        (None, True, False),
        (SimpleNamespace(summary_text="", source_message_id=uuid4()), True, False),
        (
            SimpleNamespace(summary_text="summary", source_message_id=uuid4()),
            False,
            False,
        ),
        (
            SimpleNamespace(summary_text="summary", source_message_id=uuid4()),
            True,
            True,
        ),
    ],
)
async def test_session_memory_compaction_noop_matrix(
    monkeypatch, snapshot, active, raises
):
    async def fake_get_ready_session_memory(conversation_id):
        if raises:
            raise RuntimeError("db down")
        return snapshot

    async def fake_is_message_on_active_branch(*args, **kwargs):
        return active

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        fake_get_ready_session_memory,
    )
    monkeypatch.setattr(
        chat_context,
        "is_message_on_active_branch",
        fake_is_message_on_active_branch,
    )

    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.ASSISTANT, content="answer"),
        Message(role=MessageRole.USER, content="current"),
    ]

    (
        compacted,
        did_compact,
        protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
        recent_tool_turns=0,
        protected_indexes={3},
    )

    assert [message.content for message in compacted] == [
        message.content for message in messages
    ]
    assert did_compact is False
    assert protected == {3}


@pytest.mark.anyio
async def test_prepare_model_context_raises_when_emergency_fallback_is_still_too_large(
    monkeypatch,
):
    async def fake_build_messages_with_file_content(**kwargs):
        return [
            Message(role=MessageRole.SYSTEM, content="system"),
            Message(role=MessageRole.USER, content="huge current prompt"),
        ], {1}

    monkeypatch.setattr(
        chat_context,
        "_build_messages_with_file_content",
        fake_build_messages_with_file_content,
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider=None: 50,
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_session_memory_compaction",
        lambda messages, **kwargs: _async_tuple(
            messages, False, kwargs["protected_indexes"]
        ),
    )

    with pytest.raises(ContextLengthError) as exc_info:
        await chat_context.prepare_model_context(
            agent=_agent(
                context_config={
                    "output_token_reserve": 1,
                    "safety_margin_tokens": 1,
                    "recent_raw_turns": 1,
                    "recent_tool_turns": 0,
                    "checkpoint_summary_enabled": False,
                }
            ),
            conversation=_conversation(),
            user_message="huge current prompt",
            model_id="gpt-4",
            model_context_limit=3,
            model_max_output_tokens=1,
            provider="test-provider",
        )

    assert exc_info.value.max_tokens == 1
    assert exc_info.value.actual_tokens == 50


async def _async_tuple(*values):
    return values
