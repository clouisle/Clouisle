from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.services import context_compaction


def _iteration(index: int, *, complete: bool = True) -> list[Message]:
    call_id = f"call-{index}"
    assistant = Message(
        role=MessageRole.ASSISTANT,
        content=None,
        tool_calls=[
            ToolCall(
                id=call_id,
                function=FunctionCall(name=f"lookup_{index}", arguments="{}"),
            )
        ],
    )
    if not complete:
        return [assistant]
    return [
        assistant,
        Message(
            role=MessageRole.TOOL,
            content=f"tool-{index} findings " + ("x" * 80),
            tool_call_id=call_id,
        ),
    ]


def _deterministic_message_tokens(messages, *, model_id, provider):
    return sum(
        len(message.content or "") + (10 if message.tool_calls else 0) + 2
        for message in messages
    )


def test_compact_active_tool_messages_summarizes_complete_old_iterations(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="current"),
        *_iteration(1),
        *_iteration(2),
        *_iteration(3),
    ]
    monkeypatch.setattr(
        context_compaction, "_estimate_messages", _deterministic_message_tokens
    )

    result = context_compaction.compact_active_tool_messages(
        messages,
        protected_indexes={1},
        model_id="mock-model",
        provider="mock-provider",
        input_budget=100,
        target_ratio=0.8,
    )

    assert result.changed is True
    assert result.summary_created is True
    assert "active_tool_summary" in result.actions
    assert any(
        message.role == MessageRole.ASSISTANT
        and isinstance(message.content, str)
        and "lookup_1" in message.content
        for message in result.messages
    )
    assert any(
        message.role == MessageRole.ASSISTANT
        and isinstance(message.content, str)
        and "lookup_2" in message.content
        for message in result.messages
    )
    assert any(
        message.role == MessageRole.ASSISTANT
        and message.tool_calls
        and message.tool_calls[0].id == "call-3"
        for message in result.messages
    )
    assert any(
        message.role == MessageRole.TOOL and message.tool_call_id == "call-3"
        for message in result.messages
    )

    for message in result.messages:
        if message.role == MessageRole.ASSISTANT and message.tool_calls:
            call_ids = {call.id for call in message.tool_calls}
            result_ids = {
                candidate.tool_call_id
                for candidate in result.messages
                if candidate.role == MessageRole.TOOL
                and candidate.tool_call_id in call_ids
            }
            assert result_ids == call_ids


def test_compact_active_tool_messages_keeps_incomplete_iteration_raw(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="current"),
        *_iteration(1),
        *_iteration(2),
        *_iteration(3, complete=False),
    ]
    monkeypatch.setattr(
        context_compaction, "_estimate_messages", _deterministic_message_tokens
    )

    result = context_compaction.compact_active_tool_messages(
        messages,
        protected_indexes={1},
        model_id="mock-model",
        provider="mock-provider",
        input_budget=100,
        target_ratio=0.8,
    )

    assert result.summary_created is True
    incomplete = [
        message
        for message in result.messages
        if message.role == MessageRole.ASSISTANT
        and message.tool_calls
        and message.tool_calls[0].id == "call-3"
    ]
    assert len(incomplete) == 1
    assert not any(
        message.role == MessageRole.TOOL and message.tool_call_id == "call-3"
        for message in result.messages
    )


class _CharacterEncoding:
    def encode(self, text):
        return list(text)

    def decode(self, tokens):
        return "".join(tokens)


def test_estimate_messages_serializes_model_messages(monkeypatch):
    captured = {}

    def count(payload, *, model_id, provider):
        captured.update(payload=payload, model_id=model_id, provider=provider)
        return len(payload)

    monkeypatch.setattr(context_compaction, "count_message_tokens", count)

    result = context_compaction._estimate_messages(
        [Message(role=MessageRole.USER, content="hello")],
        model_id="model",
        provider="provider",
    )

    assert result == 1
    assert captured["payload"][0]["role"] == "user"
    assert captured["model_id"] == "model"
    assert captured["provider"] == "provider"


