from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.adapters.audio.minimax_tts import MiniMaxTTSAdapter
from app.llm.adapters.audio.openai_stt import OpenAISTTAdapter
from app.llm.adapters.image.minimax import MiniMaxImageAdapter
from app.llm.adapters.image.openai_responses import OpenAIResponsesImageAdapter
from app.llm.adapters.image.volcengine import VolcengineImageAdapter
from app.llm.adapters.video.dashscope import DashScopeVideoAdapter
from app.llm.adapters.video.kling import KlingVideoAdapter
from app.llm.adapters.video.pika import PikaVideoAdapter
from app.llm.adapters.video.siliconflow import SiliconFlowVideoAdapter
from app.llm.adapters.video.volcengine import VolcengineVideoAdapter
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import (
    AudioContent,
    ImageGenerationRequest,
    STTRequest,
    TTSRequest,
    TaskStatus,
    VideoGenerationRequest,
)


def model(provider, model_id, **overrides):
    values = {
        "provider": provider,
        "model_id": model_id,
        "api_key": "key",
        "base_url": "https://provider.invalid/v1",
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "item, expected_format, expected_seed",
    [
        ({"url": "https://cdn.invalid/a.webp", "seed": 17}, "webp", 17),
        ({"b64_json": "aW1hZ2U=", "seed": "17"}, "jpeg", None),
        ({"url": "https://cdn.invalid/a.png", "b64_json": "aW1hZ2U="}, "png", None),
    ],
)
def test_volcengine_image_interprets_url_base64_format_and_seed(
    item, expected_format, expected_seed
):
    adapter = VolcengineImageAdapter(model("volcengine", "seedream"))
    result = adapter._parse_response({"data": [None, {}, item]}, {})
    image = result.images[0]
    assert image.image.format == expected_format
    assert image.seed == expected_seed
    if expected_format == "png":
        assert image.image.url.endswith("a.png")
        assert image.image.base64 == "aW1hZ2U="


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"data": None},
        {"data": []},
        {"data": [None, {}, {"url": ""}, {"b64_json": 3}]},
    ],
)
def test_volcengine_image_rejects_missing_or_malformed_output(data):
    adapter = VolcengineImageAdapter(model("volcengine", "seedream"))
    with pytest.raises(ProviderError):
        adapter._parse_response(data, {})


def test_minimax_image_filters_bad_values_and_parses_both_output_encodings():
    adapter = MiniMaxImageAdapter(model("minimax", "image-01"))
    result = adapter._parse_response(
        {
            "data": {
                "image_urls": [None, "", "https://cdn.invalid/out.jpg"],
                "image_base64": [None, "", "aW1hZ2U="],
            }
        },
        {},
    )
    assert [
        (image.image.format, image.image.url, image.image.base64)
        for image in result.images
    ] == [
        ("jpg", "https://cdn.invalid/out.jpg", None),
        ("png", None, "aW1hZ2U="),
    ]


@pytest.mark.parametrize(
    "data",
    [{}, {"data": []}, {"data": {"image_urls": [None, ""], "image_base64": [0]}}],
)
def test_minimax_image_rejects_empty_provider_result(data):
    adapter = MiniMaxImageAdapter(model("minimax", "image-01"))
    with pytest.raises(ProviderError):
        adapter._parse_response(data, {})


def test_responses_image_parser_ignores_non_image_and_supports_sdk_objects():
    adapter = OpenAIResponsesImageAdapter(model("openai", "gpt-image-1"))
    parsed = adapter._parse_images(
        SimpleNamespace(
            output=[
                {"type": "message", "result": "not-image"},
                SimpleNamespace(type="image_generation_call", result="aW1hZ2U="),
                {"type": "image_generation_call", "result": ""},
            ]
        ),
        "webp",
    )
    assert len(parsed) == 1
    assert parsed[0].image.base64 == "aW1hZ2U="
    assert parsed[0].image.format == "webp"


@pytest.mark.parametrize(
    "output",
    [
        None,
        [],
        [{"type": "message", "result": "x"}],
        [{"type": "image_generation_call", "result": None}],
    ],
)
def test_responses_image_parser_rejects_response_without_image(output):
    adapter = OpenAIResponsesImageAdapter(model("openai", "gpt-image-1"))
    with pytest.raises(InvalidRequestError, match="no generated image"):
        adapter._parse_images(SimpleNamespace(output=output), "png")


