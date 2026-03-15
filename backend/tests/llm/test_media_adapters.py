import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.image import create_image_adapter
from app.llm.adapters.image.google import GoogleImageAdapter
from app.llm.adapters.image.luma import LumaImageAdapter
from app.llm.adapters.image.openai import OpenAIImageAdapter
from app.llm.adapters.image.runway import RunwayImageAdapter
from app.llm.adapters.image.stability import StabilityImageAdapter
from app.llm.adapters.video import create_video_adapter
from app.llm.adapters.video.luma import LumaVideoAdapter
from app.llm.adapters.video.runway import RunwayVideoAdapter
from app.llm.errors import InvalidRequestError
from app.llm.manager import ModelManager
from app.llm.types import (
    ImageContent,
    ImageGenerationRequest,
    TaskStatus,
    VideoGenerationRequest,
    VideoGenerationResponse,
)
from app.models.model import ModelType


def build_model(provider: str, model_id: str, **extra):
    return SimpleNamespace(
        provider=provider,
        model_id=model_id,
        api_key="test-key",
        base_url=extra.pop("base_url", "https://example.com"),
        config=extra.pop("config", {}),
        default_params=extra.pop("default_params", {}),
        max_output_tokens=extra.pop("max_output_tokens", None),
        **extra,
    )


class TestImageFactory:
    def test_supports_custom_and_task_based_image_providers(self):
        assert isinstance(
            create_image_adapter(build_model("custom", "image-model", base_url="https://custom.example/v1")),
            OpenAIImageAdapter,
        )
        assert isinstance(
            create_image_adapter(build_model("runway", "gen4_image")),
            RunwayImageAdapter,
        )
        assert isinstance(
            create_image_adapter(build_model("luma", "photon-1")),
            LumaImageAdapter,
        )
        assert isinstance(
            create_image_adapter(build_model("stability", "stable-image-core")),
            StabilityImageAdapter,
        )
        assert isinstance(
            create_image_adapter(build_model("google", "gemini-2.5-flash-image")),
            GoogleImageAdapter,
        )

    def test_custom_image_provider_requires_base_url(self):
        with pytest.raises(InvalidRequestError):
            create_image_adapter(build_model("custom", "image-model", base_url=None))


class TestStabilityImageAdapter:
    def test_selects_endpoint_from_model_id(self):
        assert (
            StabilityImageAdapter(build_model("stability", "stable-image-ultra"))._build_path()
            == "/v2beta/stable-image/generate/ultra"
        )
        assert (
            StabilityImageAdapter(build_model("stability", "stable-image-core"))._build_path()
            == "/v2beta/stable-image/generate/core"
        )
        assert (
            StabilityImageAdapter(build_model("stability", "sd3.5-large"))._build_path()
            == "/v2beta/stable-image/generate/sd3"
        )

    def test_builds_sd3_form_payload(self):
        adapter = StabilityImageAdapter(
            build_model("stability", "sd3.5-large", base_url="https://api.stability.ai/v1")
        )

        payload = adapter._build_form_data(
            ImageGenerationRequest(
                prompt="A dramatic city skyline",
                negative_prompt="blurry",
                width=1536,
                height=1024,
                style="photographic",
                seed=7,
                extra_params={"cfg_scale": 6, "output_format": "webp"},
            ),
            output_format="webp",
            seed_offset=1,
        )

        assert adapter._build_url(adapter._build_path()) == (
            "https://api.stability.ai/v2beta/stable-image/generate/sd3"
        )
        assert payload["model"] == "sd3.5-large"
        assert payload["aspect_ratio"] == "3:2"
        assert payload["style_preset"] == "photographic"
        assert payload["negative_prompt"] == "blurry"
        assert payload["cfg_scale"] == 6
        assert payload["output_format"] == "webp"
        assert payload["seed"] == 8


