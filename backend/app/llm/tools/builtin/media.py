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
from collections.abc import Sequence
from typing import Any

from app.core.i18n import t
from app.llm import model_manager
from app.llm.adapters.media_utils import parse_image_data_url
from app.models.model import ModelType
from app.services.error_messages import resolve_user_visible_error
from app.llm.types import (
    GeneratedImage,
    ImageContent,
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
OPENAI_COMPATIBLE_IMAGE_PROVIDERS = {"openai", "azure_openai", "custom"}
OPENAI_DALLE_IMAGE_QUALITY_VALUES: Sequence[str] = ("standard", "hd")
OPENAI_DALLE_IMAGE_QUALITY_MAP = {
    "high": "hd",
    "standard": "standard",
    "hd": "hd",
}
OPENAI_GPT_IMAGE_QUALITY_VALUES: Sequence[str] = (
    "low",
    "medium",
    "high",
    "auto",
    "standard",
    "hd",
)
OPENAI_GPT_IMAGE_QUALITY_MAP = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "auto": "auto",
    "standard": "standard",
    "hd": "hd",
}


def _normalize_status(status: TaskStatus | str) -> str:
    return status.value if hasattr(status, "value") else str(status)


async def _get_image_model_id(model_ref: str | None) -> str | None:
    if not model_ref:
        return None

    try:
        model_config = await model_manager._get_model_config(
            model_ref,
            ModelType.TEXT_TO_IMAGE,
        )
    except Exception:
        return model_ref.split("/", 1)[1] if "/" in model_ref else None

    return getattr(model_config, "model_id", None)


def _get_agent_module_config(agent: Any, field_name: str) -> dict[str, Any]:
    if not agent:
        return {}
    value = getattr(agent, field_name, None) or {}
    return value if isinstance(value, dict) else {}


def _validate_allowed_providers(
    model_ref: str | None,
    config: dict[str, Any],
) -> None:
    allowed_providers = config.get("allowed_providers") or []
    if not allowed_providers or not model_ref or "/" not in model_ref:
        return

    provider = model_ref.split("/", 1)[0]
    if provider not in allowed_providers:
        raise ValueError(t("media_provider_not_allowed_for_agent", provider=provider))


def _get_provider_from_model_ref(model_ref: str | None) -> str | None:
    if not model_ref or "/" not in model_ref:
        return None
    return model_ref.split("/", 1)[0]


async def _normalize_image_quality(
    quality: str | None,
    *,
    model_ref: str | None,
) -> str | None:
    if quality is None:
        return None

    normalized_quality = quality.strip().lower()
    if not normalized_quality:
        return None

    provider = _get_provider_from_model_ref(model_ref)
    if provider not in OPENAI_COMPATIBLE_IMAGE_PROVIDERS:
        return quality

    model_id = await _get_image_model_id(model_ref)
    if model_id and model_id.startswith("gpt-image"):
        mapped_quality = OPENAI_GPT_IMAGE_QUALITY_MAP.get(normalized_quality)
        supported_values = OPENAI_GPT_IMAGE_QUALITY_VALUES
    else:
        mapped_quality = OPENAI_DALLE_IMAGE_QUALITY_MAP.get(normalized_quality)
        supported_values = OPENAI_DALLE_IMAGE_QUALITY_VALUES

    if mapped_quality is None:
        raise ValueError(
            t(
                "image_generation_invalid_quality",
                quality=quality,
                supported=", ".join(supported_values),
            )
        )
    return mapped_quality


def _get_image_source_value(image: Any, key: str) -> Any:
    if isinstance(image, dict):
        return image.get(key)
    return getattr(image, key, None)


def _chat_image_to_generation_image(image: Any, *, index: int) -> ImageContent:
    base64_value = _get_image_source_value(image, "base64")
    if isinstance(base64_value, str) and base64_value:
        parsed = parse_image_data_url(base64_value)
        if parsed:
            payload, image_format = parsed
            return ImageContent(base64=payload, format=image_format or "png")
        image_format = _get_image_source_value(image, "format") or "png"
        return ImageContent(base64=base64_value, format=image_format)

    url = _get_image_source_value(image, "url")
    if isinstance(url, str) and url:
        parsed = parse_image_data_url(url)
        if parsed:
            payload, image_format = parsed
            return ImageContent(base64=payload, format=image_format or "png")

    raise ValueError(t("image_reference_invalid_uploaded_image", index=index))


def _deduplicate_indexes(indexes: Sequence[Any]) -> list[int]:
    selected: list[int] = []
    seen: set[int] = set()
    for raw_index in indexes:
        if isinstance(raw_index, bool):
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index not in seen:
            selected.append(index)
            seen.add(index)
    return selected


