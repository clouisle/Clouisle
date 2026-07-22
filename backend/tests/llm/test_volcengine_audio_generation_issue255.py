from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.audio.volcengine_generation import (
    VolcengineAudioGenerationAdapter,
)
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import AudioContent, AudioGenerationRequest


def adapter(**overrides) -> VolcengineAudioGenerationAdapter:
    values = {
        "model_id": "seed-audio-1.0",
        "api_key": "test-key",
        "base_url": None,
        "default_params": {},
        "config": {},
    }
    values.update(overrides)
    return VolcengineAudioGenerationAdapter(SimpleNamespace(**values))


def response(status_code=200, **kwargs) -> httpx.Response:
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://volcengine.invalid"),
        **kwargs,
    )


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, AuthenticationError), (429, RateLimitError), (500, ProviderError)],
)
def test_status_errors_are_translated(status_code, error_type):
    with pytest.raises(error_type):
        adapter()._raise_for_status(response(status_code, text="failed"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_response", "message"),
    [
        (response(content=b"not-json"), "Invalid Volcengine Seed Audio response"),
        (response(json={"code": 0}), "returned no audio"),
    ],
)
async def test_generate_rejects_malformed_success_responses(provider_response, message):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = provider_response

    with (
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(ProviderError, match=message),
    ):
        await adapter().generate(AudioGenerationRequest(prompt="Ocean"))


@pytest.mark.anyio
async def test_generate_translates_request_errors_and_accepts_url_audio():
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.side_effect = httpx.RequestError("offline")

    with (
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(ProviderError, match="request failed: offline"),
    ):
        await adapter().generate(AudioGenerationRequest(prompt="Ocean"))

    client.post.side_effect = None
    client.post.return_value = response(json={"url": "https://audio.invalid/ocean.mp3"})
    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter(config={"timeout": "12"}).generate(
            AudioGenerationRequest(prompt="Ocean")
        )

    assert result.audio.url == "https://audio.invalid/ocean.mp3"
    assert result.audio.base64 is None
    assert result.audio.duration is None


def test_payload_and_references_reject_missing_required_values(tmp_path):
    with pytest.raises(AuthenticationError):
        adapter(api_key=None)._build_payload(AudioGenerationRequest(prompt="Ocean"))

    instance = adapter()
    with pytest.raises(InvalidRequestError, match="must include"):
        instance._reference(AudioContent(), "audio")

    audio_file = tmp_path / "reference.wav"
    audio_file.write_bytes(b"audio")
    assert instance._reference(AudioContent(file_path=str(audio_file)), "audio") == {
        "audio_data": "YXVkaW8="
    }
