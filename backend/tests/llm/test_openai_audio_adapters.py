from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.audio.openai_stt import OpenAISTTAdapter
from app.llm.adapters.audio.openai_tts import OpenAITTSAdapter
from app.llm.errors import AuthenticationError, InvalidRequestError, ProviderError
from app.llm.types import AudioContent, STTRequest, TTSRequest


class AsyncClient:
    def __init__(self, response=None, error=None, **_kwargs):
        self.response = response
        self.error = error
        self.post = AsyncMock(side_effect=error, return_value=response)
        self.get = AsyncMock(side_effect=error, return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def model(model_id: str):
    return SimpleNamespace(api_key="mock-key", base_url=None, model_id=model_id)


@pytest.mark.anyio
async def test_tts_normalizes_options_and_returns_encoded_audio():
    client = AsyncClient(SimpleNamespace(status_code=200, content=b"audio"))
    adapter = OpenAITTSAdapter(model("tts-1"))

    with patch(
        "app.llm.adapters.audio.openai_tts.httpx.AsyncClient", return_value=client
    ):
        result = await adapter.synthesize(
            TTSRequest(text="Hello", voice="unsupported", format="other", speed=1.25)
        )

    assert result.audio.base64 == "YXVkaW8="
    assert result.audio.format == "mp3"
    client.post.assert_awaited_once_with(
        "https://api.openai.com/v1/audio/speech",
        json={
            "model": "tts-1",
            "input": "Hello",
            "voice": "alloy",
            "response_format": "mp3",
            "speed": 1.25,
        },
        headers={
            "Authorization": "Bearer mock-key",
            "Content-Type": "application/json",
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(status_code=401), AuthenticationError),
        (
            SimpleNamespace(
                status_code=400,
                json=lambda: {"error": {"message": "invalid text"}},
            ),
            InvalidRequestError,
        ),
        (SimpleNamespace(status_code=503, text="unavailable"), ProviderError),
    ],
)
async def test_tts_translates_provider_failures(response, expected):
    with patch(
        "app.llm.adapters.audio.openai_tts.httpx.AsyncClient",
        return_value=AsyncClient(response),
    ):
        with pytest.raises(expected):
            await OpenAITTSAdapter(model("tts-1")).synthesize(TTSRequest(text="Hello"))


@pytest.mark.anyio
async def test_tts_translates_transport_failures():
    request = httpx.Request("POST", "https://api.openai.com")
    for error in (
        httpx.TimeoutException("timed out", request=request),
        httpx.RequestError("offline", request=request),
    ):
        with patch(
            "app.llm.adapters.audio.openai_tts.httpx.AsyncClient",
            return_value=AsyncClient(error=error),
        ):
            with pytest.raises(ProviderError):
                await OpenAITTSAdapter(model("tts-1")).synthesize(
                    TTSRequest(text="Hello")
                )


@pytest.mark.anyio
async def test_stt_posts_audio_options_and_parses_verbose_response():
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "text": "Hello",
            "language": "en",
            "duration": 1.5,
            "segments": [{"id": 2, "start": 0, "end": 1.5, "text": "Hello"}],
            "words": [{"word": "Hello", "start": 0, "end": 1.5}],
        },
    )
    client = AsyncClient(response)
    adapter = OpenAISTTAdapter(model("whisper-1"))

    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient", return_value=client
    ):
        result = await adapter.transcribe(
            STTRequest(
                audio=AudioContent(base64="YXVkaW8="),
                language="en",
                prompt="Names",
                response_format="unsupported",
                timestamp_granularities=["word", "segment"],
            )
        )

    assert result.text == "Hello"
    assert result.language == "en"
    assert result.duration == 1.5
    assert result.segments and result.segments[0].id == 2
    assert result.words and result.words[0].word == "Hello"
    assert client.post.await_args.kwargs["data"] == {
        "model": "whisper-1",
        "response_format": "verbose_json",
        "language": "en",
        "prompt": "Names",
        "timestamp_granularities[]": "word,segment",
    }


@pytest.mark.anyio
async def test_stt_handles_text_and_missing_audio():
    adapter = OpenAISTTAdapter(model("whisper-1"))
    adapter._get_audio_data = AsyncMock(return_value=b"audio")
    client = AsyncClient(SimpleNamespace(status_code=200, text="Transcript"))

    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient", return_value=client
    ):
        result = await adapter.transcribe(
            STTRequest(audio=AudioContent(base64="YQ=="), response_format="text")
        )
    assert result.text == "Transcript"

    adapter._get_audio_data = AsyncMock(return_value=None)
    with pytest.raises(InvalidRequestError):
        await adapter.transcribe(STTRequest(audio=AudioContent()))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(status_code=401), AuthenticationError),
        (
            SimpleNamespace(
                status_code=400,
                json=lambda: {"error": {"message": "invalid audio"}},
            ),
            InvalidRequestError,
        ),
        (SimpleNamespace(status_code=503, text="unavailable"), ProviderError),
    ],
)
async def test_stt_translates_provider_failures(response, expected):
    adapter = OpenAISTTAdapter(model("whisper-1"))
    adapter._get_audio_data = AsyncMock(return_value=b"audio")
    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient",
        return_value=AsyncClient(response),
    ):
        with pytest.raises(expected):
            await adapter.transcribe(STTRequest(audio=AudioContent(base64="YQ==")))


@pytest.mark.anyio
async def test_stt_translates_transport_failures():
    adapter = OpenAISTTAdapter(model("whisper-1"))
    adapter._get_audio_data = AsyncMock(return_value=b"audio")
    request = httpx.Request("POST", "https://api.openai.com")
    for error in (
        httpx.TimeoutException("timed out", request=request),
        httpx.RequestError("offline", request=request),
    ):
        with patch(
            "app.llm.adapters.audio.openai_stt.httpx.AsyncClient",
            return_value=AsyncClient(error=error),
        ):
            with pytest.raises(ProviderError):
                await adapter.transcribe(STTRequest(audio=AudioContent(base64="YQ==")))


@pytest.mark.anyio
async def test_stt_loads_audio_from_file_and_url(tmp_path):
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"file-audio")
    adapter = OpenAISTTAdapter(model("whisper-1"))

    assert (
        await adapter._get_audio_data(
            STTRequest(audio=AudioContent(file_path=str(audio_file)))
        )
        == b"file-audio"
    )

    client = AsyncClient(SimpleNamespace(status_code=200, content=b"url-audio"))
    with patch(
        "app.llm.adapters.audio.openai_stt.httpx.AsyncClient", return_value=client
    ):
        assert (
            await adapter._get_audio_data(
                STTRequest(audio=AudioContent(url="https://example.test/audio"))
            )
            == b"url-audio"
        )
