"""MiniMax synchronous TTS adapter."""

from __future__ import annotations

import base64
from typing import Any

from app.core.i18n import t
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import AudioContent, TTSRequest, TTSResponse
from app.models.model import Model

from ..minimax_client import MiniMaxClient
from .base import BaseTTSAdapter

_MINIMAX_NON_STREAMING_FORMATS = {"mp3", "wav", "flac"}


class MiniMaxTTSAdapter(BaseTTSAdapter):
    """Synthesize speech with MiniMax's non-streaming HTTP API."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = MiniMaxClient(model_config)
        self.model_id = model_config.model_id
        self.provider = "minimax"
        self.default_params = getattr(model_config, "default_params", None) or {}
        self.config = getattr(model_config, "config", None) or {}

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload = self._build_payload(request)
        data = await self.client.request("POST", "/t2a_v2", json=payload)
        raw_data = data.get("data")
        audio_hex = raw_data.get("audio") if isinstance(raw_data, dict) else None
        if not isinstance(audio_hex, str) or not audio_hex:
            raise ProviderError(
                message=t("minimax_tts_response_missing_output"),
                provider=self.provider,
                model=self.model_id,
            )
        try:
            audio_bytes = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise ProviderError(
                message=t("minimax_tts_invalid_audio"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        if not audio_bytes:
            raise ProviderError(
                message=t("minimax_tts_response_missing_output"),
                provider=self.provider,
                model=self.model_id,
            )

        audio_format = str(payload["audio_setting"]["format"])
        return TTSResponse(
            audio=AudioContent(
                base64=base64.b64encode(audio_bytes).decode("utf-8"),
                format=audio_format,
            ),
            model=self.model_id,
        )

    def _build_payload(self, request: TTSRequest) -> dict[str, Any]:
        if not request.text or len(request.text) >= 10_000:
            self._invalid_parameter("text")

        voice = self._value("voice", request.voice)
        if not isinstance(voice, str) or not voice:
            self._invalid_parameter("voice")

        speed = float(
            request.speed
            if "speed" in request.model_fields_set
            else self._value("speed", default=request.speed)
        )
        if not 0.5 <= speed <= 2:
            self._invalid_parameter("speed")

        audio_format = str(
            request.format
            if "format" in request.model_fields_set
            else self._value("format", default=request.format)
        ).lower()
        if audio_format not in _MINIMAX_NON_STREAMING_FORMATS:
            self._invalid_parameter("format")

        voice_setting: dict[str, Any] = {"voice_id": voice, "speed": speed}
        for key in {"vol", "pitch", "emotion", "text_normalization", "latex_read"}:
            value = self._value(key)
            if value is not None:
                voice_setting[key] = value

        audio_setting: dict[str, Any] = {"format": audio_format}
        for key in {"sample_rate", "bitrate", "channel"}:
            value = self._value(key)
            if value is not None:
                audio_setting[key] = value

        payload: dict[str, Any] = {
            "model": self.model_id,
            "text": request.text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": voice_setting,
            "audio_setting": audio_setting,
        }
        for key in {"language_boost", "aigc_watermark"}:
            value = self._value(key)
            if value is not None:
                payload[key] = value
        return payload

    def _value(
        self, key: str, request_value: Any = None, *, default: Any = None
    ) -> Any:
        if request_value not in (None, ""):
            return request_value
        value = self.default_params.get(key)
        if value not in (None, ""):
            return value
        value = self.config.get(key)
        return value if value not in (None, "") else default

    def _invalid_parameter(self, field: str) -> None:
        raise InvalidRequestError(
            message=t("minimax_invalid_parameter", field=field),
            field=field,
            provider=self.provider,
            model=self.model_id,
        )
