"""
Embedding 模型工厂 - 使用 LangChain
"""

import logging
from typing import Any, Protocol

from langchain_core.embeddings import Embeddings
from pydantic import SecretStr

from app.models.model import Model, ModelProvider


class ModelConfig(Protocol):
    """模型配置协议，用于类型检查"""

    provider: str | ModelProvider
    model_id: str
    api_key: str | None
    base_url: str | None
    config: dict[str, Any] | None


logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_REQUEST_TIMEOUT = 60.0
DEFAULT_EMBEDDING_MAX_RETRIES = 2

OPENAI_COMPATIBLE_EMBEDDING_PROVIDERS: set[ModelProvider] = {
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
}

OPENAI_COMPATIBLE_PROVIDER_BASE_URLS: dict[ModelProvider, str] = {
    ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
    ModelProvider.MOONSHOT: "https://api.moonshot.cn/v1",
    ModelProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
    ModelProvider.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ModelProvider.BAICHUAN: "https://api.baichuan-ai.com/v1",
    ModelProvider.MINIMAX: "https://api.minimax.chat/v1",
    ModelProvider.VOLCENGINE: "https://ark.cn-beijing.volces.com/api/v3",
    ModelProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
    ModelProvider.XAI: "https://api.x.ai/v1",
    ModelProvider.OLLAMA: "http://localhost:11434/v1",
}


def create_embedding_model(model_config: Model | ModelConfig) -> Embeddings:
    """
    根据模型配置创建 LangChain Embedding 模型实例

    Args:
        model_config: 数据库中的模型配置或临时配置对象

    Returns:
        Embeddings: LangChain Embedding 模型实例
    """
    provider = model_config.provider
    if isinstance(provider, str):
        try:
            provider_enum = ModelProvider(provider)
        except ValueError:
            provider_enum = None
    else:
        provider_enum = provider

    model_id = model_config.model_id
    api_key = SecretStr(model_config.api_key) if model_config.api_key else None
    base_url = model_config.base_url

    if provider_enum == ModelProvider.OPENAI:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
            check_embedding_ctx_length=False,
            request_timeout=DEFAULT_EMBEDDING_REQUEST_TIMEOUT,
            max_retries=DEFAULT_EMBEDDING_MAX_RETRIES,
        )

    elif provider_enum == ModelProvider.AZURE_OPENAI:
        from langchain_openai import AzureOpenAIEmbeddings

        config = model_config.config or {}
        azure_config = config.get("azure", {})
        return AzureOpenAIEmbeddings(
            azure_deployment=model_id,
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=azure_config.get("api_version", "2024-02-01"),
            check_embedding_ctx_length=False,
            request_timeout=DEFAULT_EMBEDDING_REQUEST_TIMEOUT,
            max_retries=DEFAULT_EMBEDDING_MAX_RETRIES,
        )

    elif provider_enum == ModelProvider.GOOGLE:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not api_key:
            raise ValueError("Google requires api_key")

        return GoogleGenerativeAIEmbeddings(
            model=model_id,
            api_key=api_key,
        )

    elif provider_enum in OPENAI_COMPATIBLE_EMBEDDING_PROVIDERS or (
        provider_enum is None and base_url is not None
    ):
        from langchain_openai import OpenAIEmbeddings

        final_base_url = base_url or (
            OPENAI_COMPATIBLE_PROVIDER_BASE_URLS.get(provider_enum)
            if provider_enum
            else None
        )

        return OpenAIEmbeddings(
            model=model_id,
            api_key=api_key or SecretStr("ollama"),
            base_url=final_base_url,
            check_embedding_ctx_length=False,
            request_timeout=DEFAULT_EMBEDDING_REQUEST_TIMEOUT,
            max_retries=DEFAULT_EMBEDDING_MAX_RETRIES,
        )

    else:
        raise ValueError(f"Unsupported provider for embedding: {provider}")
