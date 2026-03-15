"""
Media generation builtin tools for agents.

These tools let the chat model call the existing image and video generation
pipeline through function calling, while keeping the returned payload stable
for frontend rendering.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.llm import model_manager
from app.llm.types import (
    ImageGenerationRequest,
    VideoGenerationRequest,
    VideoGenerationResponse,
    TaskStatus,
)

from ..registry import tool_registry, ToolParameter

logger = logging.getLogger(__name__)

PENDING_VIDEO_STATUSES = {TaskStatus.PENDING.value, TaskStatus.PROCESSING.value}


def _normalize_status(status: TaskStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _get_agent_module_config(agent: Any, field_name: str) -> dict[str, Any]:
    if not agent:
        return {}
    value = getattr(agent, field_name, None) or {}
    return value if isinstance(value, dict) else {}


def _validate_allowed_providers(
    model_ref: str | None,
    config: dict[str, Any],
    feature_label: str,
) -> None:
    allowed_providers = config.get("allowed_providers") or []
    if not allowed_providers or not model_ref or "/" not in model_ref:
        return

    provider = model_ref.split("/", 1)[0]
    if provider not in allowed_providers:
        raise ValueError(
            f"{feature_label} provider '{provider}' is not allowed for this agent"
        )


def build_image_tool_result(
    prompt: str,
    response: Any | None = None,
    *,
    model_ref: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    images = (
        [generated.model_dump(mode="json") for generated in response.images]
        if response and getattr(response, "images", None)
        else []
    )
    model = getattr(response, "model", None) if response else None
    return {
        "kind": "media.image",
        "success": error is None,
        "prompt": prompt,
        "model": model,
        "model_ref": model_ref or model,
        "images": images,
        "error": error,
    }


def build_video_tool_result(
    prompt: str,
    response: VideoGenerationResponse | None = None,
    *,
    model_ref: str | None = None,
    poll_interval_ms: int = 3000,
    poll_timeout_s: int = 120,
    error: str | None = None,
) -> dict[str, Any]:
    status = _normalize_status(response.status) if response else TaskStatus.FAILED.value
    model = response.model if response else None
    return {
        "kind": "media.video",
        "success": error is None and status != TaskStatus.FAILED.value,
        "prompt": prompt,
        "model": model,
        "model_ref": model_ref or model,
        "task_id": response.task_id if response else None,
        "status": status,
        "progress": response.progress if response else None,
        "video": response.video.model_dump(mode="json")
        if response and response.video
        else None,
        "estimated_time": response.estimated_time if response else None,
        "requires_polling": status in PENDING_VIDEO_STATUSES,
        "poll_interval_ms": poll_interval_ms,
        "poll_timeout_s": poll_timeout_s,
        "error": error or (response.error if response else None),
    }


async def generate_image(
    prompt: str,
    width: int | None = None,
    height: int | None = None,
    num_images: int = 1,
    style: str | None = None,
    quality: str | None = None,
    negative_prompt: str | None = None,
    seed: int | None = None,
    images: list[dict[str, Any]] | None = None,
    extra_params: dict[str, Any] | None = None,
    agent: Any | None = None,
) -> dict[str, Any]:
    """Generate images through the unified model manager."""
    resolved_model_ref: str | None = None
    try:
        if agent and not getattr(agent, "enable_image_generation", False):
            raise ValueError("Image generation is not enabled for this agent")

        config = _get_agent_module_config(agent, "image_generation_config")
        resolved_model_ref = config.get("default_model_ref") or None
        _validate_allowed_providers(
            resolved_model_ref, config, "Image generation"
        )

        if num_images > int(config.get("max_images", 4)):
            raise ValueError(
                f"Image generation request exceeds agent limit ({config.get('max_images', 4)})"
            )

        if images and not config.get("allow_reference_images", True):
            raise ValueError("Reference images are disabled for this agent")

        request = ImageGenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width or int(config.get("default_width", 1024)),
            height=height or int(config.get("default_height", 1024)),
            num_images=num_images,
            style=style,
            quality=quality,
            seed=seed,
            images=images,
            extra_params=extra_params,
        )
        response = await model_manager.generate_image(
            request,
            model_id=resolved_model_ref,
        )
        return build_image_tool_result(
            prompt,
            response,
            model_ref=resolved_model_ref,
        )
    except Exception as exc:
        logger.exception("Image generation tool failed: %s", exc)
        return build_image_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            error=str(exc),
        )


async def generate_video(
    prompt: str,
    duration: float | None = None,
    aspect_ratio: str | None = None,
    motion_intensity: float | None = None,
    camera_motion: str | None = None,
    style: str | None = None,
    seed: int | None = None,
    extra_params: dict[str, Any] | None = None,
    agent: Any | None = None,
) -> dict[str, Any]:
    """Generate videos through the unified model manager."""
    resolved_model_ref: str | None = None
    poll_interval_ms = 3000
    poll_timeout_s = 120

    try:
        if agent and not getattr(agent, "enable_video_generation", False):
            raise ValueError("Video generation is not enabled for this agent")

        config = _get_agent_module_config(agent, "video_generation_config")
        resolved_model_ref = config.get("default_model_ref") or None
        _validate_allowed_providers(
            resolved_model_ref, config, "Video generation"
        )

        final_duration = duration or float(config.get("default_duration", 5.0))
        max_duration = float(config.get("max_duration", 10.0))
        if final_duration > max_duration:
            raise ValueError(
                f"Video duration exceeds agent limit ({max_duration:.1f}s)"
            )

        poll_interval_ms = int(config.get("poll_interval_ms", 3000))
        poll_timeout_s = int(config.get("poll_timeout_s", 120))

        request = VideoGenerationRequest(
            prompt=prompt,
            duration=final_duration,
            aspect_ratio=aspect_ratio or config.get("default_aspect_ratio", "16:9"),
            motion_intensity=motion_intensity,
            camera_motion=camera_motion,
            style=style,
            seed=seed,
            extra_params=extra_params,
        )
        response = await model_manager.generate_video(
            request,
            model_id=resolved_model_ref,
        )

        if _normalize_status(response.status) in PENDING_VIDEO_STATUSES:
            deadline = time.monotonic() + poll_timeout_s
            while time.monotonic() < deadline:
                await asyncio.sleep(poll_interval_ms / 1000)
                response = await model_manager.get_video_status(
                    response.task_id,
                    model_id=resolved_model_ref,
                )
                if _normalize_status(response.status) not in PENDING_VIDEO_STATUSES:
                    break

        return build_video_tool_result(
            prompt,
            response,
            model_ref=resolved_model_ref,
            poll_interval_ms=poll_interval_ms,
            poll_timeout_s=poll_timeout_s,
        )
    except Exception as exc:
        logger.exception("Video generation tool failed: %s", exc)
        return build_video_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            poll_interval_ms=poll_interval_ms,
            poll_timeout_s=poll_timeout_s,
            error=str(exc),
        )


def register_media_tools() -> None:
    """Register builtin media generation tools."""

    tool_registry.register(
        name="generate_image",
        description=(
            "Generate one or more images from a prompt. Use this when the user asks "
            "you to create illustrations, product shots, mockups, concept art, "
            "or edit/reference-based image outputs."
        ),
        parameters=[
            ToolParameter(
                name="prompt",
                type="string",
                description="Image generation prompt",
                required=True,
            ),
            ToolParameter(
                name="width",
                type="integer",
                description="Output image width in pixels",
            ),
            ToolParameter(
                name="height",
                type="integer",
                description="Output image height in pixels",
            ),
            ToolParameter(
                name="num_images",
                type="integer",
                description="Number of images to generate",
            ),
            ToolParameter(
                name="style",
                type="string",
                description="Optional visual style hint",
            ),
            ToolParameter(
                name="quality",
                type="string",
                description="Optional quality tier",
            ),
            ToolParameter(
                name="negative_prompt",
                type="string",
                description="Optional negative prompt",
            ),
            ToolParameter(
                name="seed",
                type="integer",
                description="Optional random seed",
            ),
            ToolParameter(
                name="images",
                type="array",
                description="Optional reference images for edit/reference generation",
            ),
            ToolParameter(
                name="extra_params",
                type="object",
                description="Optional provider-specific parameters",
            ),
        ],
    )(generate_image)

    tool_registry.register(
        name="generate_video",
        description=(
            "Generate a short video clip from a prompt. Use this when the user asks "
            "for cinematic motion, animated scenes, or motion-based concept clips."
        ),
        parameters=[
            ToolParameter(
                name="prompt",
                type="string",
                description="Video generation prompt",
                required=True,
            ),
            ToolParameter(
                name="duration",
                type="number",
                description="Target video duration in seconds",
            ),
            ToolParameter(
                name="aspect_ratio",
                type="string",
                description="Output aspect ratio, e.g. 16:9 or 9:16",
            ),
            ToolParameter(
                name="motion_intensity",
                type="number",
                description="Motion intensity from 0 to 1 when supported",
            ),
            ToolParameter(
                name="camera_motion",
                type="string",
                description="Optional camera motion description",
            ),
            ToolParameter(
                name="style",
                type="string",
                description="Optional visual style hint",
            ),
            ToolParameter(
                name="seed",
                type="integer",
                description="Optional random seed",
            ),
            ToolParameter(
                name="extra_params",
                type="object",
                description="Optional provider-specific parameters",
            ),
        ],
    )(generate_video)


__all__ = [
    "PENDING_VIDEO_STATUSES",
    "build_image_tool_result",
    "build_video_tool_result",
    "generate_image",
    "generate_video",
    "register_media_tools",
]
