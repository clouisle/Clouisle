import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.adapters.rerank.factory import create_rerank_adapter
from app.llm.adapters.rerank.llm_adapter import LLMRerankAdapter
from app.llm.adapters.rerank.openai_compatible_adapter import (
    OpenAICompatibleRerankAdapter,
)
from app.llm.manager import ModelManager
from app.llm.errors import ModelNotFoundError
from app.llm.types import ChatResponse, FinishReason, Usage
from app.models.model import ModelProvider, ModelType


def build_adapter() -> LLMRerankAdapter:
    model_config = SimpleNamespace(
        provider="openai",
        model_id="gpt-4o-mini",
        api_key="test-key",
        base_url=None,
        default_params=None,
        config=None,
        max_output_tokens=None,
    )
    return LLMRerankAdapter(model_config, AsyncMock())


class TestLLMRerankAdapter:
    def test_parse_results_extracts_json_and_clamps_scores(self):
        adapter = build_adapter()

        content = """
        Here is the ranking:
        {"results":[
            {"index": 2, "score": 1.5, "reason": "best match"},
            {"index": 2, "score": 0.7, "reason": "duplicate"},
            {"index": -1, "score": 0.2},
            {"index": 1, "score": -0.5, "reason": "weak"}
        ]}
        """

        results = adapter._parse_results(content, document_count=3)

        assert [item.index for item in results] == [2, 1]
        assert results[0].score == 1.0
        assert results[0].reason == "best match"
        assert results[1].score == 0.0

    def test_rerank_fills_missing_documents_and_respects_top_n(self):
        adapter = build_adapter()
        adapter.chat_adapter.chat = AsyncMock(
            return_value=ChatResponse(
                id="resp_1",
                model="gpt-4o-mini",
                content='{"results":[{"index":2,"score":0.9,"reason":"best"}]}',
                finish_reason=FinishReason.STOP,
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )
        )

        response = asyncio.run(
            adapter.rerank(
                query="What is reranking?",
                documents=["doc-a", "doc-b", "doc-c"],
                top_n=2,
            )
        )

        assert [item.index for item in response.results] == [2, 0]
        assert response.results[0].score == 0.9
        assert response.results[0].reason == "best"
        assert response.results[1].score == 0.0
        assert response.usage.total_tokens == 15


class TestOpenAICompatibleRerankAdapter:
    @staticmethod
    def build_adapter(**overrides):
        config = {
            "model_id": "rerank-model",
            "base_url": "https://rerank.example/v1/",
            "api_key": "secret",
            "config": {},
        }
        config.update(overrides)
        return OpenAICompatibleRerankAdapter(SimpleNamespace(**config))

    def test_builds_endpoint_headers_and_payload_with_runtime_precedence(self):
        adapter = self.build_adapter(
            config={
                "instruction": "configured",
                "max_chunks_per_doc": 3,
                "return_documents": True,
            }
        )

        assert adapter._get_endpoint() == "https://rerank.example/v1/rerank"
        assert adapter._build_headers() == {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret",
        }
        assert adapter._build_payload(
            "query",
            ["first", "second"],
            1,
            instruction="runtime",
            overlap_tokens=8,
        ) == {
            "model": "rerank-model",
            "query": "query",
            "documents": ["first", "second"],
            "return_documents": True,
            "top_n": 1,
            "instruction": "runtime",
            "max_chunks_per_doc": 3,
            "overlap_tokens": 8,
        }

    def test_requires_base_url_and_omits_optional_auth_and_top_n(self):
        adapter = self.build_adapter(base_url=None, api_key=None)

        with pytest.raises(ValueError, match="base_url"):
            adapter._get_endpoint()

        assert adapter._build_headers() == {"Content-Type": "application/json"}
        assert "top_n" not in adapter._build_payload("query", ["doc"], None)

    def test_parses_results_and_usage_boundaries(self):
        adapter = self.build_adapter()

        results = adapter._parse_results(
            {
                "results": [
                    {"index": "2", "relevance_score": 1.5},
                    {"index": 1, "score": -0.5},
                    {"index": 0, "score": "invalid"},
                    {"index": None, "score": 0.8},
                    {"index": "invalid", "score": 0.7},
                    "invalid",
                ]
            }
        )

        assert [(item.index, item.score) for item in results] == [
            (2, 1.0),
            (1, 0.0),
            (0, 0.0),
        ]
        assert adapter._parse_usage(
            {"meta": [{"tokens": {"input_tokens": "4", "output_tokens": 2}}]}
        ) == Usage(prompt_tokens=4, completion_tokens=2, total_tokens=6)
        assert adapter._parse_usage({"meta": ["invalid"]}) == Usage()
        assert adapter._parse_usage({"meta": "invalid"}) == Usage()

    def test_rerank_posts_request_and_returns_parsed_response(self):
        adapter = self.build_adapter()
        response = Mock()
        response.json.return_value = {
            "results": [{"index": 0, "relevance_score": 0.75}],
            "tokens": {"input_tokens": 5},
        }
        client = AsyncMock()
        client.post.return_value = response
        context = AsyncMock()
        context.__aenter__.return_value = client

        with patch(
            "app.llm.adapters.rerank.openai_compatible_adapter.httpx.AsyncClient",
            return_value=context,
        ) as client_factory:
            result = asyncio.run(adapter.rerank("query", ["doc"], top_n=1, timeout=9))

        client_factory.assert_called_once_with(timeout=9)
        client.post.assert_awaited_once_with(
            "https://rerank.example/v1/rerank",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer secret",
            },
            json={
                "model": "rerank-model",
                "query": "query",
                "documents": ["doc"],
                "return_documents": False,
                "top_n": 1,
            },
        )
        response.raise_for_status.assert_called_once_with()
        assert [(item.index, item.score) for item in result.results] == [(0, 0.75)]
        assert result.usage == Usage(prompt_tokens=5, total_tokens=5)

    def test_empty_documents_skip_http_request(self):
        adapter = self.build_adapter()

        with patch(
            "app.llm.adapters.rerank.openai_compatible_adapter.httpx.AsyncClient"
        ) as client_factory:
            result = asyncio.run(adapter.rerank("query", []))

        client_factory.assert_not_called()
        assert result.model == "rerank-model"
        assert result.results == []


