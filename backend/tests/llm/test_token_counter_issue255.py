from unittest.mock import Mock

import pytest

from app.llm import token_counter


@pytest.fixture
def encoding(monkeypatch: pytest.MonkeyPatch) -> Mock:
    fake = Mock()
    fake.encode.side_effect = lambda text: list(text)
    monkeypatch.setattr(token_counter, "get_encoding", Mock(return_value=fake))
    return fake


@pytest.mark.parametrize(
    ("model_id", "provider", "expected_name"),
    [
        ("text-embedding-3-small-v1", None, "cl100k_base"),
        ("custom-model", "ANTHROPIC", "cl100k_base"),
        ("custom-model", "unknown", "cl100k_base"),
        ("custom-model", None, "cl100k_base"),
    ],
)
def test_selects_model_provider_and_default_encodings(
    encoding: Mock, model_id: str, provider: str | None, expected_name: str
) -> None:
    assert token_counter.get_encoding_for_model(model_id, provider) is encoding
    token_counter.get_encoding.assert_called_once_with(expected_name)


def test_counts_text_and_uses_character_fallback(
    monkeypatch: pytest.MonkeyPatch, encoding: Mock
) -> None:
    assert token_counter.count_tokens("") == 0
    assert token_counter.count_tokens("hello") == 5

    monkeypatch.setattr(
        token_counter,
        "get_encoding_for_model",
        Mock(side_effect=RuntimeError("unavailable")),
    )
    assert token_counter.count_tokens("abcdefgh") == 2
    assert token_counter.count_tokens("a") == 1


def test_counts_message_fields_text_parts_and_name_overhead(encoding: Mock) -> None:
    messages = [
        {"role": "user", "name": "alice", "content": "hi", "ignored": None},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "answer"},
                {"type": "image_url", "image_url": "ignored"},
                "ignored",
            ],
        },
    ]

    assert token_counter.count_message_tokens(messages) == 36


def test_message_fallback_counts_only_text_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        token_counter,
        "get_encoding_for_model",
        Mock(side_effect=RuntimeError("unavailable")),
    )
    messages = [
        {"content": "abcd"},
        {
            "content": [
                {"type": "text", "text": "efgh"},
                {"type": "image_url"},
                "ignored",
            ]
        },
        {"content": None},
        {},
    ]

    assert token_counter.count_message_tokens(messages) == 2


@pytest.mark.parametrize(("char_count", "expected"), [(0, 1), (3, 1), (8, 2)])
def test_estimates_tokens_from_character_count(char_count: int, expected: int) -> None:
    assert token_counter.estimate_tokens_from_chars(char_count) == expected
