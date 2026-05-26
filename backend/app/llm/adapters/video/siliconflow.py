"""
SiliconFlow text-to-video adapter.
"""

from __future__ import annotations

from typing import Any

from app.core.i18n import t
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    TaskStatus,
    VideoContent,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.models.model import Model

from ..media_utils import append_prompt_directives, image_content_to_data_uri
from ..siliconflow_client import SiliconFlowClient
from .base import BaseVideoAdapter

_ASPECT_RATIO_TO_SIZE: dict[str, str] = {
    "16:9": "1280x720",
    "9:16": "720x1280",
    "1:1": "720x720",
    "4:3": "960x720",
    "3:4": "720x960",
    "21:9": "1260x540",
}


_SILICONFLOW_IMAGE_TO_VIDEO_MODEL_MARKERS = ("i2v", "image-to-video")


class SiliconFlowVideoAdapter(BaseVideoAdapter):
    """SiliconFlow video-generation adapter."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.client = SiliconFlowClient(model_config)
        self.model_id = model_config.model_id

    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        payload = self._build_payload(request)
        result = await self.client.create_task(payload)
        request_id = result.get("requestId")
        if not request_id:
            raise ProviderError(
                message=t("siliconflow_task_missing_request_id"),
                provider="siliconflow",
                model=self.model_id,
            )
        return await self.get_status(str(request_id))

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
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": append_prompt_directives(
                request.prompt,
                f"Style: {request.style}" if request.style else None,
                f"Camera movement: {request.camera_motion}"
                if request.camera_motion
                else None,
            ),
        }

        image_size = _ASPECT_RATIO_TO_SIZE.get(
            request.aspect_ratio or "16:9", "1280x720"
        )
        payload["image_size"] = image_size

        if request.seed is not None:
            payload["seed"] = request.seed

        if request.start_image is not None:
            self._ensure_image_to_video_model()
            payload["image"] = image_content_to_data_uri(
                request.start_image,
                provider="siliconflow",
                model=self.model_id,
                field_name="start_image",
            )

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _ensure_image_to_video_model(self) -> None:
        normalized = self.model_id.lower()
        if any(
            marker in normalized for marker in _SILICONFLOW_IMAGE_TO_VIDEO_MODEL_MARKERS
        ):
            return
        raise InvalidRequestError(
            message=t("video_reference_images_not_supported_for_model"),
            field="start_image",
            provider="siliconflow",
            model=self.model_id,
        )

    def _map_status(self, raw_status: Any) -> TaskStatus:
        status = str(raw_status or "")
        if status == "Succeed":
            return TaskStatus.COMPLETED
        if status == "Failed":
            return TaskStatus.FAILED
        if status == "InProgress":
            return TaskStatus.PROCESSING
        return TaskStatus.PENDING

    def _extract_video_url(self, task: dict[str, Any]) -> str | None:
        results = task.get("results")
        if not isinstance(results, dict):
            return None
        videos = results.get("videos")
        if isinstance(videos, list) and videos:
            first = videos[0]
            if isinstance(first, dict):
                url = first.get("url")
                if isinstance(url, str):
                    return url
        return None

    def _extract_error(self, task: dict[str, Any]) -> str | None:
        reason = task.get("reason")
        if reason is not None:
            return str(reason)
        return None