class TestModelManagerModelLookup:
    def test_get_model_config_filters_by_uuid(self):
        manager = ModelManager()
        model_uuid = "550e8400-e29b-41d4-a716-446655440000"
        fake_model = SimpleNamespace(
            id=model_uuid,
            name="Rerank Model",
            model_type=ModelType.RERANK,
            is_enabled=True,
        )
        query = SimpleNamespace(first=AsyncMock(return_value=fake_model))

        with patch("app.llm.manager.Model.filter", return_value=query) as mock_filter:
            model = asyncio.run(manager._get_model_config(model_uuid, ModelType.RERANK))

        assert model is fake_model
        mock_filter.assert_called_once_with(id=model_uuid, model_type=ModelType.RERANK)

    def test_get_model_config_rejects_uuid_for_mismatched_type(self):
        manager = ModelManager()
        model_uuid = "550e8400-e29b-41d4-a716-446655440000"
        query = SimpleNamespace(first=AsyncMock(return_value=None))

        with patch("app.llm.manager.Model.filter", return_value=query) as mock_filter:
            with pytest.raises(ModelNotFoundError):
                asyncio.run(manager._get_model_config(model_uuid, ModelType.RERANK))

        mock_filter.assert_called_once_with(id=model_uuid, model_type=ModelType.RERANK)


class TestRerankFactory:
    def test_factory_uses_native_adapter_for_siliconflow_host(self):
        model_config = SimpleNamespace(
            provider="openai",
            model_id="netease-youdao/bce-reranker-base_v1",
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
            default_params=None,
            config=None,
            max_output_tokens=None,
        )

        adapter = create_rerank_adapter(model_config)

        assert isinstance(adapter, OpenAICompatibleRerankAdapter)

    def test_factory_uses_native_adapter_for_siliconflow_provider(self):
        model_config = SimpleNamespace(
            provider=ModelProvider.SILICONFLOW,
            model_id="netease-youdao/bce-reranker-base_v1",
            api_key="test-key",
            base_url="https://custom.example/v1",
            default_params=None,
            config=None,
            max_output_tokens=None,
        )

        adapter = create_rerank_adapter(model_config)

        assert isinstance(adapter, OpenAICompatibleRerankAdapter)

    def test_factory_uses_native_adapter_for_explicit_native_flag(self):
        model_config = SimpleNamespace(
            provider="openai",
            model_id="netease-youdao/bce-reranker-base_v1",
            api_key="test-key",
            base_url="https://custom.example/v1",
            default_params=None,
            config={"native_rerank": True},
            max_output_tokens=None,
        )

        adapter = create_rerank_adapter(model_config)

        assert isinstance(adapter, OpenAICompatibleRerankAdapter)

    def test_factory_rejects_untrusted_url_with_siliconflow_substring(self):
        model_config = SimpleNamespace(
            provider="openai",
            model_id="gpt-4o-mini",
            api_key="test-key",
            base_url="https://evil.example/?next=siliconflow.com",
            default_params=None,
            config=None,
            max_output_tokens=None,
        )

        adapter = create_rerank_adapter(model_config)

        assert isinstance(adapter, LLMRerankAdapter)

    def test_factory_selects_google_adapter(self):
        model_config = SimpleNamespace(
            provider=ModelProvider.GOOGLE,
            model_id="gemini-2.0-flash",
            api_key="test-key",
            base_url=None,
            default_params=None,
            config=None,
            max_output_tokens=None,
        )

        with (
            patch("app.llm.adapters.rerank.factory.GeminiAdapter") as chat_adapter,
            patch("app.llm.adapters.rerank.factory.LLMRerankAdapter") as rerank_adapter,
        ):
            adapter = create_rerank_adapter(model_config)

        assert adapter is rerank_adapter.return_value
        chat_adapter.assert_called_once_with(model_config)
        rerank_adapter.assert_called_once_with(model_config, chat_adapter.return_value)

    def test_factory_ignores_non_boolean_native_rerank_config(self):
        model_config = SimpleNamespace(
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o-mini",
            api_key="test-key",
            base_url=None,
            default_params=None,
            config={"native_rerank": "true"},
            max_output_tokens=None,
        )

        with (
            patch("app.llm.adapters.rerank.factory.OpenAIAdapter") as chat_adapter,
            patch("app.llm.adapters.rerank.factory.LLMRerankAdapter") as rerank_adapter,
            patch(
                "app.llm.adapters.rerank.factory.OpenAICompatibleRerankAdapter"
            ) as native_adapter,
        ):
            adapter = create_rerank_adapter(model_config)

        assert adapter is rerank_adapter.return_value
        chat_adapter.assert_called_once_with(model_config)
        rerank_adapter.assert_called_once_with(model_config, chat_adapter.return_value)
        native_adapter.assert_not_called()
