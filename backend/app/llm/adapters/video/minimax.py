"""MiniMax asynchronous video-generation adapter."""

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

from ..media_utils import append_prompt_directives, image_content_to_data_uri
from ..minimax_client import MiniMaxClient
from .base import BaseVideoAdapter

_MINIMAX_VIDEO_EXTRA_KEYS = {
    "aigc_watermark",
    "fast_pretreatment",
    "prompt_optimizer",
    "resolution",
}


class MiniMaxVideoAdapter(BaseVideoAdapter):
    """Generate and query MiniMax video tasks."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = MiniMaxClient(model_config)
        self.model_id = model_config.model_id
        self.provider = "minimax"

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        data = await self.client.request(
            "POST", "/video_generation", json=self._build_payload(request)
        )
        task_id = data.get("task_id")
        if not task_id:
            raise ProviderError(
                message=t("minimax_task_missing_id"),
                provider=self.provider,
                model=self.model_id,
            )
        return await self.get_status(str(task_id))

    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        task = await self.client.request(
            "GET",
            "/query/video_generation",
            params={"task_id": task_id},
            task_id=task_id,
        )
        status = self._map_status(task.get("status"))
        video = None
        error = None

        if status == TaskStatus.COMPLETED:
            file_id = task.get("file_id")
            if file_id:
                file_data = await self.client.request(
                    "GET",
                    "/files/retrieve",
                    params={"file_id": file_id},
                    task_id=task_id,
                )
                video_url = self._extract_video_url(file_data)
                if video_url:
                    video = VideoContent(url=video_url, format="mp4")
            if video is None:
                status = TaskStatus.FAILED
                error = t("minimax_video_response_missing_output")
        elif status == TaskStatus.FAILED:
            error = self._extract_error(task) or t("minimax_video_generation_failed")

        return VideoGenerationResponse(
            task_id=task_id,
            status=status,
            video=video,
            error=error,
            model=self.model_id,
        )

    def _build_payload(self, request: VideoGenerationRequest) -> dict[str, Any]:
        default_params = getattr(self.model_config, "default_params", None) or {}
        extra_params = request.extra_params or {}
        payload = {
            key: value
            for key, value in {**default_params, **extra_params}.items()
            if key in _MINIMAX_VIDEO_EXTRA_KEYS and value is not None
        }
        payload.update(
            {
                "model": self.model_id,
                "prompt": append_prompt_directives(
                    request.prompt,
                    f"Style: {request.style}" if request.style else None,
                    f"Camera movement: {request.camera_motion}"
                    if request.camera_motion
                    else None,
                ),
                "duration": request.duration,
            }
        )
        if request.start_image is not None:
            payload["first_frame_image"] = image_content_to_data_uri(
                request.start_image,
                provider=self.provider,
                model=self.model_id,
                field_name="start_image",
            )
        return payload

    @staticmethod
    def _map_status(raw_status: Any) -> TaskStatus:
        status = str(raw_status or "").lower()
        if status == "success":
            return TaskStatus.COMPLETED
        if status in {"fail", "failed"}:
            return TaskStatus.FAILED
        if status == "processing":
            return TaskStatus.PROCESSING
        return TaskStatus.PENDING

    @staticmethod
    def _extract_video_url(data: dict[str, Any]) -> str | None:
        file_data = data.get("file")
        if not isinstance(file_data, dict):
            return None
        url = file_data.get("download_url")
        return url if isinstance(url, str) and url else None

    @staticmethod
    def _extract_error(data: dict[str, Any]) -> str | None:
        base_resp = data.get("base_resp")
        if not isinstance(base_resp, dict):
            return None
        message = base_resp.get("status_msg")
        return message if isinstance(message, str) and message else None
