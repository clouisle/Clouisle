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


def create_embedding_model(model_config: Model | ModelConfig) -> Embeddings:
    """
    根据模型配置创建 LangChain Embedding 模型实例

    Args:
        model_config: 数据库中的模型配置或临时配置对象

    Returns:
        Embeddings: LangChain Embedding 模型实例
    """
    provider = model_config.provider
    model_id = model_config.model_id
    api_key = SecretStr(model_config.api_key) if model_config.api_key else None
    base_url = model_config.base_url

    if provider == ModelProvider.OPENAI:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model_id,
            api_key=api_key,
            base_url=base_url,
        )

    elif provider == ModelProvider.AZURE_OPENAI:
        from langchain_openai import AzureOpenAIEmbeddings

        config = model_config.config or {}
        azure_config = config.get("azure", {})
        return AzureOpenAIEmbeddings(
            azure_deployment=model_id,
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=azure_config.get("api_version", "2024-02-01"),
        )

    elif provider == ModelProvider.GOOGLE:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not api_key:
            raise ValueError("Google requires api_key")

        return GoogleGenerativeAIEmbeddings(
            model=model_id,
            api_key=api_key,
        )

    elif provider in [
        ModelProvider.DEEPSEEK,
        ModelProvider.MOONSHOT,
        ModelProvider.ZHIPU,
        ModelProvider.QWEN,
        ModelProvider.BAICHUAN,
        ModelProvider.MINIMAX,
        ModelProvider.XAI,
        ModelProvider.OLLAMA,
        ModelProvider.CUSTOM,
    ]:
        from langchain_openai import OpenAIEmbeddings

        # 这些供应商一般兼容 OpenAI API
        provider_base_urls: dict[ModelProvider, str] = {
            ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
            ModelProvider.MOONSHOT: "https://api.moonshot.cn/v1",
            ModelProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
            ModelProvider.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ModelProvider.BAICHUAN: "https://api.baichuan-ai.com/v1",
            ModelProvider.MINIMAX: "https://api.minimax.chat/v1",
            ModelProvider.XAI: "https://api.x.ai/v1",
            ModelProvider.OLLAMA: "http://localhost:11434/v1",
        }
        # 获取 provider 的 base_url
        provider_enum = (
            ModelProvider(provider) if isinstance(provider, str) else provider
        )
        final_base_url = base_url or provider_base_urls.get(provider_enum)

        # 禁用 tokenization，因为某些 API 不支持 tokenized 输入
        # check_embedding_ctx_length=False 防止 LangChain 对输入进行 tokenize
        return OpenAIEmbeddings(
            model=model_id,
            api_key=api_key or SecretStr("ollama"),
            base_url=final_base_url,
            check_embedding_ctx_length=False,
        )

    else:
        raise ValueError(f"Unsupported provider for embedding: {provider}")
