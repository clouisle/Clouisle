from unittest.mock import Mock

from app.llm import token_counter


class Encoding:
    def encode(self, text):
        return list(text)


def test_get_encoding_caches_tiktoken_lookup(monkeypatch):
    get_encoding = Mock(return_value=Encoding())
    token_counter.get_encoding.cache_clear()
    monkeypatch.setattr(token_counter.tiktoken, "get_encoding", get_encoding)

    assert token_counter.get_encoding("test") is token_counter.get_encoding("test")
    get_encoding.assert_called_once_with("test")


def test_get_encoding_for_model_prefers_model_then_provider_defaults(monkeypatch):
    get_encoding = Mock(return_value=Encoding())
    monkeypatch.setattr(token_counter, "get_encoding", get_encoding)

    assert token_counter.get_encoding_for_model("text-embedding-3-small")
    get_encoding.assert_called_once_with("cl100k_base")

    get_encoding.reset_mock()
    assert token_counter.get_encoding_for_model("unknown", "openai")
    get_encoding.assert_called_once_with("cl100k_base")

    get_encoding.reset_mock()
    assert token_counter.get_encoding_for_model("unknown")
    get_encoding.assert_called_once_with("cl100k_base")


def test_count_tokens_handles_empty_text_and_encoding_failure(monkeypatch):
    monkeypatch.setattr(
        token_counter, "get_encoding_for_model", Mock(side_effect=RuntimeError)
    )

    assert token_counter.count_tokens("") == 0
    assert token_counter.count_tokens("abcde") == 1
    assert token_counter.count_tokens("abcdefghi") == 2
    assert token_counter.estimate_tokens_from_chars(8) == 2
    assert token_counter.estimate_tokens_from_chars(0) == 1


def test_count_message_tokens_handles_text_names_and_vision_content(monkeypatch):
    monkeypatch.setattr(
        token_counter, "get_encoding_for_model", Mock(return_value=Encoding())
    )

    result = token_counter.count_message_tokens(
        [
            {"role": "user", "content": "hi", "name": "alice", "ignored": None},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "go"}, {"type": "image"}],
            },
        ]
    )

    assert result == 32


def test_count_message_tokens_falls_back_to_text_content(monkeypatch):
    monkeypatch.setattr(
        token_counter, "get_encoding_for_model", Mock(side_effect=RuntimeError)
    )

    assert (
        token_counter.count_message_tokens(
            [{"content": "abcd"}, {"content": [{"type": "text", "text": "ef"}]}]
        )
        == 1
    )
