from uuid import uuid4

from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.services.chat_context import _compact_completed_tool_results


def test_compaction_keeps_tool_protocol_and_raw_results():
    round_id = uuid4()
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="request"),
    ]
    meta = [{}, {}]
    for index in range(3):
        call = ToolCall(
            id=f"call-{index}", function=FunctionCall(name="web_search", arguments="{}")
        )
        messages.extend(
            [
                Message(role=MessageRole.ASSISTANT, tool_calls=[call]),
                Message(
                    role=MessageRole.TOOL,
                    name="web_search",
                    tool_call_id=call.id,
                    content="long result " * 1000,
                ),
            ]
        )
        meta.extend([{"round_id": round_id}, {"round_id": round_id}])
    original = messages[3].content
    reduced, changed = _compact_completed_tool_results(
        messages,
        meta,
        budget=5000,
        hard_budget=5000,
        tool_definition_tokens=0,
        current_user_index=1,
        model_id=None,
        provider=None,
    )
    assert changed
    assert f"tr1:{round_id}:call-0" in reduced[3].content
    assert messages[3].content == original
    assert reduced[2].tool_calls[0].id == reduced[3].tool_call_id
    assert reduced[-1].content == messages[-1].content


def test_incomplete_parallel_tool_group_is_never_compacted():
    round_id = uuid4()
    calls = [
        ToolCall(id=name, function=FunctionCall(name="tool", arguments="{}"))
        for name in ("a", "b")
    ]
    messages = [
        Message(role=MessageRole.USER, content="request"),
        Message(role=MessageRole.ASSISTANT, tool_calls=calls),
        Message(
            role=MessageRole.TOOL,
            name="tool",
            tool_call_id="a",
            content="large " * 2000,
        ),
    ]
    reduced, changed = _compact_completed_tool_results(
        messages,
        [{}, {"round_id": round_id}, {"round_id": round_id}],
        budget=1,
        hard_budget=1,
        tool_definition_tokens=0,
        current_user_index=0,
        model_id=None,
        provider=None,
    )
    assert not changed
    assert reduced[2].content == messages[2].content


def test_multimodal_view_is_preserved_under_pressure():
    round_id = uuid4()
    call = ToolCall(id="view", function=FunctionCall(name="view_asset", arguments="{}"))
    messages = [
        Message(role=MessageRole.USER, content="describe image"),
        Message(role=MessageRole.ASSISTANT, tool_calls=[call]),
        Message(
            role=MessageRole.TOOL,
            name="view_asset",
            tool_call_id="view",
            content="asset " * 1000,
        ),
    ]
    reduced, changed = _compact_completed_tool_results(
        messages,
        [{}, {"round_id": round_id}, {"round_id": round_id}],
        budget=1,
        hard_budget=1,
        tool_definition_tokens=0,
        current_user_index=0,
        model_id=None,
        provider=None,
    )
    assert not changed
    assert reduced[-1].content == messages[-1].content


def test_hard_budget_allows_compacting_latest_complete_exchange():
    round_id = uuid4()
    call = ToolCall(id="one", function=FunctionCall(name="web_search", arguments="{}"))
    messages = [
        Message(role=MessageRole.USER, content="request"),
        Message(role=MessageRole.ASSISTANT, tool_calls=[call]),
        Message(
            role=MessageRole.TOOL,
            name="web_search",
            tool_call_id="one",
            content="large result " * 1000,
        ),
    ]
    reduced, changed = _compact_completed_tool_results(
        messages,
        [{}, {"round_id": round_id}, {"round_id": round_id}],
        budget=500,
        hard_budget=1000,
        tool_definition_tokens=0,
        current_user_index=0,
        model_id=None,
        provider=None,
    )
    assert changed
    assert f"tr1:{round_id}:one" in reduced[-1].content
    assert messages[-1].content != reduced[-1].content
