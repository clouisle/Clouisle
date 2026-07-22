from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.builtin.media import (
    _deduplicate_indexes,
    _get_provider_from_model_ref,
    _normalize_image_quality,
    generate_image,
    generate_video,
    normalize_image_generation_response,
    normalize_video_generation_response,
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
async def test_media_helpers_handle_empty_and_non_openai_inputs():
    assert _get_provider_from_model_ref(None) is None
    assert _get_provider_from_model_ref("model-only") is None
    assert await _normalize_image_quality("  ", model_ref="openai/dall-e-3") is None
    assert await _normalize_image_quality(" Ultra ", model_ref="google/image") == (
        " Ultra "
    )
    assert _deduplicate_indexes([False, None, "bad"]) == []
    assert await normalize_image_generation_response(None) is None
    assert await normalize_video_generation_response(None) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "agent", "expected_error"),
    [
        (
            generate_image,
            SimpleNamespace(enable_image_generation=False),
            "Image generation is not enabled",
        ),
        (
            generate_video,
            SimpleNamespace(enable_video_generation=False),
            "Video generation is not enabled",
        ),
    ],
)
async def test_media_tools_reject_disabled_agent_modules(tool, agent, expected_error):
    with patch.object(
        tool.__globals__["model_manager"], tool.__name__, AsyncMock()
    ) as manager_call:
        result = await tool(prompt="test", agent=agent)

    manager_call.assert_not_awaited()
    assert result.display_result["success"] is False
    assert expected_error in result.display_result["error"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "agent"),
    [
        (
            generate_image,
            SimpleNamespace(
                enable_image_generation=True,
                image_generation_config={
                    "default_model_ref": "blocked/image-model",
                    "allowed_providers": ["allowed"],
                },
            ),
        ),
        (
            generate_video,
            SimpleNamespace(
                enable_video_generation=True,
                video_generation_config={
                    "default_model_ref": "blocked/video-model",
                    "allowed_providers": ["allowed"],
                },
            ),
        ),
    ],
)
async def test_media_tools_reject_disallowed_provider(tool, agent):
    with patch.object(
        tool.__globals__["model_manager"], tool.__name__, AsyncMock()
    ) as manager_call:
        result = await tool(prompt="test", agent=agent)

    manager_call.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "blocked" in result.display_result["error"]


@pytest.mark.anyio
async def test_generate_image_dispatches_reference_request_and_skips_empty_asset():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "custom/dall-e-3",
            "size": "640x480",
        },
    )
    manager_response = ImageGenerationResponse(
        images=[
            GeneratedImage(image=ImageContent(base64="dropped")),
            GeneratedImage(image=ImageContent(url="https://example.com/kept.png")),
        ],
        model="dall-e-3",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(return_value=manager_response),
        ) as manager_call,
        patch(
            "app.llm.tools.builtin.media.model_manager._get_model_config",
            AsyncMock(return_value=SimpleNamespace(model_id="dall-e-3")),
        ),
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_image",
            AsyncMock(
                side_effect=[
                    None,
                    ImageContent(url="/api/v1/upload/files/generated/kept.png"),
                ]
            ),
        ) as storage_call,
    ):
        result = await generate_image(
            prompt="edit",
            quality="HIGH",
            reference_image_indexes=[True, "bad", "1", 1],
            current_images=[SimpleNamespace(base64="cmVm", format="webp")],
            agent=agent,
        )

    request = manager_call.await_args.args[0]
    assert manager_call.await_args.kwargs == {"model_id": "custom/dall-e-3"}
    assert (request.width, request.height, request.quality) == (640, 480, "hd")
    assert [(image.base64, image.format) for image in request.images] == [
        ("cmVm", "webp")
    ]
    assert storage_call.await_count == 2
    assert result.display_result["success"] is True
    assert len(result.display_result["images"]) == 1


@pytest.mark.anyio
async def test_generate_image_rejects_missing_and_invalid_references():
    manager_call = AsyncMock()
    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image", manager_call
    ):
        no_uploads = await generate_image(
            prompt="edit",
            reference_image_indexes=[1],
            current_images=[],
        )
        invalid_upload = await generate_image(
            prompt="edit",
            reference_image_indexes=[1],
            current_images=[{"url": "https://example.com/not-uploaded.png"}],
        )

    manager_call.assert_not_awaited()
    assert "No conversation images" in no_uploads.display_result["error"]
    assert "usable image data" in invalid_upload.display_result["error"]


@pytest.mark.anyio
async def test_generate_video_dispatches_start_image_and_normalizes_success():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={
            "default_model_ref": "allowed/video-model",
            "allowed_providers": ["allowed"],
            "default_duration": 4,
            "max_duration": 6,
            "default_aspect_ratio": "9:16",
        },
    )
    manager_response = VideoGenerationResponse(
        task_id="task-1",
        status=TaskStatus.COMPLETED,
        video=VideoContent(url="https://example.com/video.mp4"),
        model="video-model",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_video",
            AsyncMock(return_value=manager_response),
        ) as manager_call,
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_video",
            AsyncMock(
                return_value=VideoContent(
                    url="/api/v1/upload/files/generated/video.mp4"
                )
            ),
        ) as storage_call,
    ):
        result = await generate_video(
            prompt="animate",
            start_image_index="1",
            current_images=[{"base64": "data:image/jpeg;base64,c3RhcnQ="}],
            agent=agent,
        )

    request = manager_call.await_args.args[0]
    assert manager_call.await_args.kwargs == {"model_id": "allowed/video-model"}
    assert (request.duration, request.aspect_ratio) == (4, "9:16")
    assert (request.start_image.base64, request.start_image.format) == (
        "c3RhcnQ=",
        "jpg",
    )
    storage_call.assert_awaited_once_with(manager_response.video)
    assert result.display_result["video"]["url"].endswith("/generated/video.mp4")


@pytest.mark.anyio
async def test_generate_video_returns_pending_after_poll_timeout():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={"poll_interval_ms": 0, "poll_timeout_s": 1},
    )
    pending = VideoGenerationResponse(
        task_id="task-1",
        status=TaskStatus.PENDING,
        model="video-model",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_video",
            AsyncMock(return_value=pending),
        ),
        patch(
            "app.llm.tools.builtin.media.model_manager.get_video_status",
            AsyncMock(return_value=pending),
        ) as status_call,
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_video",
            AsyncMock(return_value=None),
        ),
        patch("app.llm.tools.builtin.media.asyncio.sleep", AsyncMock()),
        patch(
            "app.llm.tools.builtin.media.time.monotonic",
            side_effect=[0, 0, 1],
        ),
    ):
        result = await generate_video(prompt="test", agent=agent)

    status_call.assert_awaited_once()
    assert result.display_result["requires_polling"] is True
    assert result.display_result["video"] is None


@pytest.mark.anyio
async def test_generate_video_reports_limit_and_manager_errors():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={"max_duration": 2},
    )
    manager_call = AsyncMock(side_effect=RuntimeError("provider unavailable"))

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_video", manager_call
    ):
        too_long = await generate_video(prompt="test", duration=3, agent=agent)
        manager_error = await generate_video(prompt="test", duration=1, agent=agent)

    assert manager_call.await_count == 1
    assert "agent limit" in too_long.display_result["error"].lower()
    assert manager_error.display_result["success"] is False
    assert "provider unavailable" in manager_error.display_result["error"]
