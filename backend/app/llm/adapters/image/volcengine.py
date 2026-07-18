"""Volcengine Ark (Seedream) image-generation adapter."""

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

from ..media_utils import (
    append_prompt_directives,
    image_content_to_data_uri,
    infer_format,
)
from ..volcengine_client import VolcengineClient
from .base import BaseImageAdapter

_VOLCENGINE_IMAGE_EXTRA_KEYS = {
    "optimize_prompt_options",
    "output_format",
    "response_format",
    "sequential_image_generation",
    "sequential_image_generation_options",
    "watermark",
}


class VolcengineImageAdapter(BaseImageAdapter):
    """Generate Seedream images through the Ark Images API."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = VolcengineClient(model_config)
        self.model_id = model_config.model_id
        self.provider = "volcengine"

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        payload = self._build_payload(request)
        data = await self.client.generate_image(payload)
        return self._parse_response(data, payload)

    def _build_payload(self, request: ImageGenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Avoid: {request.negative_prompt}"
                if request.negative_prompt
                else None,
            ),
            "size": self._get_effective_param(
                request,
                param_key="size",
                fallback=f"{request.width}x{request.height}",
            ),
        }
        payload.update(
            self._get_effective_extra_params(
                request, include_keys=_VOLCENGINE_IMAGE_EXTRA_KEYS
            )
        )

        seed = self._get_effective_param(
            request,
            field_name="seed",
            param_key="seed",
        )
        if seed is not None:
            payload["seed"] = seed

        if request.images:
            references = [
                image_content_to_data_uri(
                    image,
                    provider=self.provider,
                    model=self.model_id,
                    field_name="images",
                )
                for image in request.images
            ]
            payload["image"] = references[0] if len(references) == 1 else references

        response_format = payload.get("response_format", "url")
        if response_format not in {"url", "b64_json"}:
            self._invalid_parameter("response_format")
        payload["response_format"] = response_format

        sequential_mode = payload.get("sequential_image_generation", "disabled")
        if sequential_mode not in {"disabled", "auto"}:
            self._invalid_parameter("sequential_image_generation")
        payload["sequential_image_generation"] = sequential_mode

        options = payload.get("sequential_image_generation_options")
        if options is not None and not isinstance(options, dict):
            self._invalid_parameter("sequential_image_generation_options")
        if sequential_mode == "auto" and request.num_images > 1:
            payload["sequential_image_generation_options"] = {
                **(options or {}),
                "max_images": request.num_images,
            }
        elif sequential_mode == "disabled":
            payload.pop("sequential_image_generation_options", None)

        return payload

    def _parse_response(
        self,
        data: dict[str, Any],
        payload: dict[str, Any],
    ) -> ImageGenerationResponse:
        raw_images = data.get("data")
        if not isinstance(raw_images, list):
            raw_images = []

        default_format = str(payload.get("output_format") or "jpeg")
        images: list[GeneratedImage] = []
        for item in raw_images:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            base64_image = item.get("b64_json")
            url = url if isinstance(url, str) and url else None
            base64_image = (
                base64_image if isinstance(base64_image, str) and base64_image else None
            )
            if not url and not base64_image:
                continue
            seed = item.get("seed")
            images.append(
                GeneratedImage(
                    image=ImageContent(
                        url=url,
                        base64=base64_image,
                        format=infer_format(url, default_format)
                        if url
                        else default_format,
                    ),
                    revised_prompt=item.get("revised_prompt"),
                    seed=seed if isinstance(seed, int) else None,
                )
            )

        if not images:
            raise ProviderError(
                message=t("volcengine_image_response_missing_output"),
                provider=self.provider,
                model=self.model_id,
            )

        return ImageGenerationResponse(images=images, model=self.model_id)

    def _invalid_parameter(self, field: str) -> None:
        raise InvalidRequestError(
            message=t("volcengine_image_invalid_parameter", field=field),
            field=field,
            provider=self.provider,
            model=self.model_id,
        )
