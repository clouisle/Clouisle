"""
Decision adapter factory.
"""

from typing import Any, Protocol

from app.models.model import Model, ModelProvider

from .base import BaseDecisionAdapter
from .typesafe_adapter import TypeSafeDecisionAdapter


class ModelConfig(Protocol):
    provider: str | ModelProvider
    model_id: str
    api_key: str | None
    base_url: str | None
    default_params: dict[str, Any] | None
    config: dict[str, Any] | None
    max_output_tokens: int | None


def create_decision_adapter(model_config: Model | ModelConfig) -> BaseDecisionAdapter:
    """根据模型配置创建决策模型适配器。"""
    provider = getattr(model_config, "provider", None)
    if hasattr(provider, "value"):
        provider_value = provider.value
    else:
        provider_value = str(provider) if provider else ""

    if provider_value == ModelProvider.TYPESAFE.value:
        return TypeSafeDecisionAdapter(model_config)

    raise ValueError(f"Unsupported provider for decision models: {provider_value}")
