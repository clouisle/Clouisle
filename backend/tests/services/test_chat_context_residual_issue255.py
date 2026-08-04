from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def _agent(*, config=None):
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


@pytest.mark.anyio
async def test_history_override_inserts_protected_current_user_and_filters_tool_results():
    protected_round_id = uuid4()

    messages, protected_indexes = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "calling tool",
                "round_id": protected_round_id,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "generate_image",
                        "arguments": {"p": "cat"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "orphan result should not reach the model",
                "tool_call_id": "missing-call",
            },
            {
                "role": "tool",
                "content": '{"kind":"media.image","images":[{}],"model":"img-1"}',
                "round_id": protected_round_id,
                "tool_call_id": "call-1",
                "tool_name": "generate_image",
            },
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
    assert messages[1].content == "current question"
    assert (
        messages[2].tool_calls
        and messages[2].tool_calls[0].function.arguments == '{"p": "cat"}'
    )
    assert (
        messages[3].content
        == "Image generation succeeded. Generated 1 image using model img-1."
    )
    assert not any("orphan result" in str(message.content) for message in messages)
    assert protected_indexes == {1, 2, 3}


def test_tool_result_summaries_cover_media_skill_and_fallback_branches():
    assert (
        chat_context.summarize_tool_result_for_llm(
            "generate_video",
            '{"kind":"media.video","status":"processing","task_id":"task-1"}',
        )
        == "Video generation started. Task task-1 is processing."
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            "generate_video",
            '{"kind":"media.video","status":"failed","error":"quota"}',
        )
        == "Video generation failed: quota"
    )
    assert (
        chat_context.summarize_tool_result_for_llm(
            "skill_loader",
            '{"result":{"type":"skill_instructions","status":"loaded","skill":{"display_name":"Ponytail"}}}',
        )
        == "Skill instructions for Ponytail were loaded."
    )
    assert chat_context.summarize_tool_result_for_llm(None, "not-json") == "not-json"


@pytest.mark.anyio
async def test_session_memory_compaction_keeps_media_and_recent_tool_turns(monkeypatch):
    source_message_id = uuid4()
    conversation = _conversation()
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old user"),
        Message(role=MessageRole.ASSISTANT, content="old assistant"),
        Message(role=MessageRole.USER, content="media [image]"),
        Message(role=MessageRole.ASSISTANT, content="media answer"),
        Message(role=MessageRole.USER, content="tool user"),
        Message(
            role=MessageRole.ASSISTANT,
            content="tool call",
            tool_calls=[
                chat_context.ToolCall(
                    id="call-1",
                    type="function",
                    function=chat_context.FunctionCall(name="lookup", arguments="{}"),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content="tool result", tool_call_id="call-1"),
        Message(role=MessageRole.USER, content="recent user"),
    ]

    async def fake_get_ready_session_memory(conversation_id):
        assert conversation_id == conversation.id
        return SimpleNamespace(
            summary_text="SESSION MEMORY SUMMARY",
            source_message_id=source_message_id,
        )

    async def fake_is_message_on_active_branch(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        fake_get_ready_session_memory,
    )
    monkeypatch.setattr(
        chat_context,
        "is_message_on_active_branch",
        fake_is_message_on_active_branch,
    )
    monkeypatch.setattr(
        chat_context, "_estimate_single_message_tokens", lambda *args, **kwargs: 1
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
        recent_tool_turns=1,
    )

    contents = [message.content for message in compacted]
    assert did_compact is True
    assert protected == {1}
    assert "SESSION MEMORY SUMMARY" in contents
    assert "old user" not in contents
    assert "media [image]" in contents
    assert "tool result" in contents
    assert "recent user" in contents


@pytest.mark.anyio
async def test_session_memory_compaction_noops_for_missing_inactive_and_failed_snapshots(
    monkeypatch,
):
    conversation = _conversation()
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="recent"),
    ]

    async def inactive_branch(*args, **kwargs):
        return False

    async def missing_snapshot(conversation_id):
        return None

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        missing_snapshot,
    )
    (
        cloned,
        did_compact,
        protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
        protected_indexes={2},
    )
    assert did_compact is False
    assert [message.content for message in cloned] == ["system", "old", "recent"]
    assert protected == {2}

    async def inactive_snapshot(conversation_id):
        return SimpleNamespace(summary_text="summary", source_message_id=uuid4())

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        inactive_snapshot,
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", inactive_branch)
    (
        cloned,
        did_compact,
        protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
        protected_indexes={2},
    )
    assert did_compact is False
    assert [message.content for message in cloned] == ["system", "old", "recent"]
    assert protected == {2}

    async def failing_snapshot(conversation_id):
        raise RuntimeError("session store unavailable")

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory",
        failing_snapshot,
    )
    (
        cloned,
        did_compact,
        protected,
    ) = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=conversation,
        model_id="gpt-4",
        provider=None,
        recent_raw_turns=1,
        protected_indexes={2},
    )
    assert did_compact is False
    assert [message.content for message in cloned] == ["system", "old", "recent"]
    assert protected == {2}


def test_context_pressure_and_token_budget_boundaries():
    budget = chat_context._build_token_budget(
        context_limit=9,
        model_max_output_tokens=99,
        output_token_reserve=99,
        safety_margin_tokens=99,
    )
    thresholds = chat_context._build_compression_thresholds(
        token_budget=budget,
        warning_ratio=0.7,
        trigger_ratio=0.8,
        blocking_ratio=0.92,
    )

    assert budget.output_reserve == 3
    assert budget.input_budget == 1
    assert thresholds.warning_input_budget == 1
    assert thresholds.trigger_input_budget == 1
    assert thresholds.blocking_input_budget == 1
    assert (
        chat_context._assess_context_pressure(
            before_tokens=0,
            token_budget=budget,
            thresholds=thresholds,
        )
        == "normal"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=1,
            token_budget=budget,
            thresholds=thresholds,
        )
        == "blocking"
    )
    assert (
        chat_context._assess_context_pressure(
            before_tokens=2,
            token_budget=budget,
            thresholds=thresholds,
        )
        == "over_budget"
    )


@pytest.mark.anyio
async def test_prepare_model_context_raises_when_emergency_fallback_still_exceeds_budget(
    monkeypatch,
):
    async def fake_build_messages(**kwargs):
        return [
            Message(role=MessageRole.SYSTEM, content="system"),
            Message(role=MessageRole.USER, content="current user"),
        ], {1}

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", fake_build_messages
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 10
    )
    monkeypatch.setattr(
        chat_context,
        "_apply_micro_compaction",
        lambda **kwargs: (kwargs["messages"], kwargs["token_budget"], set()),
    )

    with pytest.raises(ContextLengthError) as exc_info:
        await chat_context.prepare_model_context(
            agent=_agent(
                config={
                    "output_token_reserve": 1,
                    "safety_margin_tokens": 1,
                    "micro_compaction_enabled": False,
                    "macro_compaction_enabled": True,
                    "checkpoint_summary_enabled": False,
                }
            ),
            conversation=_conversation(),
            user_message="current user",
            model_id="tiny-model",
            model_context_limit=3,
            model_max_output_tokens=1,
            provider="test-provider",
        )

    assert exc_info.value.max_tokens == 1
    assert exc_info.value.actual_tokens == 10
