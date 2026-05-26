from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.model import ModelType

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
async def test_generate_image_uses_legacy_size_default_when_width_height_missing():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "openai/gpt-image-1",
            "size": "1792x1024",
            "max_images": 4,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(url="https://example.com/cat.png", format="png"),
            )
        ],
        model="gpt-image-1",
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
        await generate_image(
            prompt="A cat portrait",
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.width == 1792
    assert request.height == 1024


@pytest.mark.anyio
async def test_generate_image_clamps_num_images_to_agent_limit():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "openai/gpt-image-1",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 1,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(url="https://example.com/cat.png", format="png"),
            )
        ],
        model="gpt-image-1",
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
            num_images=4,
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.num_images == 1
    assert result.display_result["success"] is True


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


@pytest.mark.anyio
async def test_generate_video_passes_selected_start_image_reference():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={
            "default_model_ref": "siliconflow/Wan2.1-T2V-14B",
            "default_duration": 5,
            "max_duration": 10,
            "default_aspect_ratio": "16:9",
            "poll_interval_ms": 1,
            "poll_timeout_s": 1,
        },
    )
    response = VideoGenerationResponse(
        task_id="vid_123",
        status=TaskStatus.COMPLETED,
        model="siliconflow/Wan2.1-T2V-14B",
        video=VideoContent(url="https://example.com/video.mp4", format="mp4"),
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_video",
            AsyncMock(return_value=response),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.media_asset_service.normalize_video",
            AsyncMock(
                return_value=VideoContent(
                    url="/api/v1/upload/files/generated-videos/out.mp4"
                )
            ),
        ),
    ):
        result = await generate_video(
            prompt="Animate the second upload",
            start_image_index=2,
            current_images=[
                {"url": "data:image/png;base64,Zmlyc3Q="},
                {"url": "data:image/webp;base64,c2Vjb25k"},
            ],
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert result.display_result["success"] is True
    assert request.start_image is not None
    assert request.start_image.base64 == "c2Vjb25k"
    assert request.start_image.format == "webp"
    assert request.start_image.url is None


@pytest.mark.anyio
async def test_generate_video_rejects_out_of_range_start_image_index():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={
            "default_model_ref": "siliconflow/Wan2.1-T2V-14B",
            "default_duration": 5,
            "max_duration": 10,
            "default_aspect_ratio": "16:9",
            "poll_interval_ms": 1,
            "poll_timeout_s": 1,
        },
    )

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_video",
        AsyncMock(),
    ) as mock_generate:
        result = await generate_video(
            prompt="Animate image 3",
            start_image_index=3,
            current_images=[{"url": "data:image/png;base64,cmVm"}],
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "out of range" in result.display_result["error"]


@pytest.mark.anyio
async def test_generate_video_reports_unsupported_start_image_reference():
    agent = SimpleNamespace(
        enable_video_generation=True,
        video_generation_config={
            "default_model_ref": "siliconflow/Wan2.1-T2V-14B",
            "default_duration": 5,
            "max_duration": 10,
            "default_aspect_ratio": "16:9",
            "poll_interval_ms": 1,
            "poll_timeout_s": 1,
        },
    )

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_video",
        AsyncMock(
            side_effect=ValueError(
                "The selected video model does not support uploaded images as starting-frame references yet"
            )
        ),
    ) as mock_generate:
        result = await generate_video(
            prompt="Animate reference",
            start_image_index=1,
            current_images=[{"url": "data:image/png;base64,cmVm"}],
            agent=agent,
        )

    mock_generate.assert_awaited_once()
    assert result.display_result["success"] is False
    assert "does not support uploaded images" in result.display_result["error"]


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
    schema = video_tool.to_openai_schema()
    properties = schema["function"]["parameters"]["properties"]
    assert properties["start_image_index"]["type"] == "integer"
    assert all(param.name != "model_ref" for param in video_tool.parameters)


@pytest.mark.anyio
async def test_generate_image_normalizes_openai_compatible_quality_alias():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "openai/gpt-image-1",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(url="https://example.com/cat.png", format="png"),
            )
        ],
        model="gpt-image-1",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(return_value=response),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.model_manager._get_model_config",
            AsyncMock(
                return_value=SimpleNamespace(
                    model_id="gpt-image-1",
                    model_type=ModelType.TEXT_TO_IMAGE,
                )
            ),
        ),
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
            quality="high",
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.quality == "high"
    assert result.display_result["success"] is True


