"""
Video generation adapters.
"""

from app.llm.errors import UnsupportedOperationError
from app.models.model import Model, ModelProvider

from .base import BaseVideoAdapter
from .dashscope import DashScopeVideoAdapter
from .kling import KlingVideoAdapter
from .luma import LumaVideoAdapter
from .pika import PikaVideoAdapter
from .runway import RunwayVideoAdapter
from .siliconflow import SiliconFlowVideoAdapter
from .volcengine import VolcengineVideoAdapter


def create_video_adapter(model_config: Model) -> BaseVideoAdapter:
    """Create a provider-specific video-generation adapter."""
    provider = model_config.provider

    if provider == ModelProvider.RUNWAY:
        return RunwayVideoAdapter(model_config)
    if provider == ModelProvider.LUMA:
        return LumaVideoAdapter(model_config)
    if provider == ModelProvider.KLING:
        return KlingVideoAdapter(model_config)
    if provider == ModelProvider.PIKA:
        return PikaVideoAdapter(model_config)
    if provider == ModelProvider.SILICONFLOW:
        return SiliconFlowVideoAdapter(model_config)
    if provider == ModelProvider.VOLCENGINE:
        return VolcengineVideoAdapter(model_config)
    if provider == ModelProvider.QWEN:
        return DashScopeVideoAdapter(model_config)

    raise UnsupportedOperationError(
        message=f"Video generation not supported for provider: {provider}",
        operation="generate_video",
        provider=str(provider),
        model=model_config.model_id,
    )


__all__ = [
    "create_video_adapter",
    "BaseVideoAdapter",
    "DashScopeVideoAdapter",
    "KlingVideoAdapter",
    "LumaVideoAdapter",
    "PikaVideoAdapter",
    "RunwayVideoAdapter",
    "SiliconFlowVideoAdapter",
    "VolcengineVideoAdapter",
]
