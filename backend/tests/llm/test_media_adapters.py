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
from app.llm.adapters.video.dashscope import DashScopeVideoAdapter
from app.llm.adapters.video.kling import KlingVideoAdapter
from app.llm.adapters.video.luma import LumaVideoAdapter
from app.llm.adapters.video.pika import PikaVideoAdapter
from app.llm.adapters.video.runway import RunwayVideoAdapter
from app.llm.adapters.video.siliconflow import SiliconFlowVideoAdapter
from app.llm.adapters.video.volcengine import VolcengineVideoAdapter
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

    def test_supports_kling_and_pika_video_providers(self):
        assert isinstance(
            create_video_adapter(build_model("kling", "kling-v1")),
            KlingVideoAdapter,
        )
        assert isinstance(
            create_video_adapter(build_model("pika", "pika-v1")),
            PikaVideoAdapter,
        )

    def test_supports_siliconflow_volcengine_qwen_video_providers(self):
        assert isinstance(
            create_video_adapter(build_model("siliconflow", "Wan2.1-T2V-14B")),
            SiliconFlowVideoAdapter,
        )
        assert isinstance(
            create_video_adapter(build_model("volcengine", "seedance-1-lite")),
            VolcengineVideoAdapter,
        )
        assert isinstance(
            create_video_adapter(build_model("qwen", "wan2.1-t2v-plus")),
            DashScopeVideoAdapter,
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


class TestKlingVideoAdapter:
    def test_builds_payload_with_integer_duration(self):
        adapter = KlingVideoAdapter(build_model("kling", "kling-v1"))

        payload = adapter._build_payload(
            VideoGenerationRequest(prompt="A sunset over mountains", duration=5.7, aspect_ratio="16:9")
        )

        assert payload["model"] == "kling-v1"
        assert payload["prompt"] == "A sunset over mountains"
        assert payload["duration"] == 6
        assert payload["aspect_ratio"] == "16:9"

    def test_maps_kling_statuses(self):
        adapter = KlingVideoAdapter(build_model("kling", "kling-v1"))

        assert adapter._map_status("submitted") == TaskStatus.PENDING
        assert adapter._map_status("processing") == TaskStatus.PROCESSING
        assert adapter._map_status("succeed") == TaskStatus.COMPLETED
        assert adapter._map_status("failed") == TaskStatus.FAILED
        assert adapter._map_status(None) == TaskStatus.PROCESSING

    def test_extracts_video_url_from_task_result(self):
        adapter = KlingVideoAdapter(build_model("kling", "kling-v1"))

        task = {"task_result": {"videos": [{"url": "https://cdn.kling.ai/video.mp4"}]}}
        assert adapter._extract_video_url(task) == "https://cdn.kling.ai/video.mp4"

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"task_result": {}}) is None

    def test_extracts_error_from_task_status_msg(self):
        adapter = KlingVideoAdapter(build_model("kling", "kling-v1"))

        assert adapter._extract_error({"task_status_msg": "Content policy violation"}) == "Content policy violation"
        assert adapter._extract_error({}) is None


