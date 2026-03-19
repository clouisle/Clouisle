"""
DashScope (Wan/Qwen) text-to-video adapter.
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
from ..dashscope_video_client import DashScopeVideoClient
from .base import BaseVideoAdapter


class DashScopeVideoAdapter(BaseVideoAdapter):
    """DashScope (Wan) video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = DashScopeVideoClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        payload = self._build_payload(request)
        result = await self.client.create_task(payload)
        output = result.get("output", {})
        task_id = output.get("task_id")
        if not task_id:
            raise ProviderError(
                message="DashScope task did not return a task_id",
                provider="qwen",
                model=self.model_id,
            )
        return await self.get_status(str(task_id))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        task = await self.client.get_task(task_id)
        output = task.get("output", {})
        status = self._map_status(output.get("task_status"))
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
            f"Camera movement: {request.camera_motion}" if request.camera_motion else None,
        )
        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": {"prompt": prompt},
            "parameters": {},
        }

        if request.aspect_ratio:
            payload["parameters"]["size"] = request.aspect_ratio
        if request.duration:
            payload["parameters"]["duration"] = request.duration

        if request.seed is not None:
            payload["parameters"]["seed"] = request.seed

        if request.extra_params:
            payload["parameters"].update(request.extra_params)

        return payload

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").upper()
        if status == "SUCCEEDED":
            return TaskStatus.COMPLETED
        if status == "FAILED":
            return TaskStatus.FAILED
        if status == "RUNNING":
            return TaskStatus.PROCESSING
        if status == "PENDING":
            return TaskStatus.PENDING
        return TaskStatus.PENDING

    def _extract_video_url(self, task: dict[str, Any]) -> str | None:
        output = task.get("output")
        if isinstance(output, dict):
            url = output.get("video_url")
            if isinstance(url, str):
                return url
        return None

    def _extract_error(self, task: dict[str, Any]) -> str | None:
        output = task.get("output")
        if isinstance(output, dict):
            msg = output.get("message")
            if msg is not None:
                return str(msg)
        msg = task.get("message")
        if msg is not None:
            return str(msg)
        return None
