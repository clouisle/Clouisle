"""Volcengine OpenSpeech HTTP SSE text-to-speech adapter."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import uuid4

import httpx

from app.core.i18n import t
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import AudioContent, TTSRequest, TTSResponse
from app.models.model import Model

from .base import BaseTTSAdapter


class VolcengineTTSAdapter(BaseTTSAdapter):
    """Doubao TTS through OpenSpeech's documented SSE endpoint."""

    provider = "volcengine"
    default_base_url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse"
    supported_formats = {"mp3", "ogg_opus", "pcm"}
    completion_code = 20000000

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.base_url = (model_config.base_url or self.default_base_url).rstrip("/")
        self.default_params = getattr(model_config, "default_params", None) or {}
        self.config = getattr(model_config, "config", None) or {}

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        payload, audio_format = self._build_payload(request)
        chunks: list[bytes] = []
        completed = False

        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                async with client.stream(
                    "POST",
                    self.base_url,
                    json=payload,
                    headers=self._headers(),
                ) as response:
                    self._raise_for_status(response)
                    event = ""
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if line:
                            if line.startswith("event:"):
                                event = line[6:].strip()
                            elif line.startswith("data:"):
                                data_lines.append(line[5:].strip())
                            continue

                        event_chunks, event_completed = self._consume_event(
                            event, "\n".join(data_lines)
                        )
                        chunks.extend(event_chunks)
                        completed = completed or event_completed
                        event = ""
                        data_lines = []

                    if data_lines:
                        event_chunks, event_completed = self._consume_event(
                            event, "\n".join(data_lines)
                        )
                        chunks.extend(event_chunks)
                        completed = completed or event_completed
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message=t("volcengine_request_timeout"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"Volcengine request failed: {exc}",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        if not completed:
            raise ProviderError(
                message="Volcengine TTS stream ended before completion",
                provider=self.provider,
                model=self.model_id,
            )
        if not chunks:
            raise ProviderError(
                message="Volcengine TTS returned no audio",
                provider=self.provider,
                model=self.model_id,
            )

        return TTSResponse(
            audio=AudioContent(
                base64=base64.b64encode(b"".join(chunks)).decode(),
                format=audio_format,
            ),
            model=self.model_id,
        )

    def _build_payload(self, request: TTSRequest) -> tuple[dict[str, Any], str]:
        if not self.api_key:
            raise AuthenticationError(
                message=t("invalid_volcengine_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if not self.model_id:
            raise InvalidRequestError(
                message="Volcengine TTS resource ID is required",
                field="model_id",
                provider=self.provider,
                model=self.model_id,
            )

        speaker = self._value("speaker", request.voice) or self._value("voice")
        if not speaker:
            raise InvalidRequestError(
                message="Volcengine TTS speaker is required",
                field="speaker",
                provider=self.provider,
                model=self.model_id,
            )

        audio_format = (
            request.format
            if "format" in request.model_fields_set
            else self._value("format", default=request.format)
        )
        if audio_format not in self.supported_formats:
            raise InvalidRequestError(
                message=f"Unsupported Volcengine TTS format: {audio_format}",
                field="format",
                provider=self.provider,
                model=self.model_id,
            )

        speed = (
            request.speed
            if "speed" in request.model_fields_set
            else float(self._value("speed", default=request.speed))
        )
        if not 0.5 <= speed <= 2:
            raise InvalidRequestError(
                message="Volcengine TTS speed must be between 0.5 and 2.0",
                field="speed",
                provider=self.provider,
                model=self.model_id,
            )
        sample_rate = int(self._value("sample_rate", default=24000))
        if sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000}:
            raise InvalidRequestError(
                message=f"Unsupported Volcengine TTS sample rate: {sample_rate}",
                field="sample_rate",
                provider=self.provider,
                model=self.model_id,
            )
        audio_params: dict[str, Any] = {
            "format": audio_format,
            "sample_rate": sample_rate,
            "speech_rate": round((speed - 1) * 100),
        }
        for key in ("bit_rate", "emotion", "emotion_scale", "loudness_rate"):
            value = self._value(key)
            if value is not None:
                audio_params[key] = value

        return (
            {
                "user": {"uid": str(self._value("uid", default="clouisle"))},
                "req_params": {
                    "text": request.text,
                    "speaker": str(speaker),
                    "audio_params": audio_params,
                },
            },
            audio_format,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Api-Key": str(self.api_key),
            "X-Api-Resource-Id": self.model_id,
            "X-Api-Request-Id": str(uuid4()),
        }

    def _consume_event(self, event: str, data: str) -> tuple[list[bytes], bool]:
        if not data:
            return [], False
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                message="Invalid Volcengine TTS SSE payload",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        code = payload.get("code")
        if code == self.completion_code:
            return [], True
        if code != 0:
            raise ProviderError(
                message=str(payload.get("message") or "Volcengine TTS failed"),
                provider=self.provider,
                model=self.model_id,
            )
        if event == "352" and payload.get("data"):
            try:
                return [base64.b64decode(payload["data"], validate=True)], False
            except (TypeError, ValueError) as exc:
                raise ProviderError(
                    message="Invalid Volcengine TTS audio payload",
                    provider=self.provider,
                    model=self.model_id,
                ) from exc
        return [], False

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise AuthenticationError(
                message=t("invalid_volcengine_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=t("volcengine_rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code >= 400:
            raise ProviderError(
                message=f"Volcengine TTS API error: {response.text}",
                status_code=response.status_code,
                provider=self.provider,
                model=self.model_id,
            )

    def _value(self, key: str, explicit: Any = None, default: Any = None) -> Any:
        if explicit not in (None, ""):
            return explicit
        value = self.default_params.get(key)
        if value not in (None, ""):
            return value
        value = self.config.get(key)
        return default if value in (None, "") else value

    def _timeout(self) -> float:
        return float(self.config.get("timeout", 180))