class TestPikaVideoAdapter:
    def test_builds_payload_with_camel_case_aspect_ratio(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        payload = adapter._build_payload(
            VideoGenerationRequest(prompt="A robot dancing", duration=4, aspect_ratio="9:16")
        )

        assert payload["model"] == "pika-v1"
        assert payload["prompt"] == "A robot dancing"
        assert payload["duration"] == 4
        assert payload["aspectRatio"] == "9:16"

    def test_maps_pika_statuses(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        assert adapter._map_status("pending") == TaskStatus.PENDING
        assert adapter._map_status("processing") == TaskStatus.PROCESSING
        assert adapter._map_status("finished") == TaskStatus.COMPLETED
        assert adapter._map_status("failed") == TaskStatus.FAILED
        assert adapter._map_status(None) == TaskStatus.PROCESSING

    def test_extracts_video_url_from_result(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        generation = {"videos": [{"resultUrl": "https://cdn.pika.art/video.mp4"}]}
        assert adapter._extract_video_url(generation) == "https://cdn.pika.art/video.mp4"

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"videos": []}) is None

    def test_extracts_error_from_message(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        assert adapter._extract_error({"message": "Generation failed"}) == "Generation failed"
        assert adapter._extract_error({"error": "timeout"}) == "timeout"
        assert adapter._extract_error({}) is None


class TestSiliconFlowVideoAdapter:
    def test_builds_payload_with_image_size(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        payload = adapter._build_payload(
            VideoGenerationRequest(prompt="A cat playing piano", duration=5, aspect_ratio="16:9")
        )

        assert payload["model"] == "Wan2.1-T2V-14B"
        assert payload["prompt"] == "A cat playing piano"
        assert payload["image_size"] == "1280x720"

    def test_maps_siliconflow_statuses(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        assert adapter._map_status("InProgress") == TaskStatus.PROCESSING
        assert adapter._map_status("Succeed") == TaskStatus.COMPLETED
        assert adapter._map_status("Failed") == TaskStatus.FAILED
        assert adapter._map_status(None) == TaskStatus.PENDING

    def test_extracts_video_url_from_results(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        task = {"results": {"videos": [{"url": "https://cdn.siliconflow.cn/video.mp4"}]}}
        assert adapter._extract_video_url(task) == "https://cdn.siliconflow.cn/video.mp4"

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"results": {}}) is None

    def test_extracts_error_from_reason(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        assert adapter._extract_error({"reason": "Content violation"}) == "Content violation"
        assert adapter._extract_error({}) is None


class TestVolcengineVideoAdapter:
    def test_builds_payload_with_content_array(self):
        adapter = VolcengineVideoAdapter(build_model("volcengine", "seedance-1-lite"))

        payload = adapter._build_payload(
            VideoGenerationRequest(prompt="Ocean waves at sunset", duration=5, aspect_ratio="16:9")
        )

        assert payload["model"] == "seedance-1-lite"
        assert payload["content"] == [{"type": "text", "text": "Ocean waves at sunset"}]
        assert payload["parameters"]["duration"] == 5
        assert payload["parameters"]["aspect_ratio"] == "16:9"

    def test_maps_volcengine_statuses(self):
        adapter = VolcengineVideoAdapter(build_model("volcengine", "seedance-1-lite"))

        assert adapter._map_status("running") == TaskStatus.PROCESSING
        assert adapter._map_status("succeeded") == TaskStatus.COMPLETED
        assert adapter._map_status("failed") == TaskStatus.FAILED
        assert adapter._map_status("cancelled") == TaskStatus.CANCELLED
        assert adapter._map_status(None) == TaskStatus.PENDING

    def test_extracts_video_url_from_content(self):
        adapter = VolcengineVideoAdapter(build_model("volcengine", "seedance-1-lite"))

        task = {"content": [{"video_url": {"url": "https://cdn.volces.com/video.mp4"}}]}
        assert adapter._extract_video_url(task) == "https://cdn.volces.com/video.mp4"

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"content": []}) is None

    def test_extracts_error_from_error_dict(self):
        adapter = VolcengineVideoAdapter(build_model("volcengine", "seedance-1-lite"))

        assert adapter._extract_error({"error": {"message": "Quota exceeded"}}) == "Quota exceeded"
        assert adapter._extract_error({"error": "timeout"}) == "timeout"
        assert adapter._extract_error({}) is None


class TestDashScopeVideoAdapter:
    def test_builds_payload_with_input_parameters(self):
        adapter = DashScopeVideoAdapter(build_model("qwen", "wan2.1-t2v-plus"))

        payload = adapter._build_payload(
            VideoGenerationRequest(prompt="A futuristic city", duration=4, aspect_ratio="16:9")
        )

        assert payload["model"] == "wan2.1-t2v-plus"
        assert payload["input"]["prompt"] == "A futuristic city"
        assert payload["parameters"]["duration"] == 4
        assert payload["parameters"]["size"] == "16:9"

    def test_maps_dashscope_statuses(self):
        adapter = DashScopeVideoAdapter(build_model("qwen", "wan2.1-t2v-plus"))

        assert adapter._map_status("PENDING") == TaskStatus.PENDING
        assert adapter._map_status("RUNNING") == TaskStatus.PROCESSING
        assert adapter._map_status("SUCCEEDED") == TaskStatus.COMPLETED
        assert adapter._map_status("FAILED") == TaskStatus.FAILED
        assert adapter._map_status(None) == TaskStatus.PENDING

    def test_extracts_video_url_from_output(self):
        adapter = DashScopeVideoAdapter(build_model("qwen", "wan2.1-t2v-plus"))

        task = {"output": {"video_url": "https://cdn.dashscope.com/video.mp4"}}
        assert adapter._extract_video_url(task) == "https://cdn.dashscope.com/video.mp4"

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"output": {}}) is None

    def test_extracts_error_from_output_message(self):
        adapter = DashScopeVideoAdapter(build_model("qwen", "wan2.1-t2v-plus"))

        assert adapter._extract_error({"output": {"message": "Generation failed"}}) == "Generation failed"
        assert adapter._extract_error({"message": "Server error"}) == "Server error"
        assert adapter._extract_error({}) is None
