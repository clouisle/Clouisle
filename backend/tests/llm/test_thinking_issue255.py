from types import SimpleNamespace

from app.llm.adapters.chat.thinking import ContentExtractor, ThinkingExtractor


def test_thinking_extractor_uses_first_nonempty_source() -> None:
    assert (
        ThinkingExtractor.extract(
            {"reasoning_content": "   "},
            {"delta": {"reasoning": "  inspect inputs  "}},
            {"thinking": "ignored"},
        )
        == "inspect inputs"
    )


def test_thinking_extractor_returns_none_for_unusable_sources() -> None:
    assert (
        ThinkingExtractor.extract(None, "  ", {"content": [{"type": "text"}]}) is None
    )


def test_thinking_extractor_falls_back_to_object_metadata() -> None:
    source = SimpleNamespace(
        reasoning_content="",
        additional_kwargs={},
        model_extra={"unrelated": True},
        response_metadata={"content": [{"thought": True, "text": "fallback"}]},
    )

    assert ThinkingExtractor.extract(source) == "fallback"


def test_content_extractor_separates_text_thinking_and_ignores_empty_blocks() -> None:
    content = [
        {"type": "text", "text": " answer "},
        {"type": "thinking", "thinking": " reason "},
        SimpleNamespace(type="text", text=" done "),
        SimpleNamespace(is_thought=True, content=" check "),
        {"type": "text", "text": ""},
    ]

    assert ContentExtractor.extract(content) == ("answer  done", "reason  check")


def test_content_extractor_handles_plain_and_unsupported_content() -> None:
    assert ContentExtractor.extract("plain") == ("plain", None)
    assert ContentExtractor.extract({"text": "not a block list"}) == (None, None)
