"""
Luma text-to-video adapter.
"""

from __future__ import annotations

from typing import Any

from app.core.i18n import t
from app.llm.errors import ProviderError
from app.llm.types import (
    TaskStatus,
    VideoContent,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.models.model import Model

from ..luma_client import LumaClient
from ..media_utils import append_prompt_directives, require_remote_url
from .base import BaseVideoAdapter


class LumaVideoAdapter(BaseVideoAdapter):
    """Luma Dream Machine video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = LumaClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        if request.start_image is None:
            self._ensure_reference_images_supported(request)
        payload = self._build_payload(request)
        generation = await self.client.create_generation("/generations", payload)
        generation_id = generation.get("id")
        if not generation_id:
            raise ProviderError(
                message=t("luma_generation_missing_id"),
                provider="luma",
                model=self.model_id,
            )
        return await self.get_status(str(generation_id))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        generation = await self.client.get_generation(task_id)
        status = self._map_status(generation.get("state"))
        video_url = self._extract_video_url(generation)
        return VideoGenerationResponse(
            task_id=task_id,
            status=status,
            video=VideoContent(url=video_url, format="mp4") if video_url else None,
            error=None
            if status != TaskStatus.FAILED
            else self._extract_error(generation),
            model=self.model_id,
        )

    def _build_payload(self, request: VideoGenerationRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Camera movement: {request.camera_motion}"
                if request.camera_motion
                else None,
                f"Motion intensity: {request.motion_intensity}"
                if request.motion_intensity is not None
                else None,
            ),
            "duration": self._format_duration(request.duration),
            "aspect_ratio": request.aspect_ratio,
        }

        if request.start_image is not None:
            payload["keyframes"] = {
                "frame0": {
                    "type": "image",
                    "url": require_remote_url(
                        request.start_image,
                        provider="luma",
                        model=self.model_id,
                        field_name="start_image",
                    ),
                }
            }

        if request.seed is not None:
            payload["seed"] = request.seed

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _format_duration(self, duration: float) -> str:
        rounded = int(duration) if float(duration).is_integer() else round(duration, 1)
        return f"{rounded}s"

    def _map_status(self, raw_state: Any) -> TaskStatus:
        state = str(raw_state or "").lower()
        if state == "completed":
            return TaskStatus.COMPLETED
        if state == "failed":
            return TaskStatus.FAILED
        if state in {"queued", "pending"}:
            return TaskStatus.PENDING
        if state in {"cancelled", "canceled"}:
            return TaskStatus.CANCELLED
        return TaskStatus.PROCESSING

    def _extract_video_url(self, generation: dict[str, Any]) -> str | None:
        assets = generation.get("assets") or {}
        video = assets.get("video")
        if isinstance(video, str):
            return video
        if isinstance(video, dict):
            for key in ("url", "uri"):
                value = video.get(key)
                if isinstance(value, str):
                    return value
        return None

    def _extract_error(self, generation: dict[str, Any]) -> str | None:
        error = generation.get("failure_reason") or generation.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if error is not None:
            return str(error)
        return None