def test_token_helpers_cover_tokenizer_and_fallback_paths(monkeypatch):
    encoding = _CharacterEncoding()
    monkeypatch.setattr(
        context_compaction, "get_encoding_for_model", lambda *_: encoding
    )

    assert context_compaction._token_count("", model_id="m", provider=None) == 0
    assert context_compaction._token_count("abcd", model_id="m", provider=None) == 4
    assert context_compaction.truncate_text_to_tokens(
        "", max_tokens=4, model_id="m", provider=None
    ) == ("", False)
    assert context_compaction.truncate_text_to_tokens(
        "abcd", max_tokens=0, model_id="m", provider=None
    ) == ("", True)
    assert context_compaction.truncate_text_to_tokens(
        "abcd", max_tokens=4, model_id="m", provider=None
    ) == ("abcd", False)
    assert context_compaction.truncate_text_to_tokens(
        "abcdefgh", max_tokens=2, model_id="m", provider=None, marker="|"
    ) == ("ab", True)
    assert context_compaction.truncate_text_to_tokens(
        "abcdefghij", max_tokens=8, model_id="m", provider=None, marker="|"
    ) == ("abcd|hij", True)

    monkeypatch.setattr(
        context_compaction,
        "get_encoding_for_model",
        lambda *_: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert context_compaction._token_count("abcdefgh", model_id="m", provider=None) == 2
    assert context_compaction.truncate_text_to_tokens(
        "abc", max_tokens=2, model_id="m", provider=None
    ) == ("abc", False)
    fallback, changed = context_compaction.truncate_text_to_tokens(
        "abcdefghij", max_tokens=2, model_id="m", provider=None
    )
    assert changed is True
    assert fallback.startswith("a") and fallback.endswith("j")


def test_group_helpers_and_summary_handle_non_tool_and_empty_results(monkeypatch):
    encoding = _CharacterEncoding()
    monkeypatch.setattr(
        context_compaction, "get_encoding_for_model", lambda *_: encoding
    )

    assert context_compaction._group_active_iterations([], 0) == []
    assert (
        context_compaction._group_active_iterations(
            [Message(role=MessageRole.USER, content="user")], 1
        )
        == []
    )
    assert not context_compaction._group_is_complete([])
    assert not context_compaction._group_is_complete(
        [(0, Message(role=MessageRole.USER, content="user"))]
    )

    assistant = _iteration(1, complete=False)[0]
    groups = [
        [(0, assistant), (1, Message(role=MessageRole.USER, content="interleaved"))],
        [
            (2, assistant.model_copy(deep=True)),
            (3, Message(role=MessageRole.TOOL, content="", tool_call_id="call-1")),
        ],
    ]
    summary = context_compaction._summary_for_groups(
        groups, model_id="m", provider=None, max_tokens=100
    )

    assert summary.role == MessageRole.ASSISTANT
    assert "lookup_1" in summary.content
    assert "findings:" not in summary.content


def test_normalize_message_content_bounds_tool_and_reasoning_payloads(monkeypatch):
    encoding = _CharacterEncoding()
    monkeypatch.setattr(
        context_compaction, "get_encoding_for_model", lambda *_: encoding
    )
    messages = [
        Message(role=MessageRole.TOOL, content="tool result"),
        Message(
            role=MessageRole.ASSISTANT,
            content="answer",
            reasoning_content="private reasoning",
        ),
        Message(role=MessageRole.USER, content=None),
    ]

    result = context_compaction.normalize_message_content(
        messages,
        protected_indexes={0},
        model_id="m",
        provider=None,
        max_tool_result_tokens=4,
        max_reasoning_tokens=5,
    )

    assert result.changed is True
    assert result.tool_results_trimmed is True
    assert result.reasoning_trimmed is True
    assert result.actions == ["bound_tool_results", "bound_reasoning"]
    assert result.protected_indexes == {0}
    assert result.messages[0].content != messages[0].content
    assert result.messages[1].reasoning_content != messages[1].reasoning_content
    assert messages[0].content == "tool result"

    unchanged = context_compaction.normalize_message_content(
        [
            Message(role=MessageRole.TOOL, content="ok"),
            Message(
                role=MessageRole.ASSISTANT, content="answer", reasoning_content="ok"
            ),
        ],
        protected_indexes=None,
        model_id="m",
        provider=None,
        max_tool_result_tokens=20,
        max_reasoning_tokens=20,
    )
    assert unchanged.changed is False
    assert unchanged.actions == []


def test_compact_active_tool_messages_handles_no_user_and_single_group(monkeypatch):
    monkeypatch.setattr(
        context_compaction, "_estimate_messages", _deterministic_message_tokens
    )

    no_user = context_compaction.compact_active_tool_messages(
        [Message(role=MessageRole.SYSTEM, content="system")],
        protected_indexes=None,
        model_id="m",
        provider=None,
        input_budget=1,
    )
    assert no_user.changed is False
    assert no_user.messages[0] is not None

    one_group = context_compaction.compact_active_tool_messages(
        [Message(role=MessageRole.USER, content="current"), *_iteration(1)],
        protected_indexes=None,
        model_id="m",
        provider=None,
        input_budget=1,
        max_tool_result_tokens=1_000,
    )
    assert one_group.summary_created is False
    assert one_group.changed is False


def test_compact_active_tool_messages_preserves_protected_kept_group_and_bounds_tools(
    monkeypatch,
):
    monkeypatch.setattr(
        context_compaction, "_estimate_messages", _deterministic_message_tokens
    )
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="current"),
        *_iteration(1),
        *_iteration(2),
        *_iteration(3),
    ]

    result = context_compaction.compact_active_tool_messages(
        messages,
        protected_indexes={1, 6, 7},
        model_id="m",
        provider=None,
        input_budget=50,
        target_ratio=0.8,
        max_tool_result_tokens=3,
    )

    assert result.summary_created is True
    assert result.tool_results_trimmed is True
    assert result.actions == ["bound_tool_results", "active_tool_summary"]
    assert any(
        message.role == MessageRole.TOOL and message.content != original.content
        for message, original in zip(
            [item for item in result.messages if item.role == MessageRole.TOOL],
            [item for item in messages if item.role == MessageRole.TOOL],
        )
    )
    assert result.protected_indexes.issuperset({1, 2, 3, 4})


