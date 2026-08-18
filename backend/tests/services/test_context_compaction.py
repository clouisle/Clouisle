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
