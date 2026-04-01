"""
Luma image-generation adapter.
"""

from __future__ import annotations

from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.models.model import Model

from ..luma_client import LumaClient
from ..media_utils import append_prompt_directives, closest_aspect_ratio
from .base import BaseImageAdapter


class LumaImageAdapter(BaseImageAdapter):
    """Luma Dream Machine image-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = LumaClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        images: list[GeneratedImage] = []

        for _ in range(request.num_images):
            generation_id = await self._create_generation(request)
            generation = await self.client.wait_for_generation(generation_id)
            images.append(self._parse_image(generation))

        return ImageGenerationResponse(images=images, model=self.model_id)

    async def _create_generation(self, request: ImageGenerationRequest) -> str:
        payload = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Avoid: {request.negative_prompt}" if request.negative_prompt else None,
            ),
            "aspect_ratio": closest_aspect_ratio(request.width, request.height),
        }

        if request.seed is not None:
            payload["seed"] = request.seed
        if request.extra_params:
            payload.update(request.extra_params)

        generation = await self.client.create_generation("/generations/image", payload)
        generation_id = generation.get("id")
        if not generation_id:
            raise ProviderError(
                message="Luma image generation did not return an id",
                provider="luma",
                model=self.model_id,
            )
        return str(generation_id)

    def _parse_image(self, generation: dict) -> GeneratedImage:
        state = str(generation.get("state", "")).lower()
        if state != "completed":
            message = (
                generation.get("failure_reason")
                or generation.get("error")
                or "Luma image generation failed"
            )
            raise ProviderError(
                message=str(message),
                provider="luma",
                model=self.model_id,
            )

        assets = generation.get("assets") or {}
        image_url = assets.get("image")
        if not image_url:
            raise InvalidRequestError(
                message="Luma image generation completed without an image asset",
                provider="luma",
                model=self.model_id,
            )

        return GeneratedImage(
            image=ImageContent(url=image_url, format="png"),
        )
