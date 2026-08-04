from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import Message, MessageRole
from app.services import chat_context


def _agent(**compression_config):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config=compression_config,
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


@pytest.mark.anyio
async def test_session_memory_failure_preserves_messages(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="question"),
    ]

    async def fail_to_load(_conversation_id):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", fail_to_load
    )

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="gpt-4",
        provider=None,
        protected_indexes={1},
    )

    assert changed is False
    assert protected == {1}
    assert [message.content for message in compacted] == ["system", "question"]
    assert compacted[1] is not messages[1]


@pytest.mark.anyio
async def test_session_memory_from_inactive_branch_is_ignored(monkeypatch):
    source_message_id = uuid4()

    async def load_snapshot(_conversation_id):
        return SimpleNamespace(
            summary_text="stale summary", source_message_id=source_message_id
        )

    async def inactive_branch(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", load_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", inactive_branch)

    messages = [Message(role=MessageRole.USER, content="keep raw history")]
    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="gpt-4",
        provider=None,
        protected_indexes={0},
    )

    assert changed is False
    assert protected == {0}
    assert compacted[0].content == "keep raw history"


@pytest.mark.anyio
async def test_history_override_inserts_and_protects_current_round(monkeypatch):
    protected_round_id = uuid4()

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": SimpleNamespace(value="assistant"),
                "round_id": protected_round_id,
                "content": "working",
                "reasoning_content": "private reasoning",
                "tool_calls": [
                    {"id": "call-1", "name": "lookup", "arguments": {"q": "x"}}
                ],
            },
            {
                "role": "tool",
                "round_id": protected_round_id,
                "content": "result",
                "tool_call_id": "call-1",
            },
            {
                "role": "tool",
                "content": "orphan result",
                "tool_call_id": "missing-call",
            },
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=str(protected_round_id),
    )

    assert [message.role for message in messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[1].content == "current question"
    assert messages[2].tool_calls[0].function.arguments == '{"q": "x"}'
    assert messages[3].tool_call_id == "call-1"
    assert protected == {1, 2, 3}


@pytest.mark.anyio
async def test_prepare_context_can_bypass_preflight_compression(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="large input"),
    ]

    async def build_messages(**kwargs):
        return messages, {1}

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider: 100,
    )

    prepared = await chat_context.prepare_model_context(
        agent=_agent(
            enabled=False,
            output_token_reserve=10,
            safety_margin_tokens=10,
        ),
        conversation=_conversation(),
        user_message="large input",
        model_id="gpt-4",
        model_context_limit=100,
        model_max_output_tokens=10,
    )

    assert prepared.messages == messages
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "none"
    assert prepared.compression.pressure_level == "over_budget"
    assert prepared.compression.actions == []


@pytest.mark.anyio
async def test_prepare_context_uses_protected_round_for_emergency_fallback(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old history"),
        Message(role=MessageRole.USER, content="current question"),
    ]

    async def build_messages(**kwargs):
        return messages, {2}

    async def skip_session_memory(messages, **kwargs):
        return [message.model_copy(deep=True) for message in messages], False, {2}

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", skip_session_memory
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider: 20 if len(messages) == 2 else 100,
    )

    prepared = await chat_context.prepare_model_context(
        agent=_agent(
            micro_compaction_enabled=False,
            macro_compaction_enabled=False,
            checkpoint_summary_enabled=False,
            output_token_reserve=10,
            safety_margin_tokens=10,
        ),
        conversation=_conversation(),
        user_message="current question",
        model_id="gpt-4",
        model_context_limit=100,
        model_max_output_tokens=10,
        protected_round_id=uuid4(),
    )

    assert [message.content for message in prepared.messages] == [
        "system",
        "current question",
    ]
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "macro"
    assert prepared.compression.after_tokens == 20
    assert prepared.compression.actions == ["emergency_fallback"]


@pytest.mark.anyio
async def test_prepare_context_raises_when_emergency_messages_exceed_budget(
    monkeypatch,
):
    messages = [
        Message(role=MessageRole.SYSTEM, content="oversized system"),
        Message(role=MessageRole.USER, content="oversized question"),
    ]

    async def build_messages(**kwargs):
        return messages, {1}

    async def skip_session_memory(messages, **kwargs):
        return [message.model_copy(deep=True) for message in messages], False, {1}

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", skip_session_memory
    )
    monkeypatch.setattr(
        chat_context,
        "_estimate_message_tokens",
        lambda messages, model_id, provider: 100,
    )

    with pytest.raises(ContextLengthError, match="emergency fallback"):
        await chat_context.prepare_model_context(
            agent=_agent(
                micro_compaction_enabled=False,
                macro_compaction_enabled=False,
                checkpoint_summary_enabled=False,
                output_token_reserve=10,
                safety_margin_tokens=10,
            ),
            conversation=_conversation(),
            user_message="oversized question",
            model_id="gpt-4",
            model_context_limit=100,
            model_max_output_tokens=10,
        )
