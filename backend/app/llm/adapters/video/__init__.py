"""
Video generation adapters.
"""

from app.llm.errors import UnsupportedOperationError
from app.models.model import Model, ModelProvider

from .base import BaseVideoAdapter
from .luma import LumaVideoAdapter
from .runway import RunwayVideoAdapter


def create_video_adapter(model_config: Model) -> BaseVideoAdapter:
    """Create a provider-specific video-generation adapter."""
    provider = model_config.provider

    if provider == ModelProvider.RUNWAY:
        return RunwayVideoAdapter(model_config)
    if provider == ModelProvider.LUMA:
        return LumaVideoAdapter(model_config)

    raise UnsupportedOperationError(
        message=f"Video generation not supported for provider: {provider}",
        operation="generate_video",
        provider=str(provider),
        model=model_config.model_id,
    )


__all__ = [
    "create_video_adapter",
    "BaseVideoAdapter",
    "RunwayVideoAdapter",
    "LumaVideoAdapter",
]
