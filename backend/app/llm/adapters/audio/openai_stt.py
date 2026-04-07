"""
OpenAI Whisper STT 语音识别适配器
"""

import logging
import base64
import httpx
from pathlib import Path

from app.core.i18n import t
from app.models.model import Model
from app.llm.types import (
    STTRequest,
    STTResponse,
    TranscriptionSegment,
    TranscriptionWord,
)
from app.llm.errors import (
    AuthenticationError,
    RateLimitError,
    ProviderError,
    InvalidRequestError,
)
from .base import BaseSTTAdapter

logger = logging.getLogger(__name__)


class OpenAISTTAdapter(BaseSTTAdapter):
    """OpenAI Whisper STT 语音识别适配器"""

    # 支持的响应格式
    SUPPORTED_FORMATS = ["json", "text", "srt", "verbose_json", "vtt"]

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.base_url = model_config.base_url or "https://api.openai.com/v1"
        self.model_id = model_config.model_id  # whisper-1

    async def transcribe(self, request: STTRequest) -> STTResponse:
        """
        语音转文本

        Args:
            request: STT 请求

        Returns:
            STTResponse: 识别结果
        """
        # 获取音频数据
        audio_data = await self._get_audio_data(request)
        if not audio_data:
            raise InvalidRequestError(
                message=t("no_audio_data_provided"),
                provider="openai",
                model=self.model_id,
            )

        # 确定响应格式
        response_format = request.response_format or "verbose_json"
        if response_format not in self.SUPPORTED_FORMATS:
            response_format = "verbose_json"

        # 构建 multipart 表单
        files = {
            "file": ("audio.mp3", audio_data, "audio/mpeg"),
        }
        data = {
            "model": self.model_id,
            "response_format": response_format,
        }

        if request.language:
            data["language"] = request.language
        if request.prompt:
            data["prompt"] = request.prompt
        if request.timestamp_granularities:
            data["timestamp_granularities[]"] = ",".join(
                request.timestamp_granularities
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/audio/transcriptions",
                    files=files,
                    data=data,
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

                # 解析响应
                if response_format == "text":
                    return STTResponse(
                        text=response.text,
                        model=self.model_id,
                    )

                data = response.json()

                # verbose_json 格式包含详细信息
                segments = None
                words = None
                duration = None
                language = None

                if response_format == "verbose_json":
                    duration = data.get("duration")
                    language = data.get("language")

                    if "segments" in data:
                        segments = [
                            TranscriptionSegment(
                                id=seg.get("id", i),
                                start=seg.get("start", 0),
                                end=seg.get("end", 0),
                                text=seg.get("text", ""),
                            )
                            for i, seg in enumerate(data["segments"])
                        ]

                    if "words" in data:
                        words = [
                            TranscriptionWord(
                                word=w.get("word", ""),
                                start=w.get("start", 0),
                                end=w.get("end", 0),
                            )
                            for w in data["words"]
                        ]

                return STTResponse(
                    text=data.get("text", ""),
                    language=language,
                    duration=duration,
                    segments=segments,
                    words=words,
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

    async def _get_audio_data(self, request: STTRequest) -> bytes | None:
        """获取音频数据"""
        audio = request.audio

        if audio.base64:
            return base64.b64decode(audio.base64)

        if audio.file_path:
            path = Path(audio.file_path)
            if path.exists():
                return path.read_bytes()

        if audio.url:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(audio.url)
                if response.status_code == 200:
                    return response.content

        return None
