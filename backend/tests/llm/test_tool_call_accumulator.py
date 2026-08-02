"""Tests for streamed tool-call assembly helpers."""

from types import SimpleNamespace

from app.llm.adapters.chat.tool_call_accumulator import (
    ToolCallAccumulator,
    extract_tool_calls_from_content,
)


def test_accumulate_assembles_indexed_object_deltas_and_clears():
    accumulator = ToolCallAccumulator()

    assert accumulator.accumulate(SimpleNamespace(tool_calls=None)) == []
    starts = accumulator.accumulate(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    index=1,
                    id="call_1",
                    type="function",
                    function=SimpleNamespace(name="search", arguments='{"q":'),
                ),
                SimpleNamespace(
                    index=0,
                    id=None,
                    type=None,
                    function=SimpleNamespace(name="weather", arguments=""),
                ),
            ]
        )
    )
    assert [
        (call.id, call.function.name, call.function.arguments) for call in starts
    ] == [("call_1", "search", "{}")]
    updates = accumulator.accumulate(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    index=1,
                    id=None,
                    type=None,
                    function=SimpleNamespace(name="_docs", arguments='"python"}'),
                )
            ]
        )
    )
    assert [
        (call.id, call.function.name, call.function.arguments) for call in updates
    ] == [("call_1", "search_docs", "{}")]

    calls = accumulator.finalize()

    assert [
        (call.id, call.function.name, call.function.arguments) for call in calls
    ] == [
        ("call_1", "search_docs", '{"q":"python"}'),
        (calls[1].id, "weather", "{}"),
    ]
    assert accumulator.has_tool_calls() is True
    accumulator.clear()
    assert accumulator.has_tool_calls() is False
    assert accumulator.finalize() == []


def test_accumulate_dict_assembles_arguments_and_metadata():
    accumulator = ToolCallAccumulator()

    starts = accumulator.accumulate_dict(
        [
            {
                "index": 0,
                "id": "call_2",
                "type": "custom",
                "function": {"name": "get_", "arguments": '{"id":'},
            },
            {"index": 0, "function": {"name": "user", "arguments": "42}"}},
        ]
    )
    assert [
        (item.id, item.function.name, item.function.arguments) for item in starts
    ] == [("call_2", "get_user", "{}")]
    assert accumulator.accumulate_dict([{"index": 0, "function": {}}]) == []

    call = accumulator.finalize()[0]

    assert call.id == "call_2"
    assert call.type == "custom"
    assert call.function.name == "get_user"
    assert call.function.arguments == '{"id":42}'


def test_extract_tool_calls_handles_dict_object_and_non_tool_content():
    object_block = SimpleNamespace(
        type="tool_use", id=None, name="object_tool", input={"x": 1}
    )

    calls = extract_tool_calls_from_content(
        [
            {"type": "text", "text": "ignored"},
            {"type": "tool_use", "id": "call_3", "name": "dict_tool", "input": "{}"},
            object_block,
        ]
    )

    assert calls is not None
    assert [
        (call.id, call.function.name, call.function.arguments) for call in calls
    ] == [
        ("call_3", "dict_tool", "{}"),
        (calls[1].id, "object_tool", '{"x": 1}'),
    ]
    assert (
        extract_tool_calls_from_content({"type": "tool_use", "name": "empty"})[
            0
        ].function.arguments
        == "{}"
    )
    assert extract_tool_calls_from_content("not content blocks") is None
    assert extract_tool_calls_from_content([{"type": "text"}]) is None