class TestGoogleImageAdapter:
    def test_prefers_first_class_reference_images_field(self):
        adapter = GoogleImageAdapter(build_model("google", "gemini-2.5-flash-image"))

        reference_images, overrides = adapter._split_extra_params(
            ImageGenerationRequest(
                prompt="Edit this image",
                images=[ImageContent(url="https://example.com/primary.png")],
                extra_params={
                    "images": [{"url": "https://example.com/legacy.png"}],
                    "person_generation": "ALLOW_ALL",
                },
            )
        )

        assert [image.url for image in reference_images] == [
            "https://example.com/primary.png"
        ]
        assert "images" not in overrides
        assert overrides["person_generation"] == "ALLOW_ALL"

    def test_supports_legacy_reference_images_from_extra_params(self):
        adapter = GoogleImageAdapter(build_model("google", "gemini-2.5-flash-image"))

        reference_images, overrides = adapter._split_extra_params(
            ImageGenerationRequest(
                prompt="Edit this image",
                extra_params={
                    "images": [{"url": "https://example.com/legacy.png"}],
                    "person_generation": "ALLOW_ALL",
                },
            )
        )

        assert [image.url for image in reference_images] == [
            "https://example.com/legacy.png"
        ]
        assert "images" not in overrides
        assert overrides["person_generation"] == "ALLOW_ALL"

    def test_builds_generation_config_for_nano_banana_models(self):
        adapter = GoogleImageAdapter(build_model("google", "gemini-3-pro-image-preview"))

        config = adapter._build_generation_config(
            ImageGenerationRequest(
                prompt="A crisp product shot",
                negative_prompt="low quality",
                width=2048,
                height=1024,
                seed=11,
                extra_params={
                    "person_generation": "ALLOW_ADULT",
                    "response_modalities": ["IMAGE"],
                },
            ),
            seed_offset=1,
            overrides={
                "person_generation": "ALLOW_ADULT",
                "response_modalities": ["IMAGE"],
            },
        )

        assert config["seed"] == 12
        assert config["response_modalities"] == ["TEXT", "IMAGE"]
        assert config["image_config"]["aspect_ratio"] == "16:9"
        assert config["image_config"]["image_size"] == "2K"
        assert config["image_config"]["person_generation"] == "ALLOW_ADULT"

    def test_parses_google_image_response(self):
        adapter = GoogleImageAdapter(build_model("google", "gemini-2.5-flash-image"))
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    finish_reason="STOP",
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(text="Refined prompt", inline_data=None),
                            SimpleNamespace(
                                text=None,
                                inline_data=SimpleNamespace(
                                    data=b"png-bytes",
                                    mime_type="image/png",
                                ),
                            ),
                        ]
                    ),
                )
            ]
        )

        images = adapter._parse_generated_images(response, fallback_seed=9)

        assert len(images) == 1
        assert images[0].revised_prompt == "Refined prompt"
        assert images[0].seed == 9
        assert images[0].image.format == "png"


class TestVideoFactory:
    def test_supports_runway_and_luma_video_providers(self):
        assert isinstance(
            create_video_adapter(build_model("runway", "gen4.5")),
            RunwayVideoAdapter,
        )
        assert isinstance(
            create_video_adapter(build_model("luma", "ray-2")),
            LumaVideoAdapter,
        )


class TestModelManagerVideoRouting:
    def test_generate_video_uses_text_to_video_without_input_image(self):
        manager = ModelManager()
        fake_model = build_model("runway", "gen4.5", id="model-1", name="Runway", is_enabled=True)
        fake_response = VideoGenerationResponse(
            task_id="task-1",
            status=TaskStatus.PENDING,
            model="gen4.5",
        )
        fake_adapter = SimpleNamespace(generate=AsyncMock(return_value=fake_response))

        with (
            patch.object(manager, "_get_model_config", AsyncMock(return_value=fake_model)) as mock_get_model,
            patch("app.llm.manager.create_video_adapter", return_value=fake_adapter),
        ):
            result = asyncio.run(
                manager.generate_video({"prompt": "A robot walking in rain"})
            )

        assert result.task_id == "task-1"
        mock_get_model.assert_awaited_once_with(None, ModelType.TEXT_TO_VIDEO)

    def test_generate_video_rejects_image_input(self):
        manager = ModelManager()
        with pytest.raises(InvalidRequestError):
            asyncio.run(
                manager.generate_video(
                    {
                        "prompt": "Animate this still image",
                        "image": {"url": "https://example.com/input.png"},
                    }
                )
            )


class TestRunwayVideoAdapter:
    def test_builds_text_to_video_request_for_supported_model(self):
        adapter = RunwayVideoAdapter(build_model("runway", "gen4.5"))

        path, payload = adapter._build_request(
            VideoGenerationRequest(prompt="A drifting spaceship", duration=5, aspect_ratio="16:9")
        )

        assert path == "/v1/text_to_video"
        assert payload["ratio"] == "1280:720"
        assert payload["duration"] == 5

    def test_rejects_text_request_for_non_text_video_model(self):
        adapter = RunwayVideoAdapter(build_model("runway", "gen4_turbo"))

        with pytest.raises(InvalidRequestError):
            adapter._build_request(VideoGenerationRequest(prompt="No image provided"))
