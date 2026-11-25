"""
OCR adapter factory.
"""

from typing import Any, Protocol

from app.models.model import Model, ModelProvider

from .base import BaseOCRAdapter
from .mistral_adapter import MistralOCRAdapter
from .openai_compatible_adapter import OpenAICompatibleOCRAdapter


class ModelConfig(Protocol):
    provider: str | ModelProvider
    model_id: str
    api_key: str | None
    base_url: str | None
    default_params: dict[str, Any] | None
    config: dict[str, Any] | None
    max_output_tokens: int | None


# Providers that expose a chat-completions transcription endpoint for OCR models.
_OPENAI_COMPATIBLE_PROVIDERS = {
    ModelProvider.QWEN.value,
    ModelProvider.CUSTOM.value,
}


def create_ocr_adapter(model_config: Model | ModelConfig) -> BaseOCRAdapter:
    """根据模型配置创建文字识别适配器。"""
    provider = getattr(model_config, "provider", None)
    if provider is None:
        provider_value = ""
    elif hasattr(provider, "value"):
        provider_value = provider.value
    else:
        provider_value = str(provider)

    if provider_value == ModelProvider.MISTRAL.value:
        return MistralOCRAdapter(model_config)
    if provider_value in _OPENAI_COMPATIBLE_PROVIDERS:
        return OpenAICompatibleOCRAdapter(model_config)

    raise ValueError(f"Unsupported provider for OCR models: {provider_value}")
