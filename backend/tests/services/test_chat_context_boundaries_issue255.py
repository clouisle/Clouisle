from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import ContentPart, ContentType, Message, MessageRole
from app.services import chat_context


def _agent(**compression_overrides):
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={
            "output_token_reserve": 10,
            "safety_margin_tokens": 0,
            **compression_overrides,
        },
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


@pytest.mark.anyio
async def test_history_override_preserves_protected_round_and_valid_tool_results(
    monkeypatch,
):
    protected_round_id = uuid4()

    async def no_history(*_args, **_kwargs):
        return []

    monkeypatch.setattr(chat_context, "get_visible_conversation_messages", no_history)

    messages, protected = await chat_context._build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="current question",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": "assistant",
                "content": "working",
                "round_id": protected_round_id,
                "tool_calls": [
                    {"id": "call-1", "name": "lookup", "arguments": {"q": "x"}}
                ],
            },
            {
                "role": "tool",
                "content": "result",
                "tool_call_id": "call-1",
                "round_id": protected_round_id,
            },
            {
                "role": "tool",
                "content": "orphan",
                "tool_call_id": "missing",
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

    assert [message.role for message in messages[1:]] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert messages[1].content == "current question"
    assert messages[2].tool_calls[0].function.arguments == '{"q": "x"}'
    assert messages[3].tool_call_id == "call-1"
    assert protected == {1, 2, 3}


def test_file_content_trimming_and_tool_turn_summary_boundaries():
    assert chat_context._trim_file_content(None) == (None, False)
    content = "a" * 12000 + " middle " + "z" * 4000
    trimmed, changed = chat_context._trim_file_content(content)
    assert changed is True
    assert trimmed.startswith("a" * 12000)
    assert trimmed.endswith("z" * 4000)
    assert "file content trimmed" in trimmed

    call = chat_context.ToolCall(
        id="call-1",
        type="function",
        function=chat_context.FunctionCall(name="lookup", arguments="{}"),
    )
    summary = chat_context._summarize_block(
        [
            Message(role=MessageRole.USER, content="question"),
            Message(role=MessageRole.ASSISTANT, content="working", tool_calls=[call]),
            Message(role=MessageRole.TOOL, content="answer", tool_call_id="call-1"),
        ]
    )
    assert summary == (
        "User asked: question ; Assistant responded: working ; "
        "Tools involved: lookup, call-1 ; Tool outcomes: answer"
    )


@pytest.mark.parametrize(
    ("stored_content", "expected"),
    [
        ("plain text", "plain text"),
        ('["not", "an", "object"]', '["not", "an", "object"]'),
        (
            '{"kind":"media.image","images":[{},{}],"model":"image-v1"}',
            "Image generation succeeded. Generated 2 images using model image-v1.",
        ),
        (
            '{"kind":"media.image","error":"quota exceeded"}',
            "Image generation failed: quota exceeded",
        ),
        (
            '{"kind":"media.video","status":"processing","task_id":"task-1"}',
            "Video generation started. Task task-1 is processing.",
        ),
        (
            '{"kind":"media.video","status":"failed"}',
            "Video generation failed: unknown error",
        ),
        (
            '{"kind":"media.video","status":"completed","model":"video-v1"}',
            "Video generation succeeded using model video-v1.",
        ),
        (
            '{"result":{"type":"skill_instructions","status":"loaded",'
            '"skill":{"display_name":"Reports"}}}',
            "Skill instructions for Reports were loaded.",
        ),
    ],
)
def test_tool_result_summaries_cover_structured_payloads(stored_content, expected):
    assert chat_context.summarize_tool_result_for_llm(None, stored_content) == expected


def test_macro_compaction_summarizes_only_unprotected_old_turns(monkeypatch):
    monkeypatch.setattr(
        chat_context,
        "_estimate_single_message_tokens",
        lambda *args, **kwargs: 1,
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old question"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
        Message(role=MessageRole.USER, content="tool question"),
        Message(
            role=MessageRole.ASSISTANT,
            content="calling",
            tool_calls=[
                chat_context.ToolCall(
                    id="call-1",
                    type="function",
                    function=chat_context.FunctionCall(name="lookup", arguments="{}"),
                )
            ],
        ),
        Message(role=MessageRole.TOOL, content="tool result", tool_call_id="call-1"),
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="image question"),
                ContentPart(
                    type=ContentType.IMAGE,
                    image=chat_context.ImageContent(
                        url="https://example.test/image.png"
                    ),
                ),
            ],
        ),
        Message(role=MessageRole.ASSISTANT, content="image answer"),
        Message(role=MessageRole.USER, content="protected question"),
        Message(role=MessageRole.ASSISTANT, content="protected answer"),
        Message(role=MessageRole.USER, content="recent question"),
    ]

    compacted, summary_turns, recent_turns, tool_turns, blocks, protected = (
        chat_context._apply_macro_compaction(
            messages,
            model_id="test-model",
            provider=None,
            recent_raw_turns=1,
            recent_tool_turns=1,
            protected_indexes={8, 9},
        )
    )

    contents = [
        chat_context._stringify_content(message.content) for message in compacted
    ]
    assert summary_turns == blocks == 1
    assert recent_turns == 1
    assert tool_turns == 1
    assert contents[1].startswith(chat_context.MACRO_SUMMARY_PREFIX)
    assert "old question" in contents[1]
    assert "tool question" in contents
    assert "image question\n[image]" in contents
    assert "protected question" in contents
    assert "recent question" in contents
    assert protected == {7, 8}


