from unittest.mock import Mock, call, patch

import pytest
import tiktoken

from app.llm import token_counter
from app.llm.types.chat import FunctionDefinition, ToolDefinition


def encoded_length(encoding: tiktoken.Encoding, *values: str) -> int:
    return sum(len(encoding.encode(value)) for value in values)


def test_serialize_tool_calls_accepts_mapping_values() -> None:
    assert (
        token_counter.serialize_tool_calls(
            [{"id": "call-1", "function": {"name": "lookup", "arguments": "{}"}}]
        )
        == '[{"id":"call-1","function":{"name":"lookup","arguments":"{}"}}]'
    )


def test_count_tokens_uses_real_model_encoding() -> None:
    assert token_counter.count_tokens("hello world", model_id="GPT-4o-mini-2024") == 2
    assert token_counter.count_tokens("你好，世界", model_id="gpt-4") > 0


def test_empty_text_skips_tokenizer_lookup() -> None:
    with patch.object(token_counter, "get_encoding_for_model") as get_encoding:
        assert token_counter.count_tokens("") == 0
        assert token_counter.count_tokens(None) == 0  # type: ignore[arg-type]

    get_encoding.assert_not_called()


@pytest.mark.parametrize(
    ("model_id", "provider", "encoding_name"),
    [
        ("GPT-4o-mini-2024-07-18", None, "o200k_base"),
        ("gpt-4-turbo-preview", "anthropic", "cl100k_base"),
        ("unknown-model", "AZURE", "cl100k_base"),
        ("unknown-model", "unknown-provider", "cl100k_base"),
        ("unknown-model", None, "cl100k_base"),
    ],
)
def test_encoding_selection_prefers_model_then_provider_then_default(
    model_id: str, provider: str | None, encoding_name: str
) -> None:
    sentinel = Mock()
    with patch.object(
        token_counter, "get_encoding", return_value=sentinel
    ) as get_encoding:
        assert token_counter.get_encoding_for_model(model_id, provider) is sentinel

    get_encoding.assert_called_once_with(encoding_name)


def test_get_encoding_caches_tokenizer_boundary() -> None:
    token_counter.get_encoding.cache_clear()
    sentinel = Mock()
    with patch.object(
        tiktoken, "get_encoding", return_value=sentinel
    ) as provider_lookup:
        assert token_counter.get_encoding("cl100k_base") is sentinel
        assert token_counter.get_encoding("cl100k_base") is sentinel

    provider_lookup.assert_called_once_with("cl100k_base")
    token_counter.get_encoding.cache_clear()


def test_message_count_covers_text_media_names_and_tool_structures() -> None:
    encoding = tiktoken.get_encoding("cl100k_base")
    messages = [
        {"role": "system", "content": "Follow instructions."},
        {
            "role": "user",
            "name": "alice",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
                {"type": "text"},
                "ignored non-dict content",
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "weather", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": "sunny",
            "metadata": {"ignored": True},
        },
    ]
    tool_call_tokens = encoded_length(
        encoding, token_counter.serialize_tool_calls(messages[2]["tool_calls"])
    )
    expected = (
        3 * len(messages)
        + 3
        + 1
        + tool_call_tokens
        + encoded_length(
            encoding,
            "system",
            "Follow instructions.",
            "user",
            "alice",
            "Describe this image",
            "",
            "assistant",
            "tool",
            "call-1",
            "sunny",
        )
    )

    assert (
        token_counter.count_message_tokens(messages, include_tool_calls=True)
        == expected
    )
    assert token_counter.count_message_tokens(messages) == expected - tool_call_tokens


def test_tool_definition_count_serializes_pydantic_schema() -> None:
    tool = ToolDefinition(
        function=FunctionDefinition(
            name="lookup",
            description="Find information",
            parameters={"type": "object"},
        )
    )
    serialized = token_counter.serialize_tool_calls([tool])

    assert token_counter.count_tool_definition_tokens(
        [tool]
    ) == token_counter.count_tokens(serialized)
    assert token_counter.count_tool_definition_tokens([]) == 0


def test_message_count_handles_empty_and_sparse_messages() -> None:
    encoding = tiktoken.get_encoding("cl100k_base")

    assert token_counter.count_message_tokens([]) == 3
    assert token_counter.count_message_tokens([{}]) == 6
    assert token_counter.count_message_tokens(
        [{"role": "user", "content": [None, 7, {}, {"type": "image_url"}]}]
    ) == 6 + len(encoding.encode("user"))


def test_count_tokens_logs_and_estimates_when_tokenizer_fails(caplog) -> None:
    with patch.object(
        token_counter, "get_encoding_for_model", side_effect=ValueError("bad encoding")
    ):
        assert token_counter.count_tokens("abcdefghij") == 2
        assert token_counter.count_tokens("x") == 1

    assert caplog.messages == [
        "Token counting failed, using fallback: bad encoding",
        "Token counting failed, using fallback: bad encoding",
    ]


def test_message_fallback_counts_tool_calls_when_requested() -> None:
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        }
    ]
    serialized = token_counter.serialize_tool_calls(messages[0]["tool_calls"])

    with patch.object(
        token_counter, "get_encoding_for_model", side_effect=RuntimeError("offline")
    ):
        assert token_counter.count_message_tokens(
            messages, include_tool_calls=True
        ) == max(len(serialized) // 4, 1)


def test_message_fallback_extracts_only_text_content(caplog) -> None:
    messages = [
        {"role": "user", "content": "12345678"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "abcd"},
                {"type": "image_url", "image_url": {"url": "ignored"}},
                None,
            ],
        },
        {"role": "assistant", "content": None},
        {"role": "tool"},
    ]
    with patch.object(
        token_counter, "get_encoding_for_model", side_effect=RuntimeError("offline")
    ):
        assert token_counter.count_message_tokens(messages) == 3

    assert caplog.messages == ["Message token counting failed, using fallback: offline"]


def test_message_encoding_failure_falls_back_after_partial_work() -> None:
    encoding = Mock()
    encoding.encode.side_effect = [[], ValueError("invalid content")]
    messages = [{"role": "user", "content": "abcdefgh"}]

    with patch.object(token_counter, "get_encoding_for_model", return_value=encoding):
        assert token_counter.count_message_tokens(messages) == 2

    assert encoding.encode.call_args_list == [call("user"), call("abcdefgh")]


@pytest.mark.parametrize(
    ("char_count", "expected"),
    [(-8, 1), (0, 1), (3, 1), (4, 1), (9, 2)],
)
def test_character_estimation_has_one_token_floor(
    char_count: int, expected: int
) -> None:
    assert token_counter.estimate_tokens_from_chars(char_count) == expected
