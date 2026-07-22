from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.llm.adapters.rerank.llm_adapter import LLMRerankAdapter


def adapter(*responses) -> LLMRerankAdapter:
    provider = AsyncMock()
    provider.chat = AsyncMock(side_effect=responses)
    return LLMRerankAdapter(
        SimpleNamespace(provider="mock", model_id="mock-reranker"), provider
    )


def response(content: str | None, usage=None) -> SimpleNamespace:
    return SimpleNamespace(content=content, usage=usage)


@pytest.mark.anyio
async def test_empty_documents_skip_provider() -> None:
    instance = adapter()

    result = await instance.rerank("query", [])

    assert result.results == []
    instance.chat_adapter.chat.assert_not_awaited()


@pytest.mark.anyio
async def test_json_mode_failure_retries_provider_without_response_format() -> None:
    instance = adapter(RuntimeError("unsupported"), response('[{"index": 0}]'))

    result = await instance.rerank("query", ["document"], temperature=0)

    assert result.results[0].index == 0
    assert instance.chat_adapter.chat.await_args_list == [
        call(
            instance._build_messages("query", ["document"]),
            response_format={"type": "json_object"},
            temperature=0,
        ),
        call(instance._build_messages("query", ["document"]), temperature=0),
    ]


@pytest.mark.anyio
async def test_rerank_rejects_empty_or_invalid_provider_output() -> None:
    for content in (None, "not json", "prefix {invalid} suffix"):
        instance = adapter(response(content))
        with pytest.raises(ValueError, match="No valid rerank results"):
            await instance.rerank("query", ["document"])


@pytest.mark.anyio
async def test_rerank_uses_default_usage_and_keeps_all_results_without_top_n() -> None:
    instance = adapter(response('{"results":[{"index":0,"score":0.5}]}'))

    result = await instance.rerank("query", ["first", "second"])

    assert [item.index for item in result.results] == [0, 1]
    assert result.usage.total_tokens == 0


def test_messages_truncate_only_long_documents() -> None:
    instance = adapter()
    long_document = "x" * (instance.MAX_DOCUMENT_CHARS + 1)

    messages = instance._build_messages("needle", ["short", long_document])

    assert "[Document 0]\nshort" in messages[1].content
    assert long_document not in messages[1].content
    assert messages[1].content.endswith("\n...[truncated]")


def test_parse_results_ignores_invalid_items_and_normalizes_fields() -> None:
    instance = adapter()
    results = instance._parse_results(
        """[
            null,
            {},
            {"index": "bad"},
            {"index": null},
            {"index": -1},
            {"index": 3},
            {"index": 0, "score": "bad", "reason": null},
            {"index": 0, "score": 1},
            {"index": 1, "score": 2, "reason": 42},
            {"index": 2, "score": 0.4, "reason": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
        ]""",
        document_count=3,
    )

    assert [(item.index, item.score) for item in results] == [
        (0, 0.0),
        (1, 1.0),
        (2, 0.4),
    ]
    assert results[0].reason is None
    assert results[1].reason == "42"
    assert len(results[2].reason) == 500


def test_extract_json_payload_handles_empty_and_embedded_json() -> None:
    instance = adapter()

    assert instance._extract_json_payload("   ") == {}
    assert instance._extract_json_payload('prefix {"results": []} suffix') == {
        "results": []
    }
    assert instance._parse_results('"scalar"', 1) == []
    assert instance._parse_results("{}", 1) == []
