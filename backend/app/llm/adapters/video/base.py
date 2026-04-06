"""
Video generation adapter base classes.
"""

from abc import ABC, abstractmethod

from app.llm.types import VideoGenerationRequest, VideoGenerationResponse


class BaseVideoAdapter(ABC):
    """Base class for text-to-video adapters."""

    @abstractmethod
    async def generate(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationResponse:
        """Start a video generation task."""

    @abstractmethod
    async def get_status(self, task_id: str) -> VideoGenerationResponse:
        """Fetch the latest task status."""
