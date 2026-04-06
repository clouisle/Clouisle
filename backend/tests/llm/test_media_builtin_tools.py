from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools import tool_registry
from app.llm.tools.builtin.media import (
    build_image_llm_result,
    build_video_llm_result,
    generate_image,
    generate_video,
    register_media_tools,
)
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationResponse,
    TaskStatus,
    VideoContent,
    VideoGenerationResponse,
)


@pytest.mark.anyio
async def test_generate_image_uses_agent_defaults():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "google/gemini-2.5-flash-image",
            "default_width": 1536,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(url="https://example.com/cat.png", format="png"),
                revised_prompt="A refined cat portrait",
                seed=7,
            )
        ],
        model="google/gemini-2.5-flash-image",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(return_value=response),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_image",
            AsyncMock(
                return_value=ImageContent(
                    url="/api/v1/upload/files/generated-images/2026/03/cat.png",
                    format="png",
                )
            ),
        ),
    ):
        result = await generate_image(
            prompt="A cat portrait",
            num_images=1,
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.width == 1536
    assert request.height == 1024
    assert (
        mock_generate.await_args.kwargs["model_id"] == "google/gemini-2.5-flash-image"
    )
    assert result.display_result["kind"] == "media.image"
    assert result.display_result["success"] is True
    assert (
        result.display_result["images"][0]["image"]["url"]
        == "/api/v1/upload/files/generated-images/2026/03/cat.png"
    )
    assert result.llm_result.startswith("Image generation succeeded")


@pytest.mark.anyio
async def test_generate_video_polls_until_completed():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={
            "default_model_ref": "runway/gen4.5",
            "default_duration": 5,
            "max_duration": 10,
            "default_aspect_ratio": "16:9",
            "poll_interval_ms": 1,
            "poll_timeout_s": 1,
        },
    )
    initial_response = VideoGenerationResponse(
        task_id="vid_123",
        status=TaskStatus.PENDING,
        model="runway/gen4.5",
    )
    completed_response = VideoGenerationResponse(
        task_id="vid_123",
        status=TaskStatus.COMPLETED,
        model="runway/gen4.5",
        video=VideoContent(url="https://example.com/video.mp4", format="mp4"),
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_video",
            AsyncMock(return_value=initial_response),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.model_manager.get_video_status",
            AsyncMock(return_value=completed_response),
        ) as mock_status,
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_video",
            AsyncMock(
                return_value=VideoContent(
                    url="/api/v1/upload/files/generated-videos/2026/03/video.mp4",
                    format="mp4",
                )
            ),
        ),
        patch(
            "app.llm.tools.builtin.media.asyncio.sleep",
            AsyncMock(return_value=None),
        ),
    ):
        result = await generate_video(
            prompt="A cinematic robot walking through rain",
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.duration == 5
    assert request.aspect_ratio == "16:9"
    mock_status.assert_awaited_once_with("vid_123", model_id="runway/gen4.5")
    assert result.display_result["kind"] == "media.video"
    assert result.display_result["status"] == TaskStatus.COMPLETED.value
    assert (
        result.display_result["video"]["url"]
        == "/api/v1/upload/files/generated-videos/2026/03/video.mp4"
    )
    assert result.llm_result.startswith("Video generation succeeded")


@pytest.mark.anyio
async def test_generate_image_normalizes_inline_base64_to_backend_url():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "google/gemini-2.5-flash-image",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(base64="dGVzdA==", format="png"),
            )
        ],
        model="google/gemini-2.5-flash-image",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(return_value=response),
        ),
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_image",
            AsyncMock(
                return_value=ImageContent(
                    url="/api/v1/upload/files/generated-images/2026/03/test.png",
                    format="png",
                )
            ),
        ) as mock_normalize,
    ):
        result = await generate_image(prompt="A cat portrait", agent=agent)

    mock_normalize.assert_awaited_once()
    image_payload = result.display_result["images"][0]["image"]
    assert (
        image_payload["url"] == "/api/v1/upload/files/generated-images/2026/03/test.png"
    )
    assert image_payload["base64"] is None
    assert image_payload["file_path"] is None


def test_build_media_llm_summaries_are_compact():
    image_summary = build_image_llm_result(
        "A detailed portrait of a cat under moonlight",
        ImageGenerationResponse(
            images=[
                GeneratedImage(
                    image=ImageContent(
                        url="/api/v1/upload/files/generated-images/2026/03/test.png"
                    )
                )
            ],
            model="google/gemini-2.5-flash-image",
        ),
    )
    video_summary = build_video_llm_result(
        "A cinematic robot walking through rain",
        VideoGenerationResponse(
            task_id="vid_123",
            status=TaskStatus.PROCESSING,
            model="runway/gen4.5",
        ),
    )

    assert "base64" not in image_summary
    assert "/api/v1/upload/files/" not in image_summary
    assert image_summary.startswith("Image generation succeeded")
    assert (
        video_summary
        == "Video generation started. Task vid_123 is processing. Prompt: A cinematic robot walking through rain"
    )


def test_media_tools_do_not_expose_model_override_parameter():
    register_media_tools()
    image_tool = tool_registry.get_tool("generate_image")
    video_tool = tool_registry.get_tool("generate_video")

    assert image_tool is not None
    assert video_tool is not None
    assert all(param.name != "model_ref" for param in image_tool.parameters)
    assert all(param.name != "model_ref" for param in video_tool.parameters)
