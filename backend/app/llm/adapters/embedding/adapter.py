"""
Embedding 适配器基础类与 OpenAI 兼容实现
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.llm.types import EmbeddingResponse, Usage
from app.models.model import ModelProvider
from .factory import (
    DEFAULT_EMBEDDING_REQUEST_TIMEOUT,
    OPENAI_COMPATIBLE_PROVIDER_BASE_URLS,
    create_embedding_model,
)

logger = logging.getLogger(__name__)


class BaseEmbeddingAdapter(ABC):
    """Embedding 适配器基类"""

    def __init__(self, model_config: Any):
        self.model_config = model_config
        self.provider = model_config.provider
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.base_url = model_config.base_url
        self.config = model_config.config or {}

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        """生成文本嵌入向量并返回使用统计"""
        pass


class OpenAICompatibleEmbeddingAdapter(BaseEmbeddingAdapter):
    """OpenAI 及兼容协议的 Embedding 适配器（捕获上游 usage.total_tokens）"""

    def _get_base_url(self) -> str:
        if self.base_url and self.base_url.strip():
            return self.base_url.strip()

        try:
            provider_enum = (
                ModelProvider(self.provider)
                if isinstance(self.provider, str)
                else self.provider
            )
        except ValueError:
            provider_enum = None

        if provider_enum and provider_enum in OPENAI_COMPATIBLE_PROVIDER_BASE_URLS:
            return OPENAI_COMPATIBLE_PROVIDER_BASE_URLS[provider_enum]

        return "https://api.openai.com/v1"

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        if not texts:
            return EmbeddingResponse(model=self.model_id, embeddings=[], usage=Usage())

        # 尝试通过标准 OpenAI / 兼容端点读取 usage
        base_url = self._get_base_url()
        endpoint = f"{base_url.rstrip('/')}/embeddings"
        api_key = self.api_key or "ollama"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": texts,
        }

        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_EMBEDDING_REQUEST_TIMEOUT
            ) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    raw_items = data.get("data", [])
                    sorted_items = sorted(
                        raw_items, key=lambda item: item.get("index", 0)
                    )
                    expected_indexes = list(range(len(texts)))
                    actual_indexes = [item.get("index") for item in sorted_items]
                    if actual_indexes != expected_indexes:
                        raise ValueError(
                            "Embedding response does not match the input cardinality"
                        )
                    embeddings = [item["embedding"] for item in sorted_items]

                    raw_usage = data.get("usage") or {}
                    prompt_tokens = raw_usage.get("prompt_tokens") or raw_usage.get(
                        "total_tokens", 0
                    )
                    total_tokens = raw_usage.get("total_tokens") or prompt_tokens

                    usage = Usage(
                        prompt_tokens=prompt_tokens,
                        total_tokens=total_tokens,
                    )
                    return EmbeddingResponse(
                        model=self.model_id,
                        embeddings=embeddings,
                        usage=usage,
                    )
        except Exception as exc:
            logger.debug(
                "Direct embedding call failed for %s, falling back to LangChain Embeddings: %s",
                self.model_id,
                exc,
            )

        # 降级到 LangChain 实例（usage 为空由外层 fallback 到 tiktoken）
        lc_model = create_embedding_model(self.model_config)
        vectors = await lc_model.aembed_documents(texts)
        return EmbeddingResponse(
            model=self.model_id,
            embeddings=vectors,
            usage=Usage(),
        )


class FallbackEmbeddingAdapter(BaseEmbeddingAdapter):
    """基于 LangChain Embeddings 的通用适配器（例如 Google）"""

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        lc_model = create_embedding_model(self.model_config)
        vectors = await lc_model.aembed_documents(texts)
        return EmbeddingResponse(
            model=self.model_id,
            embeddings=vectors,
            usage=Usage(),
        )


def create_embedding_adapter(model_config: Any) -> BaseEmbeddingAdapter:
    """根据模型配置创建 Embedding 适配器"""
    provider = model_config.provider
    try:
        provider_enum = (
            ModelProvider(provider) if isinstance(provider, str) else provider
        )
    except ValueError:
        provider_enum = None

    if provider_enum in {
        ModelProvider.OPENAI,
        ModelProvider.OPENAI_RESPONSES,
        ModelProvider.DEEPSEEK,
        ModelProvider.MOONSHOT,
        ModelProvider.ZHIPU,
        ModelProvider.QWEN,
        ModelProvider.BAICHUAN,
        ModelProvider.MINIMAX,
        ModelProvider.VOLCENGINE,
        ModelProvider.SILICONFLOW,
        ModelProvider.XAI,
        ModelProvider.OLLAMA,
        ModelProvider.CUSTOM,
    }:
        return OpenAICompatibleEmbeddingAdapter(model_config)

    return FallbackEmbeddingAdapter(model_config)