def _resolve_generation_reference_images(
    *,
    images: list[dict[str, Any]] | None,
    reference_image_indexes: Sequence[Any] | None,
    current_images: Sequence[Any] | None,
) -> list[ImageContent] | None:
    if images and reference_image_indexes:
        raise ValueError(t("image_reference_images_conflict"))
    if images:
        return [ImageContent.model_validate(image) for image in images]
    if reference_image_indexes is None:
        return None

    selected_indexes = _deduplicate_indexes(reference_image_indexes)
    if not selected_indexes:
        return None
    if not current_images:
        raise ValueError(t("image_reference_no_uploaded_images"))

    resolved: list[ImageContent] = []
    available_count = len(current_images)
    for index in selected_indexes:
        if index < 1 or index > available_count:
            raise ValueError(
                t(
                    "image_reference_image_index_out_of_range",
                    index=index,
                    count=available_count,
                )
            )
        resolved.append(
            _chat_image_to_generation_image(current_images[index - 1], index=index)
        )
    return resolved


def _resolve_start_image_reference(
    *,
    start_image_index: Any,
    current_images: Sequence[Any] | None,
) -> ImageContent | None:
    if start_image_index is None:
        return None
    reference_images = _resolve_generation_reference_images(
        images=None,
        reference_image_indexes=[start_image_index],
        current_images=current_images,
    )
    return reference_images[0] if reference_images else None


class ToolExecutionResult(dict):
    """Structured tool result for UI persistence and LLM replay."""

    def __init__(self, *, display_result: dict[str, Any], llm_result: str) -> None:
        super().__init__(display_result=display_result, llm_result=llm_result)

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
        normalized_image = await media_asset_service.normalize_image(generated.image)
        if normalized_image is None:
            continue
        normalized_images.append(
            GeneratedImage(
                image=normalized_image,
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
        return t("image_generation_failed", error=error)

    count = len(response.images) if response and response.images else 0
    model = response.model if response else None
    prompt_excerpt = prompt.strip().replace("\n", " ")[:120]
    return t(
        "image_generation_succeeded",
        count=count,
        model=model or "-",
        prompt=prompt_excerpt,
    )


def build_video_llm_result(
    prompt: str,
    response: VideoGenerationResponse | None = None,
    *,
    error: str | None = None,
) -> str:
    status = _normalize_status(response.status) if response else TaskStatus.FAILED.value
    if error or status == TaskStatus.FAILED.value:
        message = (
            error
            or (response.error if response else None)
            or t("unknown_error_generic")
        )
        return t("video_generation_failed", error=message)

    prompt_excerpt = prompt.strip().replace("\n", " ")[:120]
    if response is not None and status in PENDING_VIDEO_STATUSES:
        return t(
            "video_generation_started",
            task_id=response.task_id,
            status=status,
            prompt=prompt_excerpt,
        )

    return t(
        "video_generation_succeeded",
        model=(response.model if response and response.model else "-"),
        prompt=prompt_excerpt,
    )


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
    reference_image_indexes: list[int] | None = None,
    extra_params: dict[str, Any] | None = None,
    agent: Any | None = None,
    current_images: list[Any] | None = None,
) -> dict[str, Any]:
    """Generate images through the unified model manager."""
    resolved_model_ref: str | None = None
    try:
        if agent and not getattr(agent, "enable_image_generation", False):
            raise ValueError(t("image_generation_not_enabled_for_agent"))

        config = _get_agent_module_config(agent, "image_generation_config")
        resolved_model_ref = config.get("default_model_ref") or None
        _validate_allowed_providers(resolved_model_ref, config)

        max_images = int(config.get("max_images", 4))
        final_num_images = min(num_images, max_images)

        reference_images = _resolve_generation_reference_images(
            images=images,
            reference_image_indexes=reference_image_indexes,
            current_images=current_images,
        )
        if reference_images and not config.get("allow_reference_images", True):
            raise ValueError(t("image_reference_images_disabled"))

        normalized_quality = await _normalize_image_quality(
            quality,
            model_ref=resolved_model_ref,
        )
        default_width = config.get("default_width")
        default_height = config.get("default_height")
        legacy_size = config.get("size")
        if (default_width is None or default_height is None) and isinstance(
            legacy_size, str
        ):
            size_parts = legacy_size.split("x", 1)
            if len(size_parts) == 2:
                parsed_width, parsed_height = size_parts
                if default_width is None and parsed_width.isdigit():
                    default_width = int(parsed_width)
                if default_height is None and parsed_height.isdigit():
                    default_height = int(parsed_height)

        request = ImageGenerationRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width or int(default_width or 1024),
            height=height or int(default_height or 1024),
            num_images=final_num_images,
            style=style,
            quality=normalized_quality,
            seed=seed,
            images=reference_images,
            extra_params=extra_params,
        )
        image_response = await model_manager.generate_image(
            request,
            model_id=resolved_model_ref,
        )
        response = await normalize_image_generation_response(image_response)
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
        error_message = resolve_user_visible_error(
            str(exc),
            fallback_key="unknown_error_generic",
        )
        display_result = build_image_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            error=error_message,
        )
        return build_media_tool_execution_result(
            display_result,
            build_image_llm_result(
                prompt,
                error=error_message,
            ),
        )


