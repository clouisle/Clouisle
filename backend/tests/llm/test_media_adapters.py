import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.image import create_image_adapter
from app.llm.adapters.image.google import GoogleImageAdapter
from app.llm.adapters.image.luma import LumaImageAdapter
from app.llm.adapters.image.openai import OpenAIImageAdapter
from app.llm.adapters.image.runway import RunwayImageAdapter
from app.llm.adapters.image.siliconflow import SiliconFlowImageAdapter
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
            create_image_adapter(
                build_model(
                    "custom", "image-model", base_url="https://custom.example/v1"
                )
            ),
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
        assert isinstance(
            create_image_adapter(
                build_model("siliconflow", "black-forest-labs/flux-1-schnell")
            ),
            SiliconFlowImageAdapter,
        )

    def test_custom_image_provider_requires_base_url(self):
        with pytest.raises(InvalidRequestError):
            create_image_adapter(build_model("custom", "image-model", base_url=None))


class TestOpenAIImageAdapter:
    def test_gpt_image_payload_uses_default_params_and_request_overrides(self):
        adapter = OpenAIImageAdapter(
            build_model(
                "openai",
                "gpt-image-1",
                default_params={
                    "background": "transparent",
                    "output_format": "webp",
                    "output_compression": 60,
                    "quality": "medium",
                },
            )
        )

        payload = adapter._build_payload(
            ImageGenerationRequest(
                prompt="A product shot",
                width=1024,
                height=1024,
                quality="high",
                extra_params={"output_compression": 85},
            )
        )

        assert payload["quality"] == "high"
        assert payload["background"] == "transparent"
        assert payload["output_format"] == "webp"
        assert payload["output_compression"] == 85

    def test_dalle_payload_preserves_existing_behavior(self):
        adapter = OpenAIImageAdapter(build_model("openai", "dall-e-3"))

        payload = adapter._build_payload(
            ImageGenerationRequest(
                prompt="An illustrated city",
                width=1024,
                height=1792,
                style="vivid",
                quality="hd",
                extra_params={"background": "transparent"},
            )
        )

        assert payload["response_format"] == "url"
        assert payload["style"] == "vivid"
        assert payload["quality"] == "hd"
        assert "background" not in payload

    def test_explicit_openai_fields_override_extra_params(self):
        adapter = OpenAIImageAdapter(build_model("openai", "gpt-image-1"))

        payload = adapter._build_payload(
            ImageGenerationRequest(
                prompt="A product shot",
                width=1024,
                height=1024,
                quality="high",
                extra_params={
                    "quality": "low",
                    "background": "opaque",
                    "output_format": "jpeg",
                    "seed": 999,
                    "user": "abc",
                },
                seed=7,
            )
        )

        assert payload["quality"] == "high"
        assert payload["background"] == "opaque"
        assert payload["output_format"] == "jpeg"
        assert payload["seed"] == 7
        assert payload["user"] == "abc"


class TestRunwayImageAdapter:
    def test_builds_text_to_image_task_payload(self):
        adapter = RunwayImageAdapter(build_model("runway", "gen4_image"))
        adapter.client = SimpleNamespace(
            create_task=AsyncMock(return_value={"id": "task-1"})
        )

        task_id = asyncio.run(
            adapter._create_task(
                ImageGenerationRequest(
                    prompt="A dramatic skyline",
                    negative_prompt="blurry",
                    width=1536,
                    height=1024,
                    style="cinematic",
                    seed=7,
                    extra_params={"guidanceScale": 6.5},
                ),
                index=1,
            )
        )

        assert task_id == "task-1"
        path, payload = adapter.client.create_task.await_args.args
        assert path == "/v1/text_to_image"
        assert payload["model"] == "gen4_image"
        assert (
            payload["promptText"]
            == "A dramatic skyline\n\nStyle: cinematic\nAvoid: blurry"
        )
        assert payload["ratio"] == "1440:1080"
        assert payload["seed"] == 8
        assert payload["guidanceScale"] == 6.5

    def test_parses_runway_task_output(self):
        adapter = RunwayImageAdapter(build_model("runway", "gen4_image"))

        images = adapter._parse_images(
            {
                "status": "SUCCEEDED",
                "output": [
                    "https://example.com/generated-1.png",
                    {"url": "https://example.com/generated-2.png"},
                ],
            }
        )

        assert [image.image.url for image in images] == [
            "https://example.com/generated-1.png",
            "https://example.com/generated-2.png",
        ]
        assert all(image.image.format == "png" for image in images)


