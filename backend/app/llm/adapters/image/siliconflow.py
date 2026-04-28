"""
SiliconFlow image-generation adapter.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.i18n import t
from app.llm.adapters.media_utils import (
    append_prompt_directives,
    infer_format,
    media_content_to_data_uri,
)
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

_SILICONFLOW_IMAGE_EXTRA_PARAM_KEYS = {
    "num_inference_steps",
    "guidance_scale",
    "cfg",
    "image",
    "image2",
    "image3",
}
_SILICONFLOW_IMAGE_REFERENCE_FIELDS = ("image", "image2", "image3")


class SiliconFlowImageAdapter(BaseImageAdapter):
    """SiliconFlow image-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.provider = "siliconflow"
        self.base_url = (
            model_config.base_url or "https://api.siliconflow.cn/v1"
        ).rstrip("/")
        self.model_id = model_config.model_id

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        payload = self._build_payload(request)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self._build_url("/images/generations"),
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message=t("siliconflow_request_timeout"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"SiliconFlow request failed: {exc}",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        self._raise_for_status(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                message=t("siliconflow_api_error"),
                provider=self.provider,
                model=self.model_id,
            ) from exc

        return self._parse_response_data(data)

    def _build_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        if self.base_url.endswith("/v1") and normalized.startswith("/v1/"):
            normalized = normalized[3:]
        return f"{self.base_url}{normalized}"

    def _build_payload(self, request: ImageGenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
            ),
            "image_size": f"{request.width}x{request.height}",
            "batch_size": request.num_images,
        }

        negative_prompt = self._get_effective_param(
            request,
            field_name="negative_prompt",
            param_key="negative_prompt",
        )
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        seed = self._get_effective_param(
            request,
            field_name="seed",
            param_key="seed",
        )
        if isinstance(seed, int):
            payload["seed"] = seed

        include_keys = {"num_inference_steps", "guidance_scale", "cfg"}
        if not request.images:
            include_keys.update(_SILICONFLOW_IMAGE_REFERENCE_FIELDS)
        payload.update(
            self._get_effective_extra_params(request, include_keys=include_keys)
        )
        payload.update(self._build_reference_image_fields(request))

        passthrough_extra_params = dict(request.extra_params or {})
        for managed_key in {
            "model",
            "prompt",
            "negative_prompt",
            "image_size",
            "batch_size",
            "seed",
            * _SILICONFLOW_IMAGE_EXTRA_PARAM_KEYS,
        }:
            passthrough_extra_params.pop(managed_key, None)
        payload.update(passthrough_extra_params)

        return payload

    def _build_reference_image_fields(
        self, request: ImageGenerationRequest
    ) -> dict[str, str]:
        if not request.images:
            return {}

        if len(request.images) > len(_SILICONFLOW_IMAGE_REFERENCE_FIELDS):
            raise InvalidRequestError(
                message="SiliconFlow supports up to 3 reference images",
                field="images",
                provider=self.provider,
                model=self.model_id,
            )

        return {
            field_name: media_content_to_data_uri(
                image,
                default_mime="image/png",
                provider=self.provider,
                model=self.model_id,
                field_name=field_name,
            )
            for field_name, image in zip(
                _SILICONFLOW_IMAGE_REFERENCE_FIELDS,
                request.images,
                strict=False,
            )
        }

    def _parse_response_data(self, data: dict[str, Any]) -> ImageGenerationResponse:
        seed = self._extract_seed(data)
        raw_images = data.get("images")
        if not isinstance(raw_images, list):
            raw_images = data.get("data", [])

        images: list[GeneratedImage] = []
        for item in raw_images:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            base64_image = item.get("b64_json") or item.get("base64")
            if not isinstance(url, str):
                url = None
            if not isinstance(base64_image, str):
                base64_image = None
            if not url and not base64_image:
                continue
            images.append(
                GeneratedImage(
                    image=ImageContent(
                        url=url,
                        base64=base64_image,
                        format=infer_format(url, "png") if url else "png",
                    ),
                    revised_prompt=item.get("revised_prompt"),
                    seed=seed,
                )
            )

        if not images:
            raise ProviderError(
                message="SiliconFlow response missing generated images",
                provider=self.provider,
                model=self.model_id,
            )

        return ImageGenerationResponse(images=images, model=self.model_id)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 200:
            return

        message = self._extract_error_message(response)
        content_blocked = self._is_content_filter_error(message)

        if response.status_code == 401:
            raise AuthenticationError(
                message=message or t("invalid_siliconflow_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 404:
            raise InvalidRequestError(
                message=message or t("siliconflow_endpoint_not_found"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=message or t("siliconflow_rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            )
        if content_blocked:
            raise ContentFilterError(
                message=message or t("siliconflow_api_error"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 400:
            raise InvalidRequestError(
                message=message or t("siliconflow_api_error"),
                provider=self.provider,
                model=self.model_id,
            )

        raise ProviderError(
            message=message or t("siliconflow_api_error"),
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

            error_value = data.get("error")
            if isinstance(error_value, dict):
                for key in ("message", "detail", "type"):
                    value = error_value.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
            elif isinstance(error_value, str) and error_value.strip():
                return error_value.strip()

            for key in ("message", "detail"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return response.text.strip()

    def _extract_seed(self, data: dict[str, Any]) -> int | None:
        seed = data.get("seed")
        if isinstance(seed, int):
            return seed
        if isinstance(seed, str) and seed.isdigit():
            return int(seed)
        return None

    def _is_content_filter_error(self, message: str) -> bool:
        lowered = message.lower()
        return any(
            keyword in lowered
            for keyword in ("content_policy", "safety", "moderation", "unsafe")
        )
