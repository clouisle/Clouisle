"""
音频适配器基类
"""

from abc import ABC, abstractmethod

from app.llm.types import (
    AudioGenerationRequest,
    AudioGenerationResponse,
    STTRequest,
    STTResponse,
    TTSRequest,
    TTSResponse,
)


class BaseTTSAdapter(ABC):
    """TTS 适配器基类"""

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """文本转语音"""
        pass


class BaseAudioGenerationAdapter(ABC):
    """Audio generation adapter base."""

    @abstractmethod
    async def generate(
        self, request: AudioGenerationRequest
    ) -> AudioGenerationResponse:
        """Generate audio from a prompt and optional references."""
        pass


class BaseSTTAdapter(ABC):
    """STT 适配器基类"""

    @abstractmethod
    async def transcribe(self, request: STTRequest) -> STTResponse:
        """语音转文本"""
        pass