async def generate_video(
    prompt: str,
    duration: float | None = None,
    aspect_ratio: str | None = None,
    motion_intensity: float | None = None,
    camera_motion: str | None = None,
    style: str | None = None,
    seed: int | None = None,
    start_image_index: int | None = None,
    extra_params: dict[str, Any] | None = None,
    agent: Any | None = None,
    current_images: list[Any] | None = None,
) -> dict[str, Any]:
    """Generate videos through the unified model manager."""
    resolved_model_ref: str | None = None
    poll_interval_ms = 3000
    poll_timeout_s = 120

    try:
        if agent and not getattr(agent, "enable_video_generation", False):
            raise ValueError(t("video_generation_not_enabled_for_agent"))

        config = _get_agent_module_config(agent, "video_generation_config")
        resolved_model_ref = config.get("default_model_ref") or None
        _validate_allowed_providers(resolved_model_ref, config)

        final_duration = duration or float(config.get("default_duration", 5.0))
        max_duration = float(config.get("max_duration", 10.0))
        if final_duration > max_duration:
            raise ValueError(
                t(
                    "video_generation_duration_exceeds_agent_limit",
                    max_duration=f"{max_duration:.1f}",
                )
            )

        poll_interval_ms = int(config.get("poll_interval_ms", 3000))
        poll_timeout_s = int(config.get("poll_timeout_s", 120))

        start_image = _resolve_start_image_reference(
            start_image_index=start_image_index,
            current_images=current_images,
        )

        request = VideoGenerationRequest(
            prompt=prompt,
            duration=final_duration,
            aspect_ratio=aspect_ratio or config.get("default_aspect_ratio", "16:9"),
            motion_intensity=motion_intensity,
            camera_motion=camera_motion,
            style=style,
            seed=seed,
            start_image=start_image,
            extra_params=extra_params,
        )
        response: VideoGenerationResponse | None = await model_manager.generate_video(
            request,
            model_id=resolved_model_ref,
        )

        if (
            response is not None
            and _normalize_status(response.status) in PENDING_VIDEO_STATUSES
        ):
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
        error_message = resolve_user_visible_error(
            str(exc),
            fallback_key="unknown_error_generic",
        )
        display_result = build_video_tool_result(
            prompt,
            model_ref=resolved_model_ref,
            poll_interval_ms=poll_interval_ms,
            poll_timeout_s=poll_timeout_s,
            error=error_message,
        )
        return build_media_tool_execution_result(
            display_result,
            build_video_llm_result(
                prompt,
                error=error_message,
            ),
        )


def register_media_tools() -> None:
    """Register builtin media generation tools."""

    tool_registry.register(
        name="generate_image",
        description=(
            "Generate one or more images from a prompt. Use this when the user asks "
            "you to create illustrations, product shots, mockups, concept art, "
            "or edit/reference-based image outputs. Uploaded chat images are "
            "available as 1-based indexes; use reference_image_indexes for only "
            "the specific uploaded images the user wants to reference."
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
                description=(
                    "Optional explicit reference image objects. For images uploaded "
                    "in the current chat, use reference_image_indexes instead."
                ),
                items={"type": "object"},
            ),
            ToolParameter(
                name="reference_image_indexes",
                type="array",
                description=(
                    "1-based indexes of uploaded chat images to use as references. "
                    "Choose only the specific images needed, e.g. [3] for uploaded "
                    "image #3 or [5] for the last image when five images were uploaded."
                ),
                items={"type": "integer"},
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
            "for cinematic motion, animated scenes, or motion-based concept clips. "
            "When the user asks to use an uploaded image as the video's first frame, "
            "set start_image_index to that uploaded image's 1-based index. Current "
            "video providers may reject image references explicitly if unsupported."
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
                name="start_image_index",
                type="integer",
                description=(
                    "1-based index of the uploaded chat image to use as the video's "
                    "starting frame/reference image when the selected video model supports it."
                ),
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