class TestLumaImageAdapter:
    def test_builds_image_generation_payload(self):
        adapter = LumaImageAdapter(build_model("luma", "photon-1"))
        adapter.client = SimpleNamespace(
            create_generation=AsyncMock(return_value={"id": "generation-1"})
        )

        generation_id = asyncio.run(
            adapter._create_generation(
                ImageGenerationRequest(
                    prompt="A portrait",
                    negative_prompt="blurry",
                    width=1024,
                    height=1792,
                    style="natural",
                    seed=11,
                    extra_params={"guidance_scale": 7},
                )
            )
        )

        assert generation_id == "generation-1"
        path, payload = adapter.client.create_generation.await_args.args
        assert path == "/generations/image"
        assert payload["model"] == "photon-1"
        assert payload["prompt"] == "A portrait\n\nStyle: natural\nAvoid: blurry"
        assert payload["aspect_ratio"] == "9:16"
        assert payload["seed"] == 11
        assert payload["guidance_scale"] == 7

    def test_parses_luma_generation_asset(self):
        adapter = LumaImageAdapter(build_model("luma", "photon-1"))

        image = adapter._parse_image(
            {
                "state": "completed",
                "assets": {"image": "https://example.com/generated.png"},
            }
        )

        assert image.image.url == "https://example.com/generated.png"
        assert image.image.format == "png"


class TestSiliconFlowImageAdapter:
    def test_builds_payload_with_siliconflow_field_mapping(self):
        adapter = SiliconFlowImageAdapter(
            build_model(
                "siliconflow",
                "black-forest-labs/flux-1-schnell",
                default_params={
                    "negative_prompt": "blurry",
                    "num_inference_steps": 20,
                    "guidance_scale": 7.5,
                },
            )
        )

        payload = adapter._build_payload(
            ImageGenerationRequest(
                prompt="A product shot",
                width=1536,
                height=1024,
                num_images=2,
                style="cinematic",
                seed=7,
                extra_params={
                    "cfg": 1.5,
                    "guidance_scale": 6.0,
                    "image_size": "wrong",
                    "batch_size": 99,
                    "response_format": "url",
                },
            )
        )

        assert payload["model"] == "black-forest-labs/flux-1-schnell"
        assert payload["prompt"] == "A product shot\n\nStyle: cinematic"
        assert payload["image_size"] == "1536x1024"
        assert payload["batch_size"] == 2
        assert payload["negative_prompt"] == "blurry"
        assert payload["num_inference_steps"] == 20
        assert payload["guidance_scale"] == 6.0
        assert payload["cfg"] == 1.5
        assert payload["seed"] == 7
        assert payload["response_format"] == "url"

    def test_maps_reference_images_to_image_fields(self):
        adapter = SiliconFlowImageAdapter(
            build_model("siliconflow", "Qwen/Qwen-Image-Edit-2509")
        )

        payload = adapter._build_payload(
            ImageGenerationRequest(
                prompt="Edit this image",
                images=[
                    ImageContent(url="https://example.com/primary.png"),
                    ImageContent(base64="aGVsbG8="),
                ],
                extra_params={"image": "https://example.com/ignored.png"},
            )
        )

        assert payload["image"] == "https://example.com/primary.png"
        assert payload["image2"] == "data:image/png;base64,aGVsbG8="
        assert "image3" not in payload

    def test_parses_siliconflow_image_response(self):
        adapter = SiliconFlowImageAdapter(
            build_model("siliconflow", "black-forest-labs/flux-1-schnell")
        )

        result = adapter._parse_response_data(
            {
                "images": [
                    {"url": "https://example.com/generated.webp"},
                    {"url": "https://example.com/generated-2.png"},
                ],
                "seed": 42,
            }
        )

        assert len(result.images) == 2
        assert result.images[0].image.url == "https://example.com/generated.webp"
        assert result.images[0].image.format == "webp"
        assert result.images[0].seed == 42
        assert result.images[1].image.format == "png"

    def test_raises_for_too_many_reference_images(self):
        adapter = SiliconFlowImageAdapter(
            build_model("siliconflow", "Qwen/Qwen-Image-Edit-2509")
        )

        with pytest.raises(InvalidRequestError):
            adapter._build_payload(
                ImageGenerationRequest(
                    prompt="Edit this image",
                    images=[
                        ImageContent(url="https://example.com/1.png"),
                        ImageContent(url="https://example.com/2.png"),
                        ImageContent(url="https://example.com/3.png"),
                        ImageContent(url="https://example.com/4.png"),
                    ],
                )
            )


