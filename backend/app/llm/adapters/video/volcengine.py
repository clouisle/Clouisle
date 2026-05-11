"""
Volcengine (Seedance) text-to-video adapter.
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

from ..media_utils import append_prompt_directives
from ..volcengine_client import VolcengineClient
from .base import BaseVideoAdapter


class VolcengineVideoAdapter(BaseVideoAdapter):
    """Volcengine (Seedance) video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = VolcengineClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        payload = self._build_payload(request)
        result = await self.client.create_task(payload)
        task_id = result.get("id")
        if not task_id:
            raise ProviderError(
                message=t("volcengine_task_missing_id"),
                provider="volcengine",
                model=self.model_id,
            )
        return await self.get_status(str(task_id))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        task = await self.client.get_task(task_id)
        status = self._map_status(task.get("status"))
        video_url = self._extract_video_url(task)
        return VideoGenerationResponse(
            task_id=task_id,
            status=status,
            video=VideoContent(url=video_url, format="mp4") if video_url else None,
            error=None if status != TaskStatus.FAILED else self._extract_error(task),
            model=self.model_id,
        )

    def _build_payload(self, request: VideoGenerationRequest) -> dict[str, Any]:
        prompt = append_prompt_directives(
            request.prompt,
            f"Style: {request.style}" if request.style else None,
            f"Camera movement: {request.camera_motion}"
            if request.camera_motion
            else None,
        )
        payload: dict[str, Any] = {
            "model": self.model_id,
            "content": [{"type": "text", "text": prompt}],
            "parameters": {},
        }

        if request.duration:
            payload["parameters"]["duration"] = request.duration
        if request.aspect_ratio:
            payload["parameters"]["aspect_ratio"] = request.aspect_ratio

        if request.seed is not None:
            payload["parameters"]["seed"] = request.seed

        if request.extra_params:
            payload["parameters"].update(request.extra_params)

        return payload

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").lower()
        if status == "succeeded":
            return TaskStatus.COMPLETED
        if status == "failed":
            return TaskStatus.FAILED
        if status == "cancelled":
            return TaskStatus.CANCELLED
        if status == "running":
            return TaskStatus.PROCESSING
        return TaskStatus.PENDING

    def _extract_video_url(self, task: dict[str, Any]) -> str | None:
        content = task.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                video_url = first.get("video_url")
                if isinstance(video_url, dict):
                    url = video_url.get("url")
                    if isinstance(url, str):
                        return url
        return None

    def _extract_error(self, task: dict[str, Any]) -> str | None:
        error = task.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if error is not None:
            return str(error)
        return None
