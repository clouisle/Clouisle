"""
Kling text-to-video adapter.
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

from ..kling_client import KlingClient
from ..media_utils import append_prompt_directives, image_content_to_raw_base64
from .base import BaseVideoAdapter


class KlingVideoAdapter(BaseVideoAdapter):
    """Kling AI video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = KlingClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        payload = self._build_payload(request)
        task_type = "image2video" if request.start_image is not None else "text2video"
        task = await self.client.create_task(f"/v1/videos/{task_type}", payload)
        task_id = task.get("task_id")
        if not task_id:
            raise ProviderError(
                message=t("kling_task_missing_id"),
                provider="kling",
                model=self.model_id,
            )
        return await self.get_status(self._encode_task_id(str(task_id), task_type))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        task_type, raw_task_id = self._decode_task_id(task_id)
        task = await self.client.get_task(raw_task_id, task_type=task_type)
        status = self._map_status(task.get("task_status"))
        video_url = self._extract_video_url(task)
        return VideoGenerationResponse(
            task_id=task_id,
            status=status,
            video=VideoContent(url=video_url, format="mp4") if video_url else None,
            error=None if status != TaskStatus.FAILED else self._extract_error(task),
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
            ),
            "duration": int(round(request.duration)),
            "aspect_ratio": request.aspect_ratio,
        }

        if request.start_image is not None:
            payload["image"] = image_content_to_raw_base64(
                request.start_image,
                provider="kling",
                model=self.model_id,
                field_name="image",
            )

        if request.seed is not None:
            payload["seed"] = request.seed

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _encode_task_id(self, task_id: str, task_type: str) -> str:
        if task_type == "text2video":
            return task_id
        return f"{task_type}:{task_id}"

    def _decode_task_id(self, task_id: str) -> tuple[str, str]:
        if ":" not in task_id:
            return "text2video", task_id
        task_type, raw_task_id = task_id.split(":", 1)
        if task_type in {"text2video", "image2video"} and raw_task_id:
            return task_type, raw_task_id
        return "text2video", task_id

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").lower()
        if status == "succeed":
            return TaskStatus.COMPLETED
        if status == "failed":
            return TaskStatus.FAILED
        if status == "submitted":
            return TaskStatus.PENDING
        return TaskStatus.PROCESSING

    def _extract_video_url(self, task: dict[str, Any]) -> str | None:
        task_result = task.get("task_result")
        if not isinstance(task_result, dict):
            return None
        videos = task_result.get("videos")
        if isinstance(videos, list) and videos:
            first = videos[0]
            if isinstance(first, dict):
                url = first.get("url")
                if isinstance(url, str):
                    return url
        return None

    def _extract_error(self, task: dict[str, Any]) -> str | None:
        error = task.get("task_status_msg")
        if error is not None:
            return str(error)
        return None
