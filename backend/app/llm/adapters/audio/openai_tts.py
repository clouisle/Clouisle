"""
OpenAI TTS 语音合成适配器
"""

import logging
import base64
import httpx

from app.core.i18n import t
from app.models.model import Model
from app.llm.types import TTSRequest, TTSResponse, AudioContent
from app.llm.errors import (
    AuthenticationError,
    RateLimitError,
    ProviderError,
    InvalidRequestError,
)
from .base import BaseTTSAdapter

logger = logging.getLogger(__name__)


class OpenAITTSAdapter(BaseTTSAdapter):
    """OpenAI TTS 语音合成适配器"""

    # OpenAI TTS 支持的声音
    SUPPORTED_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    # 支持的格式
    SUPPORTED_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.base_url = model_config.base_url or "https://api.openai.com/v1"
        self.model_id = model_config.model_id  # tts-1 或 tts-1-hd

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        文本转语音

        Args:
            request: TTS 请求

        Returns:
            TTSResponse: 合成结果
        """
        # 验证参数
        voice = request.voice or "alloy"
        if voice not in self.SUPPORTED_VOICES:
            voice = "alloy"

        audio_format = request.format or "mp3"
        if audio_format not in self.SUPPORTED_FORMATS:
            audio_format = "mp3"

        payload = {
            "model": self.model_id,
            "input": request.text,
            "voice": voice,
            "response_format": audio_format,
            "speed": request.speed,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/audio/speech",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 401:
                    raise AuthenticationError(
                        message=t("invalid_api_key"),
                        provider="openai",
                        model=self.model_id,
                    )
                elif response.status_code == 429:
                    raise RateLimitError(
                        message=t("rate_limit_exceeded"),
                        provider="openai",
                        model=self.model_id,
                    )
                elif response.status_code == 400:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get(
                        "message", t("bad_request")
                    )
                    raise InvalidRequestError(
                        message=error_msg,
                        provider="openai",
                        model=self.model_id,
                    )
                elif response.status_code != 200:
                    raise ProviderError(
                        message=f"OpenAI API error: {response.text}",
                        status_code=response.status_code,
                        provider="openai",
                        model=self.model_id,
                    )

                # 响应是音频二进制数据
                audio_data = response.content
                audio_base64 = base64.b64encode(audio_data).decode("utf-8")

                return TTSResponse(
                    audio=AudioContent(
                        base64=audio_base64,
                        format=audio_format,
                    ),
                    model=self.model_id,
                )

            except httpx.TimeoutException:
                raise ProviderError(
                    message=t("request_timeout"),
                    provider="openai",
                    model=self.model_id,
                )
            except httpx.RequestError as e:
                raise ProviderError(
                    message=f"Request error: {str(e)}",
                    provider="openai",
                    model=self.model_id,
                )
