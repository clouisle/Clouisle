"""
Rerank 适配器工厂
"""

from typing import Any, Protocol

from app.models.model import Model, ModelProvider
from app.llm.adapters.chat import (
    AnthropicAdapter,
    DeepSeekAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    OpenAICompatibleAdapter,
    XAIAdapter,
)

from .base import BaseRerankAdapter
from .llm_adapter import LLMRerankAdapter
from .openai_compatible_adapter import OpenAICompatibleRerankAdapter


class ModelConfig(Protocol):
    provider: str | ModelProvider
    model_id: str
    api_key: str | None
    base_url: str | None
    default_params: dict[str, Any] | None
    config: dict[str, Any] | None
    max_output_tokens: int | None


def _should_use_native_openai_compatible_rerank(
    model_config: Model | ModelConfig,
) -> bool:
    config = getattr(model_config, "config", None) or {}
    if config.get("native_rerank") is True or config.get("rerank_api") == "native":
        return True

    base_url = (getattr(model_config, "base_url", None) or "").lower()
    if "siliconflow.cn" in base_url or "siliconflow.com" in base_url:
        return True

    return False


def create_rerank_adapter(model_config: Model | ModelConfig) -> BaseRerankAdapter:
    """根据模型配置创建重排序适配器。"""
    provider = model_config.provider
    provider_value = provider.value if hasattr(provider, "value") else str(provider)

    if _should_use_native_openai_compatible_rerank(model_config):
        return OpenAICompatibleRerankAdapter(model_config)

    if provider_value == ModelProvider.OPENAI.value:
        chat_adapter = OpenAIAdapter(model_config)
    elif provider_value == ModelProvider.ANTHROPIC.value:
        chat_adapter = AnthropicAdapter(model_config)
    elif provider_value == ModelProvider.GOOGLE.value:
        chat_adapter = GeminiAdapter(model_config)
    elif provider_value == ModelProvider.DEEPSEEK.value:
        chat_adapter = DeepSeekAdapter(model_config)
    elif provider_value == ModelProvider.XAI.value:
        chat_adapter = XAIAdapter(model_config)
    elif provider_value == ModelProvider.AZURE_OPENAI.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="azure")
    elif provider_value == ModelProvider.MOONSHOT.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="moonshot")
    elif provider_value == ModelProvider.ZHIPU.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="zhipu")
    elif provider_value == ModelProvider.QWEN.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="qwen")
    elif provider_value == ModelProvider.BAICHUAN.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="baichuan")
    elif provider_value == ModelProvider.MINIMAX.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="minimax")
    elif provider_value == ModelProvider.VOLCENGINE.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="volcengine")
    elif provider_value == ModelProvider.OLLAMA.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="ollama")
    elif provider_value == ModelProvider.CUSTOM.value:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint="custom")
    else:
        chat_adapter = OpenAICompatibleAdapter(model_config, provider_hint=provider_value)

    return LLMRerankAdapter(model_config, chat_adapter)
