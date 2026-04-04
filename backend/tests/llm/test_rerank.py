import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.llm.adapters.rerank.factory import create_rerank_adapter
from app.llm.adapters.rerank.llm_adapter import LLMRerankAdapter
from app.llm.adapters.rerank.openai_compatible_adapter import (
    OpenAICompatibleRerankAdapter,
)
from app.llm.manager import ModelManager
from app.llm.types import ChatResponse, FinishReason, Usage
from app.models.model import ModelType


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


class TestModelManagerModelLookup:
    def test_get_model_config_filters_handle_by_model_type(self):
        manager = ModelManager()
        fake_model = SimpleNamespace(
            id="model-1",
            name="Rerank Model",
            is_enabled=True,
        )
        query = SimpleNamespace(first=AsyncMock(return_value=fake_model))

        with patch("app.llm.manager.Model.filter", return_value=query) as mock_filter:
            model = asyncio.run(
                manager._get_model_config("openai/gpt-4o-mini", ModelType.RERANK)
            )

        assert model is fake_model
        mock_filter.assert_called_once_with(
            provider="openai",
            model_id="gpt-4o-mini",
            model_type=ModelType.RERANK,
        )


class TestRerankFactory:
    def test_factory_uses_native_adapter_for_siliconflow(self):
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
