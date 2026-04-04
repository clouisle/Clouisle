"""
Runway text-to-video adapter.
"""

from __future__ import annotations

from typing import Any

from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    TaskStatus,
    VideoContent,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.models.model import Model

from ..media_utils import append_prompt_directives
from ..runway_client import RunwayClient
from .base import BaseVideoAdapter

_TEXT_TO_VIDEO_MODELS = {"gen4.5", "veo3", "veo3.1", "veo3.1_fast"}
_TEXT_TO_VIDEO_RATIOS = {
    "16:9": "1280:720",
    "9:16": "720:1280",
}


class RunwayVideoAdapter(BaseVideoAdapter):
    """Runway task-based video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = RunwayClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        task = await self.client.create_task(*self._build_request(request))
        task_id = task.get("id")
        if not task_id:
            raise ProviderError(
                message="Runway video task did not return an id",
                provider="runway",
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

    def _build_request(
        self, request: VideoGenerationRequest
    ) -> tuple[str, dict[str, Any]]:
        prompt = append_prompt_directives(
            request.prompt,
            f"Style: {request.style}" if request.style else None,
            f"Camera movement: {request.camera_motion}"
            if request.camera_motion
            else None,
        )
        duration = int(round(request.duration))

        if self.model_id not in _TEXT_TO_VIDEO_MODELS:
            raise InvalidRequestError(
                message=f"Model {self.model_id} does not support text-to-video on Runway",
                provider="runway",
                model=self.model_id,
            )

        payload = {
            "model": self.model_id,
            "promptText": prompt,
            "ratio": _TEXT_TO_VIDEO_RATIOS.get(
                request.aspect_ratio, _TEXT_TO_VIDEO_RATIOS["16:9"]
            ),
            "duration": duration,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.extra_params:
            payload.update(request.extra_params)
        return "/v1/text_to_video", payload

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").upper()
        if status in {"SUCCEEDED", "COMPLETED"}:
            return TaskStatus.COMPLETED
        if status in {"FAILED", "THROTTLED"}:
            return TaskStatus.FAILED
        if status in {"CANCELED", "CANCELLED"}:
            return TaskStatus.CANCELLED
        if status in {"PENDING", "QUEUED"}:
            return TaskStatus.PENDING
        return TaskStatus.PROCESSING

    def _extract_video_url(self, task: dict[str, Any]) -> str | None:
        output = task.get("output")
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str):
                    return item
                if isinstance(item, dict):
                    url = item.get("url") or item.get("uri")
                    if isinstance(url, str):
                        return url
        if isinstance(output, dict):
            for key in ("video", "url", "uri"):
                url = output.get(key)
                if isinstance(url, str):
                    return url
            videos = output.get("videos")
            if isinstance(videos, list) and videos:
                first = videos[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, dict):
                    url = first.get("url") or first.get("uri")
                    if isinstance(url, str):
                        return url
        return None

    def _extract_error(self, task: dict[str, Any]) -> str | None:
        error = task.get("failure") or task.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        if error is not None:
            return str(error)
        return None
