"""Volcengine Seed Audio HTTP generation adapter."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
from pathlib import Path
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
from app.llm.types import (
    AudioContent,
    AudioGenerationRequest,
    AudioGenerationResponse,
)
from app.llm.types.base import MediaContent
from app.models.model import Model

from .base import BaseAudioGenerationAdapter


class VolcengineAudioGenerationAdapter(BaseAudioGenerationAdapter):
    """Seed Audio 1.0 through OpenSpeech's documented HTTP endpoint."""

    provider = "volcengine"
    default_base_url = "https://openspeech.bytedance.com/api/v3/tts/create"
    supported_formats = {"wav", "mp3", "pcm", "ogg_opus"}

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.base_url = (model_config.base_url or self.default_base_url).rstrip("/")
        self.default_params = getattr(model_config, "default_params", None) or {}
        self.config = getattr(model_config, "config", None) or {}

    async def generate(
        self, request: AudioGenerationRequest
    ) -> AudioGenerationResponse:
        payload, audio_format = await asyncio.to_thread(self._build_payload, request)
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": str(self.api_key),
            "X-Api-Request-Id": str(uuid4()),
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )
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

        self._raise_for_status(response)
        try:
            result = response.json()
        except ValueError as exc:
            raise ProviderError(
                message="Invalid Volcengine Seed Audio response",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        code = result.get("code")
        if code not in (None, 0, 20000000):
            raise ProviderError(
                message=str(result.get("message") or "Volcengine Seed Audio failed"),
                provider=self.provider,
                model=self.model_id,
            )

        audio = result.get("audio")
        url = result.get("url")
        if not audio and not url:
            raise ProviderError(
                message="Volcengine Seed Audio returned no audio",
                provider=self.provider,
                model=self.model_id,
            )

        return AudioGenerationResponse(
            audio=AudioContent(
                base64=str(audio) if audio else None,
                url=str(url) if url else None,
                duration=self._optional_float(result.get("duration")),
                format=audio_format,
            ),
            model=self.model_id,
        )

    def _build_payload(
        self, request: AudioGenerationRequest
    ) -> tuple[dict[str, Any], str]:
        if not self.api_key:
            raise AuthenticationError(
                message=t("invalid_volcengine_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if self.model_id != "seed-audio-1.0":
            raise InvalidRequestError(
                message="Volcengine audio generation requires seed-audio-1.0",
                field="model_id",
                provider=self.provider,
                model=self.model_id,
            )
        if request.image and request.audio_references:
            raise InvalidRequestError(
                message="Seed Audio image and audio references cannot be combined",
                field="references",
                provider=self.provider,
                model=self.model_id,
            )

        audio_format = (
            request.format
            if "format" in request.model_fields_set
            else self._value("format", request.format)
        )
        if audio_format not in self.supported_formats:
            raise InvalidRequestError(
                message=f"Unsupported Seed Audio format: {audio_format}",
                field="format",
                provider=self.provider,
                model=self.model_id,
            )

        sample_rate = int(self._value("sample_rate", 24000))
        if sample_rate not in {8000, 16000, 24000, 32000, 44100, 48000}:
            raise InvalidRequestError(
                message=f"Unsupported Seed Audio sample rate: {sample_rate}",
                field="sample_rate",
                provider=self.provider,
                model=self.model_id,
            )
        payload: dict[str, Any] = {
            "model": self.model_id,
            "text_prompt": request.prompt,
            "audio_config": {
                "format": audio_format,
                "sample_rate": sample_rate,
            },
        }
        references: list[dict[str, str]] = []
        if request.image:
            references.append(self._reference(request.image, "image"))
        else:
            references.extend(
                self._reference(reference, "audio")
                for reference in request.audio_references
            )
        if references:
            payload["references"] = references

        allowed = {
            "speech_rate",
            "loudness_rate",
            "pitch_rate",
            "enable_subtitle",
        }
        for key in allowed:
            value = request.extra_params.get(key, self._value(key))
            if value is not None:
                payload["audio_config"][key] = value
        return payload, audio_format

    def _reference(self, content: MediaContent, kind: str) -> dict[str, str]:
        if content.url:
            return {f"{kind}_url": content.url}
        if content.base64:
            value = content.base64
            if value.startswith("data:"):
                value = value.split(",", 1)[1]
            return {f"{kind}_data": value}
        if content.file_path:
            mime_type, _ = mimetypes.guess_type(content.file_path)
            if kind == "image" and not (mime_type or "").startswith("image/"):
                raise InvalidRequestError(
                    message="Unsupported Seed Audio image reference",
                    field="image",
                    provider=self.provider,
                    model=self.model_id,
                )
            data = base64.b64encode(Path(content.file_path).read_bytes()).decode()
            return {f"{kind}_data": data}
        raise InvalidRequestError(
            message=f"{kind} reference must include url, base64, or file_path",
            field=f"{kind}_reference",
            provider=self.provider,
            model=self.model_id,
        )

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
                message=f"Volcengine Seed Audio API error: {response.text}",
                status_code=response.status_code,
                provider=self.provider,
                model=self.model_id,
            )

    def _value(self, key: str, default: Any = None) -> Any:
        value = self.default_params.get(key)
        if value not in (None, ""):
            return value
        value = self.config.get(key)
        return default if value in (None, "") else value

    def _timeout(self) -> float:
        return float(self.config.get("timeout", 180))

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return float(value) if value is not None else None
