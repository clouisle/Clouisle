"""
Tests for embedding adapters and usage metering
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.embedding import (
    OpenAICompatibleEmbeddingAdapter,
    create_embedding_adapter,
)
from app.llm.types import EmbeddingResponse
from app.models.model import ModelProvider


@pytest.mark.asyncio
async def test_openai_compatible_embedding_adapter_captures_usage(monkeypatch):
    config = SimpleNamespace(
        provider=ModelProvider.OPENAI,
        model_id="text-embedding-3-small",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        config={},
    )
    adapter = create_embedding_adapter(config)
    assert isinstance(adapter, OpenAICompatibleEmbeddingAdapter)

    fake_response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2]},
                {"index": 1, "embedding": [0.3, 0.4]},
            ],
            "usage": {"prompt_tokens": 10, "total_tokens": 10},
        },
    )

    client_instance = AsyncMock()
    client_instance.post = AsyncMock(return_value=fake_response)
    client_instance.__aenter__.return_value = client_instance
    client_instance.__aexit__.return_value = None

    with patch(
        "app.llm.adapters.embedding.adapter.httpx.AsyncClient",
        return_value=client_instance,
    ):
        result = await adapter.embed(["hello", "world"])

    assert isinstance(result, EmbeddingResponse)
    assert result.embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert result.usage.total_tokens == 10
    assert result.usage.prompt_tokens == 10


@pytest.mark.asyncio
async def test_openai_compatible_embedding_adapter_falls_back_on_error(monkeypatch):
    config = SimpleNamespace(
        provider=ModelProvider.OPENAI,
        model_id="text-embedding-3-small",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        config={},
    )
    adapter = create_embedding_adapter(config)

    client_instance = AsyncMock()
    client_instance.post = AsyncMock(side_effect=RuntimeError("network error"))
    client_instance.__aenter__.return_value = client_instance
    client_instance.__aexit__.return_value = None

    fake_lc_model = SimpleNamespace(
        aembed_documents=AsyncMock(return_value=[[0.5, 0.6]])
    )

    with (
        patch(
            "app.llm.adapters.embedding.adapter.httpx.AsyncClient",
            return_value=client_instance,
        ),
        patch(
            "app.llm.adapters.embedding.adapter.create_embedding_model",
            return_value=fake_lc_model,
        ),
    ):
        result = await adapter.embed(["fallback"])

    assert result.embeddings == [[0.5, 0.6]]
    assert result.usage.total_tokens == 0


@pytest.mark.asyncio
async def test_fallback_embedding_adapter_for_other_providers(monkeypatch):
    config = SimpleNamespace(
        provider="other",
        model_id="other-embed",
        api_key=None,
        base_url=None,
        config={},
    )
    adapter = create_embedding_adapter(config)
    assert not isinstance(adapter, OpenAICompatibleEmbeddingAdapter)

    fake_lc_model = SimpleNamespace(
        aembed_documents=AsyncMock(return_value=[[0.7, 0.8]])
    )

    with patch(
        "app.llm.adapters.embedding.adapter.create_embedding_model",
        return_value=fake_lc_model,
    ):
        result = await adapter.embed(["test"])

    assert result.embeddings == [[0.7, 0.8]]
    assert result.usage.total_tokens == 0
