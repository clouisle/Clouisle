from types import SimpleNamespace

import pytest

from app.llm.adapters.chat.thinking import ContentExtractor, ThinkingExtractor


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        ((None, "  ", " reasoning "), "reasoning"),
        (
            ([{"type": "thinking", "thinking": "a"}, {"thought": True, "text": "b"}],),
            "ab",
        ),
        (
            (
                [
                    {"type": "reasoning", "content": "c"},
                    {"is_thought": True, "content": "d"},
                ],
            ),
            "cd",
        ),
        (
            (
                [
                    SimpleNamespace(type="analysis", text="e"),
                    SimpleNamespace(type="text", thought=True, content="f"),
                ],
            ),
            "ef",
        ),
        (([SimpleNamespace(type="text", is_thought=True, text="g"), object()],), "g"),
        (({"reasoning_content": "direct"},), "direct"),
        (({"reasoning": "", "delta": {"thinking": "nested"}},), "nested"),
        (({"content": [{"type": "thought", "text": "block"}]},), "block"),
        ((SimpleNamespace(thinking_content="attribute"),), "attribute"),
        (
            (SimpleNamespace(additional_kwargs={"analysis": "additional"}),),
            "additional",
        ),
        ((SimpleNamespace(model_extra={"cot": "extra"}),), "extra"),
        ((SimpleNamespace(response_metadata={"thoughts": "metadata"}),), "metadata"),
        (({"delta": {"reasoning": ""}, "content": []},), None),
        (
            (
                SimpleNamespace(
                    reasoning_content="",
                    additional_kwargs={"analysis": ""},
                    model_extra={"cot": ""},
                    response_metadata={"thoughts": ""},
                ),
            ),
            None,
        ),
        (({"content": "ordinary"}, SimpleNamespace()), None),
    ],
)
def test_thinking_extractor_sources(sources, expected):
    assert ThinkingExtractor.extract(*sources) == expected


def test_thinking_extractor_ignores_empty_and_non_thinking_blocks():
    blocks = [
        {"type": "thinking", "text": ""},
        {"thought": True},
        {"type": "text", "text": "answer"},
        SimpleNamespace(type="thinking", text=""),
        SimpleNamespace(type="text", thought=True),
        SimpleNamespace(type="text", text="answer"),
    ]

    assert ThinkingExtractor.extract(blocks) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (("answer"), ("answer", None)),
        ((None), (None, None)),
        (
            (
                [
                    {"type": "text", "text": " answer "},
                    {"type": "thinking", "thinking": " think "},
                    {"thought": True, "content": "more"},
                    {"is_thought": True, "text": "deep"},
                    {"type": "text", "text": ""},
                ]
            ),
            ("answer", "think moredeep"),
        ),
        (
            (
                [
                    SimpleNamespace(type="text", content="plain"),
                    SimpleNamespace(type="reasoning", thinking="reason"),
                    SimpleNamespace(type="text", thought=True, text="thought"),
                    SimpleNamespace(type="text", is_thought=True, content="marked"),
                    object(),
                ]
            ),
            ("plain", "reasonthoughtmarked"),
        ),
        (([]), (None, None)),
    ],
)
def test_content_extractor(content, expected):
    assert ContentExtractor.extract(content) == expected
