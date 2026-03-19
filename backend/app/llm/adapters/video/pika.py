"""
Pika text-to-video adapter.
"""

from __future__ import annotations

from typing import Any

from app.llm.errors import ProviderError
from app.llm.types import (
    TaskStatus,
    VideoContent,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.models.model import Model

from ..media_utils import append_prompt_directives
from ..pika_client import PikaClient
from .base import BaseVideoAdapter


class PikaVideoAdapter(BaseVideoAdapter):
    """Pika video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = PikaClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        payload = self._build_payload(request)
        generation = await self.client.create_generation("/generate", payload)
        generation_id = generation.get("id")
        if not generation_id:
            raise ProviderError(
                message="Pika generation did not return an id",
                provider="pika",
                model=self.model_id,
            )
        return await self.get_status(str(generation_id))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        generation = await self.client.get_generation(task_id)
        status = self._map_status(generation.get("status"))
        video_url = self._extract_video_url(generation)
        return VideoGenerationResponse(
            task_id=task_id,
            status=status,
            video=VideoContent(url=video_url, format="mp4") if video_url else None,
            error=None if status != TaskStatus.FAILED else self._extract_error(generation),
            model=self.model_id,
        )

    def _build_payload(self, request: VideoGenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Camera movement: {request.camera_motion}" if request.camera_motion else None,
            ),
            "duration": request.duration,
            "aspectRatio": request.aspect_ratio,
        }

        if request.seed is not None:
            payload["seed"] = request.seed

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").lower()
        if status == "finished":
            return TaskStatus.COMPLETED
        if status == "failed":
            return TaskStatus.FAILED
        if status == "pending":
            return TaskStatus.PENDING
        return TaskStatus.PROCESSING

    def _extract_video_url(self, generation: dict[str, Any]) -> str | None:
        videos = generation.get("videos")
        if isinstance(videos, list) and videos:
            first = videos[0]
            if isinstance(first, dict):
                url = first.get("resultUrl")
                if isinstance(url, str):
                    return url
        return None

    def _extract_error(self, generation: dict[str, Any]) -> str | None:
        error = generation.get("message") or generation.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if error is not None:
            return str(error)
        return None
