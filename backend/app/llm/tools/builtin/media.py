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
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResponse,
    VideoGenerationRequest,
    VideoGenerationResponse,
    TaskStatus,
)
from app.services.media_asset_service import media_asset_service

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


class ToolExecutionResult(dict):
    """Structured tool result for UI persistence and LLM replay."""

    @property
    def display_result(self) -> dict[str, Any]:
        return self["display_result"]

    @property
    def llm_result(self) -> str:
        return self["llm_result"]


async def normalize_image_generation_response(
    response: ImageGenerationResponse | None,
) -> ImageGenerationResponse | None:
    if response is None:
        return None

    normalized_images: list[GeneratedImage] = []
    for generated in response.images:
        normalized_images.append(
            GeneratedImage(
                image=(await media_asset_service.normalize_image(generated.image)),
                revised_prompt=generated.revised_prompt,
                seed=generated.seed,
            )
        )

    return ImageGenerationResponse(images=normalized_images, model=response.model)


async def normalize_video_generation_response(
    response: VideoGenerationResponse | None,
) -> VideoGenerationResponse | None:
    if response is None:
        return None

    return VideoGenerationResponse(
        task_id=response.task_id,
        status=response.status,
        video=await media_asset_service.normalize_video(response.video),
        progress=response.progress,
        error=response.error,
        model=response.model,
        estimated_time=response.estimated_time,
    )


def build_image_tool_result(
    prompt: str,
    response: ImageGenerationResponse | None = None,
    *,
    model_ref: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    images = (
        [generated.model_dump(mode="json") for generated in response.images]
        if response and response.images
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


def build_image_llm_result(
    prompt: str,
    response: ImageGenerationResponse | None = None,
    *,
    error: str | None = None,
) -> str:
    if error:
        return f"Image generation failed: {error}"

    count = len(response.images) if response and response.images else 0
    model = response.model if response else None
    prompt_excerpt = prompt.strip().replace("\n", " ")[:120]
    model_suffix = f" using model {model}" if model else ""
    return (
        f"Image generation succeeded. Generated {count} image"
        f"{'s' if count != 1 else ''}{model_suffix}. Prompt: {prompt_excerpt}"
    )


def build_video_llm_result(
    prompt: str,
    response: VideoGenerationResponse | None = None,
    *,
    error: str | None = None,
) -> str:
    status = _normalize_status(response.status) if response else TaskStatus.FAILED.value
    if error or status == TaskStatus.FAILED.value:
        message = error or (response.error if response else None) or "unknown error"
        return f"Video generation failed: {message}"

    prompt_excerpt = prompt.strip().replace("\n", " ")[:120]
    if status in PENDING_VIDEO_STATUSES:
        return (
            f"Video generation started. Task {response.task_id} is {status}. "
            f"Prompt: {prompt_excerpt}"
        )

    model_suffix = f" using model {response.model}" if response and response.model else ""
    return f"Video generation succeeded{model_suffix}. Prompt: {prompt_excerpt}"


def build_media_tool_execution_result(
    display_result: dict[str, Any],
    llm_result: str,
) -> ToolExecutionResult:
    return ToolExecutionResult(display_result=display_result, llm_result=llm_result)


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
        response = await normalize_image_generation_response(response)
        display_result = build_image_tool_result(
            prompt,
            response,
            model_ref=resolved_model_ref,
        )
        return build_media_tool_execution_result(
            display_result,
            build_image_llm_result(prompt, response),
        )
    except Exception as exc:
        logger.exception("Image generation tool failed: %s", exc)
        display_result = build_image_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            error=str(exc),
        )
        return build_media_tool_execution_result(
            display_result,
            build_image_llm_result(prompt, error=str(exc)),
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

        response = await normalize_video_generation_response(response)
        display_result = build_video_tool_result(
            prompt,
            response,
            model_ref=resolved_model_ref,
            poll_interval_ms=poll_interval_ms,
            poll_timeout_s=poll_timeout_s,
        )
        return build_media_tool_execution_result(
            display_result,
            build_video_llm_result(prompt, response),
        )
    except Exception as exc:
        logger.exception("Video generation tool failed: %s", exc)
        display_result = build_video_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            poll_interval_ms=poll_interval_ms,
            poll_timeout_s=poll_timeout_s,
            error=str(exc),
        )
        return build_media_tool_execution_result(
            display_result,
            build_video_llm_result(prompt, error=str(exc)),
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
    "ToolExecutionResult",
    "build_image_llm_result",
    "build_image_tool_result",
    "build_media_tool_execution_result",
    "build_video_llm_result",
    "build_video_tool_result",
    "generate_image",
    "generate_video",
    "normalize_image_generation_response",
    "normalize_video_generation_response",
    "register_media_tools",
]
