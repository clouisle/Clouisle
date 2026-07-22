import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.llm.adapters.audio.openai_stt import OpenAISTTAdapter
from app.llm.adapters.image.google import GoogleImageAdapter
from app.llm.adapters.video.kling import KlingVideoAdapter
from app.llm.adapters.video.pika import PikaVideoAdapter
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import (
    AudioContent,
    ImageGenerationRequest,
    STTRequest,
    TaskStatus,
    VideoGenerationRequest,
)


def model(provider: str, model_id: str, **overrides):
    values = {
        "provider": provider,
        "model_id": model_id,
        "api_key": "secret",
        "base_url": "https://provider.invalid/v1",
        "config": {},
        "default_params": {},
        "max_output_tokens": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_google_generate_calls_mocked_sdk_until_requested_images():
    first = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="first", inline_data=None),
                        SimpleNamespace(
                            text=None,
                            inline_data=SimpleNamespace(
                                data=b"first-image", mime_type="image/webp"
                            ),
                        ),
                    ]
                ),
            )
        ]
    )
    second = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text=None,
                            inline_data=SimpleNamespace(
                                data=b"second-image", mime_type="image/jpeg"
                            ),
                        )
                    ]
                ),
            )
        ]
    )
    generate_content = AsyncMock(side_effect=[first, second])
    sdk_client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    client_factory = Mock(return_value=sdk_client)
    genai = ModuleType("google.genai")
    genai.Client = client_factory
    types = ModuleType("google.genai.types")
    types.HttpOptions = Mock(return_value="http-options")
    genai.types = types
    google = ModuleType("google")
    google.genai = genai

    with patch.dict(
        sys.modules,
        {"google": google, "google.genai": genai, "google.genai.types": types},
    ):
        result = await GoogleImageAdapter(
            model("google", "gemini-3-pro-image-preview")
        ).generate(
            ImageGenerationRequest(
                prompt="Two product shots", num_images=2, seed=7, width=2048
            )
        )

    assert [image.image.format for image in result.images] == ["webp", "jpeg"]
    assert [image.seed for image in result.images] == [7, 8]
    assert generate_content.await_count == 2
    assert generate_content.await_args_list[1].kwargs["config"]["seed"] == 8
    client_factory.assert_called_once()


@pytest.mark.parametrize(
    ("adapter_class", "create_name", "created", "task_id", "expected_status"),
    [
        (PikaVideoAdapter, "create_generation", {"id": 12}, "12", TaskStatus.COMPLETED),
        (
            KlingVideoAdapter,
            "create_task",
            {"task_id": "k-1"},
            "k-1",
            TaskStatus.COMPLETED,
        ),
    ],
)
@pytest.mark.anyio
async def test_video_generate_uses_mocked_provider_clients_and_returns_status(
    adapter_class, create_name, created, task_id, expected_status
):
    adapter = adapter_class(
        model(adapter_class.__name__.split("Video")[0].lower(), "v1")
    )
    create = AsyncMock(return_value=created)
    if adapter_class is PikaVideoAdapter:
        adapter.client = SimpleNamespace(
            create_generation=create,
            get_generation=AsyncMock(
                return_value={
                    "status": "finished",
                    "videos": [{"resultUrl": "https://video.invalid/pika.mp4"}],
                }
            ),
            config={},
        )
    else:
        adapter.client = SimpleNamespace(
            create_task=create,
            get_task=AsyncMock(
                return_value={
                    "task_status": "succeed",
                    "task_result": {
                        "videos": [{"url": "https://video.invalid/kling.mp4"}]
                    },
                }
            ),
        )

    result = await adapter.generate(VideoGenerationRequest(prompt="Animate"))

    assert result.task_id == task_id
    assert result.status == expected_status
    assert result.video is not None
    assert getattr(adapter.client, create_name).await_count == 1


@pytest.mark.parametrize("adapter_class", [PikaVideoAdapter, KlingVideoAdapter])
@pytest.mark.anyio
async def test_video_generate_rejects_mocked_provider_response_without_task_id(
    adapter_class,
):
    adapter = adapter_class(
        model(adapter_class.__name__.split("Video")[0].lower(), "v1")
    )
    adapter.client = SimpleNamespace(
        create_generation=AsyncMock(return_value={}),
        create_task=AsyncMock(return_value={}),
        config={},
    )

    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Animate"))


class MockAsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.post = AsyncMock(side_effect=error, return_value=response)
        self.get = AsyncMock(side_effect=error, return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.anyio
async def test_openai_stt_posts_all_options_and_parses_verbose_response():
    response = SimpleNamespace(
        status_code=200,
        text="unused",
        json=Mock(
            return_value={
                "text": "hello world",
                "language": "en",
                "duration": 1.5,
                "segments": [{"start": 0.0, "end": 1.5, "text": "hello world"}],
                "words": [{"word": "hello", "start": 0.0, "end": 0.5}],
            }
        ),
    )
    client = MockAsyncClient(response)

    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient", return_value=client
    ):
        result = await OpenAISTTAdapter(model("openai", "whisper-1")).transcribe(
            STTRequest(
                audio=AudioContent(base64="YXVkaW8="),
                language="en",
                prompt="Names",
                response_format="unsupported",
                timestamp_granularities=["word", "segment"],
            )
        )

    assert result.text == "hello world"
    assert result.segments and result.segments[0].id == 0
    assert result.words and result.words[0].word == "hello"
    assert client.post.await_args.kwargs["data"] == {
        "model": "whisper-1",
        "response_format": "verbose_json",
        "language": "en",
        "prompt": "Names",
        "timestamp_granularities[]": "word,segment",
    }


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        (401, {}, AuthenticationError),
        (429, {}, RateLimitError),
        (400, {"error": {"message": "bad audio"}}, InvalidRequestError),
        (503, {}, ProviderError),
    ],
)
@pytest.mark.anyio
async def test_openai_stt_translates_mocked_provider_failures(status, error, expected):
    response = SimpleNamespace(
        status_code=status,
        text="provider unavailable",
        json=Mock(return_value=error),
    )
    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient",
        return_value=MockAsyncClient(response),
    ):
        with pytest.raises(expected):
            await OpenAISTTAdapter(model("openai", "whisper-1")).transcribe(
                STTRequest(audio=AudioContent(base64="YQ=="))
            )


@pytest.mark.parametrize(
    "error",
    [
        httpx.TimeoutException("slow"),
        httpx.RequestError("disconnected"),
    ],
)
@pytest.mark.anyio
async def test_openai_stt_translates_mocked_transport_failures(error):
    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient",
        return_value=MockAsyncClient(error=error),
    ):
        with pytest.raises(ProviderError):
            await OpenAISTTAdapter(model("openai", "whisper-1")).transcribe(
                STTRequest(audio=AudioContent(base64="YQ=="))
            )