class TestStabilityImageAdapter:
    def test_selects_endpoint_from_model_id(self):
        assert (
            StabilityImageAdapter(
                build_model("stability", "stable-image-ultra")
            )._build_path()
            == "/v2beta/stable-image/generate/ultra"
        )
        assert (
            StabilityImageAdapter(
                build_model("stability", "stable-image-core")
            )._build_path()
            == "/v2beta/stable-image/generate/core"
        )
        assert (
            StabilityImageAdapter(build_model("stability", "sd3.5-large"))._build_path()
            == "/v2beta/stable-image/generate/sd3"
        )

    def test_builds_sd3_form_payload(self):
        adapter = StabilityImageAdapter(
            build_model(
                "stability", "sd3.5-large", base_url="https://api.stability.ai/v1"
            )
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

    def test_uses_default_params_for_style_preset_and_output_format(self):
        adapter = StabilityImageAdapter(
            build_model(
                "stability",
                "stable-image-core",
                default_params={
                    "style_preset": "cinematic",
                    "output_format": "jpeg",
                },
            )
        )

        payload = adapter._build_form_data(
            ImageGenerationRequest(
                prompt="A mountain landscape",
                width=1024,
                height=1024,
            ),
            output_format="jpeg",
            seed_offset=0,
        )

        assert payload["style_preset"] == "cinematic"
        assert payload["output_format"] == "jpeg"

    def test_explicit_stability_fields_override_extra_params(self):
        adapter = StabilityImageAdapter(build_model("stability", "sd3.5-large"))

        output_format = adapter._get_output_format(
            ImageGenerationRequest(
                prompt="A dramatic city skyline",
                quality="png",
                extra_params={"output_format": "webp"},
            )
        )
        payload = adapter._build_form_data(
            ImageGenerationRequest(
                prompt="A dramatic city skyline",
                width=1536,
                height=1024,
                style="photographic",
                seed=7,
                extra_params={
                    "style_preset": "anime",
                    "aspect_ratio": "1:1",
                    "seed": 999,
                    "cfg_scale": 6,
                    "model": "wrong-model",
                },
            ),
            output_format=output_format,
            seed_offset=1,
        )

        assert output_format == "webp"
        assert payload["style_preset"] == "photographic"
        assert payload["aspect_ratio"] == "3:2"
        assert payload["seed"] == 8
        assert payload["model"] == "sd3.5-large"
        assert payload["cfg_scale"] == 6


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
        adapter = GoogleImageAdapter(
            build_model("google", "gemini-3-pro-image-preview")
        )

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

    def test_uses_default_params_for_google_image_config(self):
        adapter = GoogleImageAdapter(
            build_model(
                "google",
                "gemini-3-pro-image-preview",
                default_params={
                    "aspect_ratio": "9:16",
                    "image_size": "4K",
                    "person_generation": "ALLOW_ALL",
                    "prominent_people": "ALLOW_ADULT",
                    "output_mime_type": "image/jpeg",
                    "output_compression_quality": 72,
                },
            )
        )

        config = adapter._build_generation_config(
            ImageGenerationRequest(
                prompt="A portrait",
                width=1024,
                height=1024,
            ),
            seed_offset=0,
            overrides=adapter._split_extra_params(
                ImageGenerationRequest(prompt="A portrait")
            )[1],
        )

        assert config["image_config"]["aspect_ratio"] == "9:16"
        assert config["image_config"]["image_size"] == "4K"
        assert config["image_config"]["person_generation"] == "ALLOW_ALL"
        assert config["image_config"]["prominent_people"] == "ALLOW_ADULT"
        assert config["image_config"]["output_mime_type"] == "image/jpeg"
        assert config["image_config"]["output_compression_quality"] == 72

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
        fake_model = build_model(
            "runway", "gen4.5", id="model-1", name="Runway", is_enabled=True
        )
        fake_response = VideoGenerationResponse(
            task_id="task-1",
            status=TaskStatus.PENDING,
            model="gen4.5",
        )
        fake_adapter = SimpleNamespace(generate=AsyncMock(return_value=fake_response))

        with (
            patch.object(
                manager, "_get_model_config", AsyncMock(return_value=fake_model)
            ) as mock_get_model,
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
            VideoGenerationRequest(
                prompt="A drifting spaceship", duration=5, aspect_ratio="16:9"
            )
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
            VideoGenerationRequest(
                prompt="A sunset over mountains", duration=5.7, aspect_ratio="16:9"
            )
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

        assert (
            adapter._extract_error({"task_status_msg": "Content policy violation"})
            == "Content policy violation"
        )
        assert adapter._extract_error({}) is None


class TestPikaVideoAdapter:
    def test_builds_payload_with_camel_case_aspect_ratio(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        payload = adapter._build_payload(
            VideoGenerationRequest(
                prompt="A robot dancing", duration=4, aspect_ratio="9:16"
            )
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
        assert (
            adapter._extract_video_url(generation) == "https://cdn.pika.art/video.mp4"
        )

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"videos": []}) is None

    def test_extracts_error_from_message(self):
        adapter = PikaVideoAdapter(build_model("pika", "pika-v1"))

        assert (
            adapter._extract_error({"message": "Generation failed"})
            == "Generation failed"
        )
        assert adapter._extract_error({"error": "timeout"}) == "timeout"
        assert adapter._extract_error({}) is None


class TestSiliconFlowVideoAdapter:
    def test_builds_payload_with_image_size(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        payload = adapter._build_payload(
            VideoGenerationRequest(
                prompt="A cat playing piano", duration=5, aspect_ratio="16:9"
            )
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

        task = {
            "results": {"videos": [{"url": "https://cdn.siliconflow.cn/video.mp4"}]}
        }
        assert (
            adapter._extract_video_url(task) == "https://cdn.siliconflow.cn/video.mp4"
        )

        assert adapter._extract_video_url({}) is None
        assert adapter._extract_video_url({"results": {}}) is None

    def test_extracts_error_from_reason(self):
        adapter = SiliconFlowVideoAdapter(build_model("siliconflow", "Wan2.1-T2V-14B"))

        assert (
            adapter._extract_error({"reason": "Content violation"})
            == "Content violation"
        )
        assert adapter._extract_error({}) is None


class TestVolcengineVideoAdapter:
    def test_builds_payload_with_content_array(self):
        adapter = VolcengineVideoAdapter(build_model("volcengine", "seedance-1-lite"))

        payload = adapter._build_payload(
            VideoGenerationRequest(
                prompt="Ocean waves at sunset", duration=5, aspect_ratio="16:9"
            )
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

        assert (
            adapter._extract_error({"error": {"message": "Quota exceeded"}})
            == "Quota exceeded"
        )
        assert adapter._extract_error({"error": "timeout"}) == "timeout"
        assert adapter._extract_error({}) is None


class TestDashScopeVideoAdapter:
    def test_builds_payload_with_input_parameters(self):
        adapter = DashScopeVideoAdapter(build_model("qwen", "wan2.1-t2v-plus"))

        payload = adapter._build_payload(
            VideoGenerationRequest(
                prompt="A futuristic city", duration=4, aspect_ratio="16:9"
            )
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

        assert (
            adapter._extract_error({"output": {"message": "Generation failed"}})
            == "Generation failed"
        )
        assert adapter._extract_error({"message": "Server error"}) == "Server error"
        assert adapter._extract_error({}) is None
