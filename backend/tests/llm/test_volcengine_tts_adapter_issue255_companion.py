import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.llm.adapters.audio.volcengine_tts import VolcengineTTSAdapter
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import TTSRequest


def adapter(**overrides) -> VolcengineTTSAdapter:
    values = {
        "model_id": "seed-tts-2.0",
        "api_key": "test-key",
        "base_url": "https://volcengine.invalid/tts/",
        "default_params": {},
        "config": {},
    }
    values.update(overrides)
    return VolcengineTTSAdapter(SimpleNamespace(**values))


def install_transport(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)


def test_config_precedence_defaults_and_payload():
    instance = adapter(
        default_params={
            "speaker": "default-speaker",
            "format": "ogg_opus",
            "speed": "1.25",
            "sample_rate": "48000",
            "emotion": "happy",
            "bit_rate": None,
        },
        config={
            "speaker": "config-speaker",
            "voice": "config-voice",
            "format": "pcm",
            "speed": 0.75,
            "sample_rate": 16000,
            "bit_rate": 128000,
            "emotion_scale": 4,
            "loudness_rate": 2,
            "uid": "configured-user",
            "timeout": "12.5",
        },
    )

    payload, audio_format = instance._build_payload(TTSRequest(text="Hello"))

    assert instance.base_url == "https://volcengine.invalid/tts"
    assert instance._value("speaker", "runtime-speaker") == "runtime-speaker"
    assert instance._value("missing", default="fallback") == "fallback"
    assert instance._timeout() == 12.5
    assert audio_format == "ogg_opus"
    assert payload == {
        "user": {"uid": "configured-user"},
        "req_params": {
            "text": "Hello",
            "speaker": "default-speaker",
            "audio_params": {
                "format": "ogg_opus",
                "sample_rate": 48000,
                "speech_rate": 25,
                "bit_rate": 128000,
                "emotion": "happy",
                "emotion_scale": 4,
                "loudness_rate": 2,
            },
        },
    }

    explicit, explicit_format = instance._build_payload(
        TTSRequest(text="Hello", voice="runtime", format="pcm", speed=0.5)
    )
    assert explicit_format == "pcm"
    assert explicit["req_params"]["speaker"] == "runtime"
    assert explicit["req_params"]["audio_params"]["speech_rate"] == -50


@pytest.mark.parametrize(
    ("instance", "tts_request", "error_type", "message"),
    [
        (
            adapter(api_key=None),
            TTSRequest(text="Hello", voice="speaker"),
            AuthenticationError,
            None,
        ),
        (
            adapter(model_id=""),
            TTSRequest(text="Hello", voice="speaker"),
            InvalidRequestError,
            "resource ID",
        ),
        (
            adapter(),
            TTSRequest(text="Hello"),
            InvalidRequestError,
            "speaker is required",
        ),
        (
            adapter(default_params={"speaker": "s", "format": "wav"}),
            TTSRequest(text="Hello"),
            InvalidRequestError,
            "Unsupported.*format",
        ),
        (
            adapter(default_params={"speaker": "s", "speed": 2.1}),
            TTSRequest(text="Hello"),
            InvalidRequestError,
            "speed must be",
        ),
        (
            adapter(default_params={"speaker": "s", "sample_rate": 12345}),
            TTSRequest(text="Hello"),
            InvalidRequestError,
            "sample rate",
        ),
    ],
)
def test_payload_validation(instance, tts_request, error_type, message):
    with pytest.raises(error_type, match=message):
        instance._build_payload(tts_request)


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, AuthenticationError), (429, RateLimitError), (503, ProviderError)],
)
def test_http_status_variants(status_code, error_type):
    response = httpx.Response(status_code, text="failed")
    with pytest.raises(error_type):
        adapter()._raise_for_status(response)

    adapter()._raise_for_status(httpx.Response(200))


@pytest.mark.parametrize(
    ("event", "data", "message"),
    [
        ("352", "not-json", "Invalid Volcengine TTS SSE payload"),
        (
            "352",
            json.dumps({"code": 0, "data": "%%%"}),
            "Invalid Volcengine TTS audio payload",
        ),
        (
            "352",
            json.dumps({"code": 0, "data": 1}),
            "Invalid Volcengine TTS audio payload",
        ),
        ("153", json.dumps({"code": 1}), "Volcengine TTS failed"),
    ],
)
def test_event_errors(event, data, message):
    with pytest.raises(ProviderError, match=message):
        adapter()._consume_event(event, data)


def test_non_audio_and_empty_events_are_ignored():
    instance = adapter()
    assert instance._consume_event("352", "") == ([], False)
    assert instance._consume_event("153", json.dumps({"code": 0, "data": "YQ=="})) == (
        [],
        False,
    )


@pytest.mark.anyio
async def test_synthesize_streams_binary_chunks_and_sends_payload(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b": keepalive\n"
                b"event: 352\n"
                b'data: {"code":0,"data":"YQ=="}\n\n'
                b"event: ignored\n"
                b'data: {"code":0}\n\n'
                b"event: 352\n"
                b'data: {"code":0,"data":"Yg=="}\n\n'
                b"event: 152\n"
                b'data: {"code":20000000}\n'
            ),
        )

    install_transport(monkeypatch, handler)
    result = await adapter(default_params={"speaker": "narrator"}).synthesize(
        TTSRequest(text="Hello")
    )

    request = captured["request"]
    assert request.method == "POST"
    assert request.url == httpx.URL("https://volcengine.invalid/tts")
    assert request.headers["x-api-key"] == "test-key"
    assert request.headers["x-api-resource-id"] == "seed-tts-2.0"
    assert json.loads(request.content)["req_params"]["text"] == "Hello"
    assert result.audio.base64 == "YWI="
    assert result.audio.format == "mp3"
    assert result.model == "seed-tts-2.0"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'event: 352\ndata: {"code":0,"data":"YQ=="}\n\n', "before completion"),
        (b'event: 152\ndata: {"code":20000000}\n\n', "returned no audio"),
    ],
)
async def test_synthesize_rejects_incomplete_or_empty_streams(
    monkeypatch, content, message
):
    install_transport(monkeypatch, lambda request: httpx.Response(200, content=content))

    with pytest.raises(ProviderError, match=message):
        await adapter(default_params={"speaker": "narrator"}).synthesize(
            TTSRequest(text="Hello")
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport_error", "message"),
    [
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("offline"), "request failed: offline"),
    ],
)
async def test_synthesize_translates_transport_errors(
    monkeypatch, transport_error, message
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error

    install_transport(monkeypatch, handler)
    with patch("app.llm.adapters.audio.volcengine_tts.t", side_effect=lambda key: key):
        with pytest.raises(ProviderError, match=message):
            await adapter(default_params={"speaker": "narrator"}).synthesize(
                TTSRequest(text="Hello")
            )
