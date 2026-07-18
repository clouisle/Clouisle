"""
音频适配器
"""

from app.models.model import Model, ModelProvider
from app.llm.errors import UnsupportedOperationError

from .base import BaseAudioGenerationAdapter, BaseTTSAdapter, BaseSTTAdapter
from .openai_tts import OpenAITTSAdapter
from .openai_stt import OpenAISTTAdapter
from .volcengine_generation import VolcengineAudioGenerationAdapter
from .volcengine_tts import VolcengineTTSAdapter


def create_tts_adapter(model_config: Model) -> BaseTTSAdapter:
    """
    创建 TTS 适配器

    Args:
        model_config: 模型配置

    Returns:
        BaseTTSAdapter: TTS 适配器
    """
    provider = model_config.provider

    if provider == ModelProvider.OPENAI:
        return OpenAITTSAdapter(model_config)
    elif provider == ModelProvider.AZURE_OPENAI:
        return OpenAITTSAdapter(model_config)
    elif provider == ModelProvider.VOLCENGINE:
        return VolcengineTTSAdapter(model_config)
    else:
        raise UnsupportedOperationError(
            message=f"TTS not supported for provider: {provider}",
            operation="text_to_speech",
            provider=provider,
        )


def create_audio_generation_adapter(model_config: Model) -> BaseAudioGenerationAdapter:
    """Create a prompt-to-audio adapter for a configured model."""
    provider = model_config.provider
    if provider == ModelProvider.VOLCENGINE:
        return VolcengineAudioGenerationAdapter(model_config)
    raise UnsupportedOperationError(
        message=f"Audio generation not supported for provider: {provider}",
        operation="audio_generation",
        provider=provider,
    )


def create_stt_adapter(model_config: Model) -> BaseSTTAdapter:
    """
    创建 STT 适配器

    Args:
        model_config: 模型配置

    Returns:
        BaseSTTAdapter: STT 适配器
    """
    provider = model_config.provider

    if provider == ModelProvider.OPENAI:
        return OpenAISTTAdapter(model_config)
    elif provider == ModelProvider.AZURE_OPENAI:
        return OpenAISTTAdapter(model_config)
    else:
        raise UnsupportedOperationError(
            message=f"STT not supported for provider: {provider}",
            operation="speech_to_text",
            provider=provider,
        )


__all__ = [
    "create_tts_adapter",
    "create_audio_generation_adapter",
    "create_stt_adapter",
    "BaseAudioGenerationAdapter",
    "BaseTTSAdapter",
    "BaseSTTAdapter",
    "OpenAITTSAdapter",
    "OpenAISTTAdapter",
    "VolcengineAudioGenerationAdapter",
    "VolcengineTTSAdapter",
]
