"""MiniMax image-generation adapter."""

from __future__ import annotations

from typing import Any

from app.core.i18n import t
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.models.model import Model

from ..media_utils import image_content_to_data_uri, infer_format
from ..minimax_client import MiniMaxClient
from .base import BaseImageAdapter

_MINIMAX_IMAGE_EXTRA_KEYS = {
    "aigc_watermark",
    "aspect_ratio",
    "prompt_optimizer",
    "response_format",
    "style",
}


class MiniMaxImageAdapter(BaseImageAdapter):
    """Generate images through MiniMax's native image API."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = MiniMaxClient(model_config)
        self.model_id = model_config.model_id
        self.provider = "minimax"

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        payload = self._build_payload(request)
        data = await self.client.request("POST", "/image_generation", json=payload)
        return self._parse_response(data, payload)

    def _build_payload(self, request: ImageGenerationRequest) -> dict[str, Any]:
        payload = self._get_effective_extra_params(
            request, include_keys=_MINIMAX_IMAGE_EXTRA_KEYS
        )
        payload.update(
            {
                "model": self.model_id,
                "prompt": request.prompt,
                "n": request.num_images,
            }
        )

        response_format = payload.get("response_format", "url")
        if response_format not in {"url", "base64"}:
            self._invalid_parameter("response_format")
        payload["response_format"] = response_format

        if "aspect_ratio" not in payload:
            payload["width"] = request.width
            payload["height"] = request.height

        seed = self._get_effective_param(request, field_name="seed", param_key="seed")
        if seed is not None:
            payload["seed"] = seed

        if request.images:
            payload["subject_reference"] = [
                {
                    "type": "character",
                    "image_file": image_content_to_data_uri(
                        image,
                        provider=self.provider,
                        model=self.model_id,
                        field_name="images",
                    ),
                }
                for image in request.images
            ]

        return payload

    def _parse_response(
        self, data: dict[str, Any], payload: dict[str, Any]
    ) -> ImageGenerationResponse:
        raw_data = data.get("data")
        raw_data = raw_data if isinstance(raw_data, dict) else {}
        urls = raw_data.get("image_urls")
        base64_images = raw_data.get("image_base64")
        urls = urls if isinstance(urls, list) else []
        base64_images = base64_images if isinstance(base64_images, list) else []

        images = [
            GeneratedImage(image=ImageContent(url=url, format=infer_format(url, "png")))
            for url in urls
            if isinstance(url, str) and url
        ]
        images.extend(
            GeneratedImage(image=ImageContent(base64=value, format="png"))
            for value in base64_images
            if isinstance(value, str) and value
        )
        if not images:
            raise ProviderError(
                message=t("minimax_image_response_missing_output"),
                provider=self.provider,
                model=self.model_id,
            )
        return ImageGenerationResponse(images=images, model=self.model_id)

    def _invalid_parameter(self, field: str) -> None:
        raise InvalidRequestError(
            message=t("minimax_invalid_parameter", field=field),
            field=field,
            provider=self.provider,
            model=self.model_id,
        )
