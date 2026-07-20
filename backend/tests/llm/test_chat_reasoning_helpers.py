from types import SimpleNamespace

from app.llm.adapters.chat.thinking import ContentExtractor, ThinkingExtractor
from app.llm.adapters.chat.tool_call_accumulator import (
    ToolCallAccumulator,
    extract_tool_calls_from_content,
)


def test_thinking_and_content_extractors_handle_provider_blocks_and_metadata():
    response = SimpleNamespace(
        additional_kwargs={"reasoning_content": "  metadata reasoning  "}
    )

    assert ThinkingExtractor.extract("  ", response) == "metadata reasoning"
    assert (
        ThinkingExtractor.extract(
            [
                {"type": "thinking", "thinking": "first "},
                {"thought": True, "text": "second"},
            ]
        )
        == "first second"
    )
    assert ContentExtractor.extract(
        [
            {"type": "text", "text": "Answer "},
            {"type": "analysis", "content": "reasoning "},
            {"thought": True, "text": "continued"},
            {"type": "text", "text": "done"},
        ]
    ) == ("Answer done", "reasoning continued")


def test_tool_call_accumulator_combines_interleaved_stream_deltas():
    accumulator = ToolCallAccumulator()

    accumulator.accumulate(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    index=0,
                    id="call-weather",
                    type="function",
                    function=SimpleNamespace(name="get_", arguments='{"city":'),
                ),
                SimpleNamespace(
                    index=1,
                    id="call-time",
                    function=SimpleNamespace(name="get_", arguments='{"zone":'),
                ),
            ]
        )
    )
    accumulator.accumulate(
        SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    index=0,
                    function=SimpleNamespace(name="weather", arguments='"Paris"}'),
                ),
                SimpleNamespace(
                    index=1,
                    function=SimpleNamespace(name="time", arguments='"UTC"}'),
                ),
            ]
        )
    )

    calls = accumulator.finalize()

    assert [
        (call.id, call.function.name, call.function.arguments) for call in calls
    ] == [
        ("call-weather", "get_weather", '{"city":"Paris"}'),
        ("call-time", "get_time", '{"zone":"UTC"}'),
    ]
    assert accumulator.has_tool_calls()
    accumulator.clear()
    assert not accumulator.has_tool_calls()


def test_tool_call_helpers_support_dict_deltas_and_anthropic_blocks():
    accumulator = ToolCallAccumulator()
    accumulator.accumulate_dict(
        [
            {
                "index": 0,
                "id": "call-search",
                "function": {"name": "search", "arguments": ""},
            },
            {"index": 0, "function": {"arguments": '{"query":"docs"}'}},
        ]
    )

    call = accumulator.finalize()[0]
    assert (call.id, call.function.name, call.function.arguments) == (
        "call-search",
        "search",
        '{"query":"docs"}',
    )

    calls = extract_tool_calls_from_content(
        [
            {"type": "text", "text": "ignored"},
            {
                "type": "tool_use",
                "id": "dict-call",
                "name": "lookup",
                "input": {"id": 1},
            },
            SimpleNamespace(
                type="tool_use", id="object-call", name="read", input='{"path": "a"}'
            ),
        ]
    )

    assert [
        (item.id, item.function.name, item.function.arguments) for item in calls
    ] == [
        ("dict-call", "lookup", '{"id": 1}'),
        ("object-call", "read", '{"path": "a"}'),
    ]
    assert extract_tool_calls_from_content("not content blocks") is None
