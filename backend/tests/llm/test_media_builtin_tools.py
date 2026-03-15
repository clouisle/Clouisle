from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools import tool_registry
from app.llm.tools.builtin.media import generate_image, generate_video, register_media_tools
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

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image",
        AsyncMock(return_value=response),
    ) as mock_generate:
        result = await generate_image(
            prompt="A cat portrait",
            num_images=1,
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.width == 1536
    assert request.height == 1024
    assert mock_generate.await_args.kwargs["model_id"] == "google/gemini-2.5-flash-image"
    assert result["kind"] == "media.image"
    assert result["success"] is True
    assert result["images"][0]["image"]["url"] == "https://example.com/cat.png"


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

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_video",
        AsyncMock(return_value=initial_response),
    ) as mock_generate, patch(
        "app.llm.tools.builtin.media.model_manager.get_video_status",
        AsyncMock(return_value=completed_response),
    ) as mock_status, patch(
        "app.llm.tools.builtin.media.asyncio.sleep",
        AsyncMock(return_value=None),
    ):
        result = await generate_video(
            prompt="A cinematic robot walking through rain",
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.duration == 5
    assert request.aspect_ratio == "16:9"
    mock_status.assert_awaited_once_with("vid_123", model_id="runway/gen4.5")
    assert result["kind"] == "media.video"
    assert result["status"] == TaskStatus.COMPLETED.value
    assert result["video"]["url"] == "https://example.com/video.mp4"


def test_media_tools_do_not_expose_model_override_parameter():
    register_media_tools()
    image_tool = tool_registry.get_tool("generate_image")
    video_tool = tool_registry.get_tool("generate_video")

    assert image_tool is not None
    assert video_tool is not None
    assert all(param.name != "model_ref" for param in image_tool.parameters)
    assert all(param.name != "model_ref" for param in video_tool.parameters)
