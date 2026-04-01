"""
图像生成适配器
"""

from app.models.model import Model, ModelProvider
from app.llm.errors import UnsupportedOperationError

from .base import BaseImageAdapter
from .google import GoogleImageAdapter
from .luma import LumaImageAdapter
from .openai import OpenAIImageAdapter
from .runway import RunwayImageAdapter
from .stability import StabilityImageAdapter


def create_image_adapter(model_config: Model) -> BaseImageAdapter:
    """
    创建图像生成适配器

    Args:
        model_config: 模型配置

    Returns:
        BaseImageAdapter: 图像生成适配器
    """
    provider = model_config.provider

    if provider == ModelProvider.OPENAI:
        return OpenAIImageAdapter(model_config)
    elif provider == ModelProvider.AZURE_OPENAI:
        # Azure OpenAI 使用相同的适配器，只是 base_url 不同
        return OpenAIImageAdapter(model_config)
    elif provider == ModelProvider.CUSTOM:
        return OpenAIImageAdapter(model_config)
    elif provider == ModelProvider.GOOGLE:
        return GoogleImageAdapter(model_config)
    elif provider == ModelProvider.RUNWAY:
        return RunwayImageAdapter(model_config)
    elif provider == ModelProvider.LUMA:
        return LumaImageAdapter(model_config)
    elif provider == ModelProvider.STABILITY:
        return StabilityImageAdapter(model_config)
    else:
        raise UnsupportedOperationError(
            message=f"Image generation not supported for provider: {provider}",
            operation="generate_image",
            provider=provider,
        )


__all__ = [
    "create_image_adapter",
    "BaseImageAdapter",
    "OpenAIImageAdapter",
    "GoogleImageAdapter",
    "RunwayImageAdapter",
    "LumaImageAdapter",
    "StabilityImageAdapter",
]