@pytest.mark.parametrize(
    "task, status, url, error",
    [
        (
            {
                "status": "succeeded",
                "content": {"video_url": "https://cdn.invalid/v.mp4"},
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/v.mp4",
            None,
        ),
        ({"status": "running", "content": []}, TaskStatus.PROCESSING, None, None),
        ({"status": "expired", "error": {"code": 410}}, TaskStatus.FAILED, None, "410"),
        (
            {"status": "cancelled", "error": "stopped"},
            TaskStatus.CANCELLED,
            None,
            "stopped",
        ),
        (
            {
                "status": "succeeded",
                "content": [
                    {"x": 1},
                    {"video_url": {"url": "https://cdn.invalid/nested.mp4"}},
                ],
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/nested.mp4",
            None,
        ),
    ],
)
@pytest.mark.anyio
async def test_volcengine_video_maps_provider_status_and_video_payload(
    task, status, url, error
):
    adapter = VolcengineVideoAdapter(model("volcengine", "seedance"))
    adapter.client.get_task = AsyncMock(return_value=task)
    result = await adapter.get_status("task-1")
    assert result.status == status
    assert (result.video.url if result.video else None) == url
    assert result.error == error


@pytest.mark.anyio
async def test_volcengine_video_detects_missing_output_and_task_id():
    adapter = VolcengineVideoAdapter(model("volcengine", "seedance"))
    adapter.client.get_task = AsyncMock(
        return_value={"status": "succeeded", "content": []}
    )
    result = await adapter.get_status("task-2")
    assert result.status == TaskStatus.FAILED
    assert result.video is None and result.error
    adapter.client.create_task = AsyncMock(return_value={})
    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Animate"))


@pytest.mark.parametrize(
    "adapter_type, task, status, url, error",
    [
        (
            SiliconFlowVideoAdapter,
            {
                "status": "Succeed",
                "results": {"videos": [{"url": "https://cdn.invalid/v.mp4"}]},
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/v.mp4",
            None,
        ),
        (
            SiliconFlowVideoAdapter,
            {"status": "Failed", "reason": {"message": "denied"}},
            TaskStatus.FAILED,
            None,
            "{'message': 'denied'}",
        ),
        (
            SiliconFlowVideoAdapter,
            {"status": "InProgress", "results": {"videos": []}},
            TaskStatus.PROCESSING,
            None,
            None,
        ),
        (
            SiliconFlowVideoAdapter,
            {"status": None, "results": []},
            TaskStatus.PENDING,
            None,
            None,
        ),
        (
            DashScopeVideoAdapter,
            {
                "output": {
                    "task_status": "SUCCEEDED",
                    "video_url": "https://cdn.invalid/q.mp4",
                }
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/q.mp4",
            None,
        ),
        (
            DashScopeVideoAdapter,
            {"output": {"task_status": "FAILED", "message": "rejected"}},
            TaskStatus.FAILED,
            None,
            "rejected",
        ),
        (
            DashScopeVideoAdapter,
            {"output": {"task_status": "unknown"}},
            TaskStatus.PENDING,
            None,
            None,
        ),
        (
            KlingVideoAdapter,
            {
                "task_status": "succeed",
                "task_result": {"videos": [{"url": "https://cdn.invalid/k.mp4"}]},
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/k.mp4",
            None,
        ),
        (
            KlingVideoAdapter,
            {"task_status": "failed", "task_status_msg": "rejected"},
            TaskStatus.FAILED,
            None,
            "rejected",
        ),
        (
            KlingVideoAdapter,
            {"task_status": "submitted"},
            TaskStatus.PENDING,
            None,
            None,
        ),
        (
            PikaVideoAdapter,
            {
                "status": "finished",
                "videos": [{"resultUrl": "https://cdn.invalid/p.mp4"}],
            },
            TaskStatus.COMPLETED,
            "https://cdn.invalid/p.mp4",
            None,
        ),
        (
            PikaVideoAdapter,
            {"status": "failed", "message": {"code": 9}},
            TaskStatus.FAILED,
            None,
            "9",
        ),
        (PikaVideoAdapter, {"status": "pending"}, TaskStatus.PENDING, None, None),
    ],
)
@pytest.mark.anyio
async def test_video_adapters_parse_status_video_and_failure_fields(
    adapter_type, task, status, url, error
):
    adapter = adapter_type(model("provider", "video-model"))
    if adapter_type is SiliconFlowVideoAdapter:
        adapter.client.get_task = AsyncMock(return_value=task)
    elif adapter_type in (DashScopeVideoAdapter, KlingVideoAdapter):
        adapter.client.get_task = AsyncMock(return_value=task)
    else:
        adapter.client.get_generation = AsyncMock(return_value=task)
    result = await adapter.get_status("task-3")
    assert result.status == status
    assert (result.video.url if result.video else None) == url
    assert result.error == error


@pytest.mark.anyio
async def test_missing_video_task_identifiers_are_provider_errors():
    adapter = SiliconFlowVideoAdapter(model("siliconflow", "wan"))
    adapter.client.create_task = AsyncMock(return_value={})
    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Animate"))

    adapter = DashScopeVideoAdapter(model("qwen", "wan"))
    adapter.client.create_task = AsyncMock(return_value={"output": {}})
    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Animate"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "adapter_type, method, response",
    [
        (KlingVideoAdapter, "create_task", {"task_id": ""}),
        (PikaVideoAdapter, "create_generation", {"id": None}),
    ],
)
async def test_kling_and_pika_reject_provider_responses_without_task_id(
    adapter_type, method, response
):
    adapter = adapter_type(model("provider", "video-model"))
    setattr(adapter.client, method, AsyncMock(return_value=response))
    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Animate"))


@pytest.mark.parametrize(
    "adapter_type, task",
    [
        (SiliconFlowVideoAdapter, {"results": {"videos": [None]}}),
        (KlingVideoAdapter, {"task_result": {"videos": [None]}}),
        (PikaVideoAdapter, {"videos": [None]}),
        (DashScopeVideoAdapter, {"output": []}),
    ],
)
def test_video_response_ignores_malformed_first_video_entry(adapter_type, task):
    adapter = adapter_type(model("provider", "video-model"))
    assert adapter._extract_video_url(task) is None


@pytest.mark.parametrize(
    "adapter_type, params, generation_request, field",
    [
        (
            MiniMaxImageAdapter,
            {"response_format": "binary"},
            ImageGenerationRequest(prompt="A portrait"),
            "response_format",
        ),
        (
            VolcengineImageAdapter,
            {"response_format": "binary"},
            ImageGenerationRequest(prompt="A portrait"),
            "response_format",
        ),
        (
            VolcengineImageAdapter,
            {"sequential_image_generation": "sometimes"},
            ImageGenerationRequest(prompt="A portrait"),
            "sequential_image_generation",
        ),
        (
            VolcengineImageAdapter,
            {"sequential_image_generation": "disabled"},
            ImageGenerationRequest(prompt="A portrait", num_images=2),
            "sequential_image_generation",
        ),
        (
            VolcengineImageAdapter,
            {
                "sequential_image_generation": "auto",
                "sequential_image_generation_options": [],
            },
            ImageGenerationRequest(prompt="A portrait", num_images=2),
            "sequential_image_generation_options",
        ),
    ],
)
def test_image_payload_rejects_incompatible_provider_options(
    adapter_type, params, generation_request, field
):
    adapter = adapter_type(model("provider", "image-model", default_params=params))
    with pytest.raises(InvalidRequestError) as error:
        adapter._build_payload(generation_request)
    assert error.value.field == field


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": {"audio": None}},
        {"data": {"audio": ""}},
        {"data": {"audio": "zz"}},
        {"data": {"audio": "  "}},
    ],
)
@pytest.mark.anyio
async def test_minimax_tts_rejects_missing_and_invalid_hex_audio(data):
    adapter = MiniMaxTTSAdapter(
        model("minimax", "speech-01", default_params={"voice": "narrator"})
    )
    adapter.client.request = AsyncMock(return_value=data)
    with pytest.raises(ProviderError):
        await adapter.synthesize(TTSRequest(text="A short sentence"))


def test_minimax_tts_reads_default_voice_speed_format_and_audio_settings():
    adapter = MiniMaxTTSAdapter(
        model(
            "minimax",
            "speech-01",
            default_params={
                "voice": "narrator",
                "format": "WAV",
                "speed": 1.2,
                "sample_rate": 24000,
            },
        )
    )
    payload = adapter._build_payload(TTSRequest(text="A short sentence"))
    assert payload["voice_setting"] == {"voice_id": "narrator", "speed": 1.2}
    assert payload["audio_setting"] == {"format": "wav", "sample_rate": 24000}


@pytest.mark.anyio
async def test_openai_stt_parses_sparse_verbose_payload_with_provider_defaults():
    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "text": "recognized",
                "segments": [{}, {"id": 8, "text": "word"}],
                "words": [{}, {"word": "Hi"}],
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient", return_value=Client()
    ):
        result = await OpenAISTTAdapter(model("openai", "whisper-1")).transcribe(
            STTRequest(
                audio=AudioContent(base64="YXVkaW8="), response_format="verbose_json"
            )
        )
    assert result.text == "recognized"
    assert result.language is None and result.duration is None
    assert [segment.id for segment in result.segments] == [0, 8]
    assert [word.word for word in result.words] == ["", "Hi"]