def test_fit_tool_results_to_budget_covers_early_returns_and_pair_safe_fit(monkeypatch):
    monkeypatch.setattr(
        context_compaction,
        "_estimate_messages",
        lambda messages, **_: sum(
            len(message.content or "") + 2 for message in messages
        ),
    )

    within = context_compaction.fit_tool_results_to_budget(
        [Message(role=MessageRole.USER, content="ok")],
        protected_indexes=None,
        model_id="m",
        provider=None,
        input_budget=100,
    )
    assert within.changed is False

    no_tools = context_compaction.fit_tool_results_to_budget(
        [Message(role=MessageRole.USER, content="too large")],
        protected_indexes={0},
        model_id="m",
        provider=None,
        input_budget=1,
    )
    assert no_tools.changed is False
    assert no_tools.protected_indexes == {0}

    messages = [
        Message(role=MessageRole.USER, content="prefix"),
        Message(role=MessageRole.ASSISTANT, content="calling"),
        Message(role=MessageRole.TOOL, content="abcdefgh", tool_call_id="call-1"),
        Message(role=MessageRole.TOOL, content="ijklmnop", tool_call_id="call-2"),
    ]
    fitted = context_compaction.fit_tool_results_to_budget(
        messages,
        protected_indexes={2},
        model_id="m",
        provider=None,
        input_budget=12,
    )
    assert fitted.changed is True
    assert fitted.actions == ["fit_tool_results_to_budget"]
    assert [
        message.tool_call_id
        for message in fitted.messages
        if message.role == MessageRole.TOOL
    ] == [
        "call-1",
        "call-2",
    ]
    assert all(
        len(message.content) < 8
        for message in fitted.messages
        if message.role == MessageRole.TOOL
    )


def test_compact_active_tool_messages_keeps_all_groups_when_group_budget_fits(
    monkeypatch,
):
    def estimate(messages, **_kwargs):
        # Exercise the defensive no-summary path when aggregate and grouped
        # token estimates disagree because of envelope accounting.
        return 100 if len(messages) > 2 else 0

    monkeypatch.setattr(context_compaction, "_estimate_messages", estimate)
    messages = [
        Message(role=MessageRole.USER, content="current"),
        *_iteration(1),
        *_iteration(2),
    ]

    result = context_compaction.compact_active_tool_messages(
        messages,
        protected_indexes=None,
        model_id="m",
        provider=None,
        input_budget=100,
        target_ratio=0.8,
    )

    assert result.summary_created is False
    assert result.changed is False
    assert len(result.messages) == len(messages)
