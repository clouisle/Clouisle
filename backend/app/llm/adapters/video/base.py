"""
Video generation adapter base classes.
"""

from abc import ABC, abstractmethod

from app.core.i18n import t
from app.llm.errors import InvalidRequestError
from app.llm.types import VideoGenerationRequest, VideoGenerationResponse


class BaseVideoAdapter(ABC):
    """Base class for text-to-video adapters."""

    def _ensure_reference_images_supported(self, request: VideoGenerationRequest) -> None:
        if request.start_image is None:
            return
        raise InvalidRequestError(
            message=t("video_reference_images_not_supported_for_model"),
            field="start_image",
        )

    @abstractmethod
    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        """Start a video generation task."""

    @abstractmethod
    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        """Fetch the latest task status."""