@pytest.mark.anyio
async def test_generate_image_rejects_invalid_openai_compatible_quality():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "openai/gpt-image-1",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": True,
        },
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.model_manager._get_model_config",
            AsyncMock(
                return_value=SimpleNamespace(
                    model_id="dall-e-3",
                    model_type=ModelType.TEXT_TO_IMAGE,
                )
            ),
        ),
    ):
        result = await generate_image(
            prompt="A cat portrait",
            quality="ultra",
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "Supported values: standard, hd" in result.display_result["error"]


@pytest.mark.anyio
async def test_generate_image_gpt_image_quality_falls_back_to_model_ref_suffix():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "openai/gpt-image-1",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": True,
        },
    )
    response = ImageGenerationResponse(
        images=[
            GeneratedImage(
                image=ImageContent(url="https://example.com/cat.png", format="png"),
            )
        ],
        model="gpt-image-1",
    )

    with (
        patch(
            "app.llm.tools.builtin.media.model_manager.generate_image",
            AsyncMock(return_value=response),
        ) as mock_generate,
        patch(
            "app.llm.tools.builtin.media.model_manager._get_model_config",
            AsyncMock(side_effect=RuntimeError("lookup failed")),
        ),
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
        await generate_image(
            prompt="A cat portrait",
            quality="medium",
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert request.quality == "medium"


@pytest.mark.anyio
async def test_generate_image_uses_selected_uploaded_image_reference():
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
        images=[GeneratedImage(image=ImageContent(url="https://example.com/out.png"))],
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
                    url="/api/v1/upload/files/generated-images/out.png"
                )
            ),
        ),
    ):
        result = await generate_image(
            prompt="Use the second image as reference",
            reference_image_indexes=[2],
            current_images=[
                {"url": "data:image/png;base64,Zmlyc3Q="},
                {"url": "data:image/jpeg;base64,c2Vjb25k"},
            ],
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert result.display_result["success"] is True
    assert len(request.images) == 1
    assert request.images[0].base64 == "c2Vjb25k"
    assert request.images[0].format == "jpg"
    assert request.images[0].url is None


@pytest.mark.anyio
async def test_generate_image_deduplicates_reference_indexes_in_order():
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
        images=[GeneratedImage(image=ImageContent(url="https://example.com/out.png"))],
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
                    url="/api/v1/upload/files/generated-images/out.png"
                )
            ),
        ),
    ):
        await generate_image(
            prompt="Use selected images",
            reference_image_indexes=[2, 2, 1],
            current_images=[
                {"url": "data:image/png;base64,Zmlyc3Q="},
                {"url": "data:image/webp;base64,c2Vjb25k"},
            ],
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert [image.base64 for image in request.images] == ["c2Vjb25k", "Zmlyc3Q="]
    assert [image.format for image in request.images] == ["webp", "png"]


@pytest.mark.anyio
async def test_generate_image_rejects_reference_image_conflict():
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

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image",
        AsyncMock(),
    ) as mock_generate:
        result = await generate_image(
            prompt="Use reference",
            images=[{"url": "https://example.com/ref.png"}],
            reference_image_indexes=[1],
            current_images=[{"url": "data:image/png;base64,cmVm"}],
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "not both" in result.display_result["error"]


@pytest.mark.anyio
async def test_generate_image_rejects_reference_index_out_of_range():
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

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image",
        AsyncMock(),
    ) as mock_generate:
        result = await generate_image(
            prompt="Use image 3",
            reference_image_indexes=[3],
            current_images=[{"url": "data:image/png;base64,cmVm"}],
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "out of range" in result.display_result["error"]


@pytest.mark.anyio
async def test_generate_image_preserves_explicit_images_input():
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
        images=[GeneratedImage(image=ImageContent(url="https://example.com/out.png"))],
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
                    url="/api/v1/upload/files/generated-images/out.png"
                )
            ),
        ),
    ):
        await generate_image(
            prompt="Use explicit reference",
            images=[{"url": "https://example.com/ref.png"}],
            agent=agent,
        )

    request = mock_generate.await_args.args[0]
    assert len(request.images) == 1
    assert request.images[0].url == "https://example.com/ref.png"


@pytest.mark.anyio
async def test_generate_image_rejects_reference_indexes_when_disabled():
    agent = SimpleNamespace(
        enable_image_generation=True,
        image_generation_config={
            "default_model_ref": "google/gemini-2.5-flash-image",
            "default_width": 1024,
            "default_height": 1024,
            "max_images": 4,
            "allow_reference_images": False,
        },
    )

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image",
        AsyncMock(),
    ) as mock_generate:
        result = await generate_image(
            prompt="Use reference",
            reference_image_indexes=[1],
            current_images=[{"url": "data:image/png;base64,cmVm"}],
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert (
        result.display_result["error"] == "Reference images are disabled for this agent"
    )


@pytest.mark.anyio
async def test_generate_image_rejects_unusable_uploaded_reference_image():
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

    with patch(
        "app.llm.tools.builtin.media.model_manager.generate_image",
        AsyncMock(),
    ) as mock_generate:
        result = await generate_image(
            prompt="Use reference",
            reference_image_indexes=[1],
            current_images=[{"url": "/api/v1/upload/files/images/2026/05/private.png"}],
            agent=agent,
        )

    mock_generate.assert_not_awaited()
    assert result.display_result["success"] is False
    assert "does not contain usable image data" in result.display_result["error"]


def test_generate_image_schema_includes_items_for_images_array():
    register_media_tools()
    image_tool = tool_registry.get_tool("generate_image")
    assert image_tool is not None

    schema = image_tool.to_openai_schema()
    properties = schema["function"]["parameters"]["properties"]
    images_prop = properties["images"]
    reference_indexes_prop = properties["reference_image_indexes"]
    assert images_prop["type"] == "array"
    assert "items" in images_prop
    assert images_prop["items"] == {"type": "object"}
    assert reference_indexes_prop["type"] == "array"
    assert reference_indexes_prop["items"] == {"type": "integer"}
