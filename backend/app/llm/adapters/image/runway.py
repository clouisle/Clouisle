"""
Runway text-to-image adapter.
"""

from __future__ import annotations

from typing import Any

from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.models.model import Model

from ..media_utils import append_prompt_directives, closest_aspect_ratio
from ..runway_client import RunwayClient
from .base import BaseImageAdapter

_RUNWAY_IMAGE_RATIOS = {
    "21:9": "2112:912",
    "16:9": "1920:1080",
    "4:3": "1440:1080",
    "1:1": "1080:1080",
    "3:4": "1080:1440",
    "9:16": "1080:1920",
}


class RunwayImageAdapter(BaseImageAdapter):
    """Runway task-based text-to-image adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = RunwayClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        images: list[GeneratedImage] = []

        for index in range(request.num_images):
            task_id = await self._create_task(request, index)
            task = await self.client.wait_for_task(task_id)
            images.extend(self._parse_images(task))

        return ImageGenerationResponse(images=images, model=self.model_id)

    async def _create_task(self, request: ImageGenerationRequest, index: int) -> str:
        ratio = closest_aspect_ratio(request.width, request.height)
        payload: dict[str, Any] = {
            "model": self.model_id,
            "promptText": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Avoid: {request.negative_prompt}"
                if request.negative_prompt
                else None,
            ),
            "ratio": _RUNWAY_IMAGE_RATIOS.get(ratio, _RUNWAY_IMAGE_RATIOS["1:1"]),
        }

        if request.seed is not None:
            payload["seed"] = request.seed + index

        extra_params = getattr(request, "extra_params", None) or {}
        payload.update(extra_params)

        task = await self.client.create_task("/v1/text_to_image", payload)
        task_id = task.get("id")
        if not task_id:
            raise ProviderError(
                message="Runway image task did not return an id",
                provider="runway",
                model=self.model_id,
            )
        return str(task_id)

    def _parse_images(self, task: dict[str, Any]) -> list[GeneratedImage]:
        status = str(task.get("status", "")).upper()
        if status != "SUCCEEDED":
            message = (
                task.get("failure") or task.get("error") or "Runway image task failed"
            )
            raise ProviderError(
                message=str(message),
                provider="runway",
                model=self.model_id,
            )

        raw_output = task.get("output") or []
        urls: list[str] = []
        if isinstance(raw_output, list):
            for item in raw_output:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    url = item.get("url") or item.get("uri")
                    if isinstance(url, str):
                        urls.append(url)
        elif isinstance(raw_output, dict):
            for key in ("images", "output"):
                value = raw_output.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            urls.append(item)
                        elif isinstance(item, dict):
                            url = item.get("url") or item.get("uri")
                            if isinstance(url, str):
                                urls.append(url)

        if not urls:
            raise InvalidRequestError(
                message="Runway image task completed without image output",
                provider="runway",
                model=self.model_id,
            )

        return [
            GeneratedImage(
                image=ImageContent(url=url, format="png"),
            )
            for url in urls
        ]