@pytest.mark.anyio
async def test_session_memory_failure_returns_deep_clones(monkeypatch):
    async def fail_snapshot(_conversation_id):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", fail_snapshot
    )
    original = [Message(role=MessageRole.USER, content="keep me")]

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        original,
        conversation=_conversation(),
        model_id="test-model",
        provider=None,
        protected_indexes={0},
    )

    assert changed is False
    assert protected == {0}
    assert compacted == original
    assert compacted[0] is not original[0]


@pytest.mark.anyio
@pytest.mark.parametrize("snapshot_case", ["missing", "inactive", "short"])
async def test_session_memory_compaction_noop_boundaries(monkeypatch, snapshot_case):
    snapshot = None
    if snapshot_case != "missing":
        snapshot = SimpleNamespace(summary_text="summary", source_message_id=uuid4())

    async def get_snapshot(_conversation_id):
        return snapshot

    async def active_branch(*args, **kwargs):
        return snapshot_case != "inactive"

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", get_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", active_branch)
    messages = [
        Message(role=MessageRole.USER, content="first"),
        Message(role=MessageRole.ASSISTANT, content="answer"),
    ]

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="test-model",
        provider=None,
        recent_raw_turns=2,
        protected_indexes={0},
    )

    assert changed is False
    assert protected == {0}
    assert compacted == messages
    assert compacted[0] is not messages[0]


@pytest.mark.anyio
async def test_session_memory_compacts_old_unprotected_turns(monkeypatch):
    snapshot = SimpleNamespace(summary_text="stored summary", source_message_id=uuid4())

    async def get_snapshot(_conversation_id):
        return snapshot

    async def active_branch(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.services.session_memory.get_ready_session_memory", get_snapshot
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", active_branch)
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old question"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
        Message(role=MessageRole.USER, content="protected question"),
        Message(role=MessageRole.ASSISTANT, content="protected answer"),
        Message(role=MessageRole.USER, content="recent question"),
    ]

    compacted, changed, protected = await chat_context._apply_session_memory_compaction(
        messages,
        conversation=_conversation(),
        model_id="test-model",
        provider=None,
        recent_raw_turns=1,
        protected_indexes={3},
    )

    assert changed is True
    assert [message.content for message in compacted] == [
        "system",
        "stored summary",
        "protected question",
        "protected answer",
        "recent question",
    ]
    assert protected == {1, 2}


@pytest.mark.anyio
@pytest.mark.parametrize("emergency_tokens", [10, 100])
async def test_prepare_model_context_emergency_fallback_boundary(
    monkeypatch, emergency_tokens
):
    built_messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old history"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
        Message(role=MessageRole.USER, content="current question"),
    ]

    async def build_messages(**kwargs):
        return [message.model_copy(deep=True) for message in built_messages], {3}

    async def no_session_memory(messages, *, protected_indexes, **kwargs):
        return list(messages), False, set(protected_indexes)

    def estimate(messages, *, model_id, provider):
        return 100 if len(messages) > 2 else emergency_tokens

    monkeypatch.setattr(
        chat_context, "_build_messages_with_file_content", build_messages
    )
    monkeypatch.setattr(
        chat_context, "_apply_session_memory_compaction", no_session_memory
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)

    call = chat_context.prepare_model_context(
        agent=_agent(
            micro_compaction_enabled=False,
            macro_compaction_enabled=False,
            checkpoint_summary_enabled=False,
        ),
        conversation=_conversation(),
        user_message="current question",
        model_id="test-model",
        model_context_limit=60,
        model_max_output_tokens=10,
        provider="test-provider",
        protected_round_id=uuid4(),
    )

    if emergency_tokens > 50:
        with pytest.raises(ContextLengthError) as error:
            await call
        assert error.value.max_tokens == 50
        assert error.value.actual_tokens == emergency_tokens
        assert error.value.provider == "test-provider"
        return

    prepared = await call
    assert [message.content for message in prepared.messages] == [
        "system",
        "current question",
    ]
    assert prepared.protected_indexes == {1}
    assert prepared.compression.stage == "macro"
    assert prepared.compression.actions == ["emergency_fallback"]
    assert prepared.compression.after_tokens == emergency_tokens


def test_budget_compaction_handles_noop_clone_and_macro_summary(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old"),
        Message(role=MessageRole.USER, content="recent"),
    ]
    budget = chat_context.TokenBudget(100, 0, 0, 100)
    compression = chat_context.CompressionMeta(
        stage="micro",
        before_tokens=120,
        after_tokens=80,
        input_budget=100,
        actions=[],
    )

    cloned, unchanged, protected = chat_context._apply_budget_compaction(
        messages=messages,
        model_id="test-model",
        provider=None,
        token_budget=budget,
        compression=compression,
        file_content_trimmed=False,
        protected_indexes={2},
    )
    assert unchanged is compression
    assert protected == {2}
    assert cloned[0] is not messages[0]

    monkeypatch.setattr(
        chat_context,
        "_apply_macro_compaction",
        lambda *args, **kwargs: (
            [messages[0], messages[-1]],
            1,
            1,
            0,
            1,
            {1},
        ),
    )
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *args, **kwargs: 40
    )
    compression.after_tokens = 120

    compacted, updated, protected = chat_context._apply_budget_compaction(
        messages=messages,
        model_id="test-model",
        provider=None,
        token_budget=budget,
        compression=compression,
        file_content_trimmed=True,
        pressure_level="blocking",
        protected_indexes={2},
    )
    assert compacted == [messages[0], messages[-1]]
    assert protected == {1}
    assert updated.stage == "macro"
    assert updated.after_tokens == 40
    assert updated.file_content_trimmed is True
    assert updated.actions == ["macro_summary"]
