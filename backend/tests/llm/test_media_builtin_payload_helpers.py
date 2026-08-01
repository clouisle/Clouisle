from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.builtin.media import (
    _deduplicate_indexes,
    _resolve_generation_reference_images,
    build_image_tool_result,
    build_video_tool_result,
    normalize_image_generation_response,
)
from app.schemas.response import BusinessError
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationResponse,
    TaskStatus,
    VideoContent,
    VideoGenerationResponse,
)


def test_media_payload_builders_normalize_status_and_serialized_images():
    image_response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(base64="aW1hZ2U=", format="png"),
                revised_prompt="refined",
                seed=42,
            )
        ],
        model="provider/image-model",
    )
    video_response = VideoGenerationResponse(
        task_id="task-1",
        status=TaskStatus.PENDING,
        progress=0.25,
        video=VideoContent(url="/video.mp4", format="mp4"),
        model="provider/video-model",
        estimated_time=12,
    )

    image_result = build_image_tool_result("draw", image_response)
    video_result = build_video_tool_result("animate", video_response)

    assert image_result["success"] is True
    assert image_result["model_ref"] == "provider/image-model"
    assert image_result["images"] == [
        {
            "image": image_response.images[0].image.model_dump(mode="json"),
            "revised_prompt": "refined",
            "seed": 42,
        }
    ]
    assert video_result["status"] == "pending"
    assert video_result["requires_polling"] is True
    assert video_result["video"] == video_response.video.model_dump(mode="json")


def test_reference_indexes_discard_invalid_values_and_reject_missing_sources():
    assert _deduplicate_indexes(["2", 2, True, None, "bad", 1.8, 1]) == [2, 1]

    with pytest.raises(BusinessError) as exc_info:
        _resolve_generation_reference_images(
            images=None,
            reference_image_indexes=[1],
            current_images=None,
        )
    assert exc_info.value.msg_key == "image_reference_no_uploaded_images"

    with pytest.raises(BusinessError) as exc_info:
        _resolve_generation_reference_images(
            images=[{"url": "https://example.com/ref.png"}],
            reference_image_indexes=[1],
            current_images=[{"url": "data:image/png;base64,cmVm"}],
        )
    assert exc_info.value.msg_key == "image_reference_images_conflict"


@pytest.mark.anyio
async def test_image_response_normalization_omits_unpersistable_images():
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(image=ImageContent(url="https://example.com/keep.png")),
            GeneratedImage(image=ImageContent(url="https://example.com/drop.png")),
        ],
        model="image-model",
    )
    persisted = ImageContent(url="/api/v1/upload/files/keep.png", format="png")

    with patch(
        "app.llm.tools.builtin.media.media_asset_service.normalize_image",
        AsyncMock(side_effect=[persisted, None]),
    ) as normalize_image:
        normalized = await normalize_image_generation_response(response)

    assert normalize_image.await_count == 2
    assert normalized == ImageGenerationResponse(
        images=[GeneratedImage(image=persisted)], model="image-model"
    )
