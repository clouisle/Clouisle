"""
Stability AI text-to-image adapter.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.i18n import t
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.models.model import Model

from .base import BaseImageAdapter

_STABILITY_ASPECT_RATIOS: dict[str, float] = {
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "5:4": 5 / 4,
    "3:2": 3 / 2,
    "1:1": 1.0,
    "2:3": 2 / 3,
    "4:5": 4 / 5,
    "9:16": 9 / 16,
    "9:21": 9 / 21,
}
_STABILITY_IMAGE_PATHS = {
    "ultra": "/v2beta/stable-image/generate/ultra",
    "core": "/v2beta/stable-image/generate/core",
    "sd3": "/v2beta/stable-image/generate/sd3",
}


class StabilityImageAdapter(BaseImageAdapter):
    """Stability AI Stable Image / Stable Diffusion adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.provider = (
            model_config.provider.value
            if hasattr(model_config.provider, "value")
            else str(model_config.provider)
        )
        self.base_url = self._normalize_base_url(model_config.base_url)
        self.model_id = model_config.model_id

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        output_format = self._get_output_format(request)
        images: list[GeneratedImage] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            for index in range(request.num_images):
                response = await self._submit_generation(
                    client=client,
                    payload=self._build_form_data(
                        request,
                        output_format=output_format,
                        seed_offset=index,
                    ),
                )
                images.append(
                    self._parse_response(response, output_format=output_format)
                )

        return ImageGenerationResponse(images=images, model=self.model_id)

    async def _submit_generation(
        self,
        *,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> httpx.Response:
        try:
            response = await client.post(
                self._build_url(self._build_path()),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "image/*",
                },
                data=payload,
                files={"none": ("", b"")},
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message=t("request_timeout"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"Request error: {exc}",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        self._raise_for_status(response)
        return response

    def _build_path(self) -> str:
        model_id = self.model_id.lower()
        if "ultra" in model_id:
            return _STABILITY_IMAGE_PATHS["ultra"]
        if "core" in model_id:
            return _STABILITY_IMAGE_PATHS["core"]
        return _STABILITY_IMAGE_PATHS["sd3"]

    def _build_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        if self.base_url.endswith("/v1") and normalized.startswith("/v2beta/"):
            return f"{self.base_url[:-3]}{normalized}"
        return f"{self.base_url}{normalized}"

    def _build_form_data(
        self,
        request: ImageGenerationRequest,
        *,
        output_format: str,
        seed_offset: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "output_format": output_format,
        }

        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        style_preset = self._get_effective_param(
            request,
            field_name="style",
            param_key="style_preset",
        )
        if style_preset:
            payload["style_preset"] = style_preset

        if request.width > 0 and request.height > 0:
            payload["aspect_ratio"] = self._closest_aspect_ratio(
                request.width,
                request.height,
            )

        if request.seed is not None and request.seed >= 0:
            payload["seed"] = request.seed + seed_offset

        if self._build_path() == _STABILITY_IMAGE_PATHS["sd3"]:
            payload["model"] = self.model_id

        extra_params = dict(request.extra_params or {})
        for managed_key in {"style_preset", "output_format", "seed", "aspect_ratio", "model"}:
            extra_params.pop(managed_key, None)
        payload.update(extra_params)
        return payload

    def _parse_response(
        self,
        response: httpx.Response,
        *,
        output_format: str,
    ) -> GeneratedImage:
        content_type = response.headers.get("content-type", "").lower()

        if "application/json" in content_type:
            data = response.json()
            image_base64 = self._extract_base64_image(data)
            if not image_base64:
                raise ProviderError(
                    message=t("stability_response_missing_image_data"),
                    provider=self.provider,
                    model=self.model_id,
                )
            return GeneratedImage(
                image=ImageContent(
                    base64=image_base64,
                    format=self._infer_output_format(content_type, output_format),
                ),
                seed=self._extract_seed(data),
            )

        if not response.content:
            raise ProviderError(
                message=t("stability_response_missing_image_bytes"),
                provider=self.provider,
                model=self.model_id,
            )

        return GeneratedImage(
            image=ImageContent(
                base64=base64.b64encode(response.content).decode("utf-8"),
                format=self._infer_output_format(content_type, output_format),
            ),
            seed=self._extract_seed(response.headers),
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 200:
            return

        message = self._extract_error_message(response)

        if response.status_code == 401:
            raise AuthenticationError(
                message=message or t("invalid_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 403:
            raise ContentFilterError(
                message=message or t("stability_content_blocked_by_moderation"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=message or t("rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code in {400, 413, 422}:
            raise InvalidRequestError(
                message=message or t("invalid_stability_image_request"),
                provider=self.provider,
                model=self.model_id,
            )

        raise ProviderError(
            message=message or t("stability_image_generation_failed"),
            status_code=response.status_code,
            provider=self.provider,
            model=self.model_id,
        )

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text.strip()

        if isinstance(data, dict):
            errors = data.get("errors")
            if isinstance(errors, list):
                parts = []
                for item in errors:
                    if isinstance(item, dict):
                        parts.append(
                            str(item.get("message") or item.get("detail") or item)
                        )
                    else:
                        parts.append(str(item))
                if parts:
                    return "; ".join(parts)

            for key in ("message", "error", "detail", "name"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return response.text.strip()

    def _extract_base64_image(self, data: dict[str, Any]) -> str | None:
        for key in ("image", "base64", "b64_json"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value

        artifacts = data.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                for key in ("base64", "b64_json"):
                    value = artifact.get(key)
                    if isinstance(value, str) and value:
                        return value
        return None

    def _extract_seed(self, data: Any) -> int | None:
        if isinstance(data, dict):
            seed = data.get("seed")
            if isinstance(seed, int):
                return seed

            artifacts = data.get("artifacts")
            if isinstance(artifacts, list):
                for artifact in artifacts:
                    if isinstance(artifact, dict) and isinstance(
                        artifact.get("seed"), int
                    ):
                        return artifact["seed"]

        if isinstance(data, httpx.Headers):
            for key in ("seed", "x-seed"):
                value = data.get(key)
                if value and value.isdigit():
                    return int(value)

        return None

    def _get_output_format(self, request: ImageGenerationRequest) -> str:
        output_format = self._get_effective_param(
            request,
            param_key="output_format",
        )
        if isinstance(output_format, str) and output_format:
            return output_format

        if request.quality in {"jpeg", "png", "webp"}:
            return str(request.quality)

        return "png"

    def _infer_output_format(self, content_type: str, fallback: str) -> str:
        if "image/jpeg" in content_type:
            return "jpeg"
        if "image/webp" in content_type:
            return "webp"
        if "image/png" in content_type:
            return "png"
        return fallback

    def _normalize_base_url(self, base_url: str | None) -> str:
        return (base_url or "https://api.stability.ai").rstrip("/")

    def _closest_aspect_ratio(self, width: int, height: int) -> str:
        target = width / height
        return min(
            _STABILITY_ASPECT_RATIOS,
            key=lambda ratio: abs(_STABILITY_ASPECT_RATIOS[ratio] - target),
        )
