from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.llm.adapters.audio import (
    MiniMaxTTSAdapter,
    VolcengineAudioGenerationAdapter,
    VolcengineTTSAdapter,
    create_audio_generation_adapter,
    create_tts_adapter,
)
from app.llm.errors import InvalidRequestError, ProviderError, UnsupportedOperationError
from app.llm.manager import ModelManager
from app.llm.types import (
    AudioContent,
    AudioGenerationRequest,
    AudioGenerationResponse,
    ImageContent,
    TTSRequest,
)
from app.models.model import ModelProvider, ModelType


def test_audio_generation_request_limits_audio_references():
    with pytest.raises(ValidationError):
        AudioGenerationRequest(
            prompt="Create ocean ambience",
            audio_references=[AudioContent(base64="YQ==") for _ in range(4)],
        )


def test_audio_generation_factory_rejects_unsupported_provider():
    with pytest.raises(UnsupportedOperationError):
        create_audio_generation_adapter(SimpleNamespace(provider="openai"))


def build_volcengine_model(model_id: str, **kwargs):
    return SimpleNamespace(
        provider=ModelProvider.VOLCENGINE,
        model_id=model_id,
        api_key="test-key",
        base_url=None,
        default_params=kwargs.get("default_params", {}),
        config=kwargs.get("config", {}),
    )


def test_minimax_tts_factory_and_payload():
    model = SimpleNamespace(
        provider=ModelProvider.MINIMAX,
        model_id="speech-2.8-hd",
        api_key="test-key",
        base_url=None,
        default_params={
            "voice": "male-qn-qingse",
            "speed": 0.8,
            "format": "wav",
            "sample_rate": 32000,
        },
        config={},
    )
    adapter = create_tts_adapter(model)

    assert isinstance(adapter, MiniMaxTTSAdapter)
    assert adapter._build_payload(TTSRequest(text="Hello", speed=1.25)) == {
        "model": "speech-2.8-hd",
        "text": "Hello",
        "stream": False,
        "output_format": "hex",
        "voice_setting": {"voice_id": "male-qn-qingse", "speed": 1.25},
        "audio_setting": {"format": "wav", "sample_rate": 32000},
    }
    assert (
        adapter._build_payload(TTSRequest(text="Hello"))["voice_setting"]["speed"]
        == 0.8
    )


@pytest.mark.anyio
async def test_minimax_tts_decodes_hex_audio():
    model = SimpleNamespace(
        provider=ModelProvider.MINIMAX,
        model_id="speech-2.8-hd",
        api_key="test-key",
        base_url=None,
        default_params={"voice": "male-qn-qingse"},
        config={},
    )
    adapter = MiniMaxTTSAdapter(model)
    adapter.client = SimpleNamespace(
        request=AsyncMock(return_value={"data": {"audio": "6869"}})
    )

    response = await adapter.synthesize(TTSRequest(text="Hello"))

    assert response.audio.base64 == "aGk="
    assert response.audio.format == "mp3"
    adapter.client.request.assert_awaited_once_with(
        "POST",
        "/t2a_v2",
        json={
            "model": "speech-2.8-hd",
            "text": "Hello",
            "stream": False,
            "output_format": "hex",
            "voice_setting": {"voice_id": "male-qn-qingse", "speed": 1.0},
            "audio_setting": {"format": "mp3"},
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize("audio", [None, "not-hex", ""])
async def test_minimax_tts_rejects_missing_or_invalid_provider_audio(audio):
    adapter = MiniMaxTTSAdapter(
        SimpleNamespace(
            provider=ModelProvider.MINIMAX,
            model_id="speech-2.8-hd",
            api_key="test-key",
            base_url=None,
            default_params={"voice": "male-qn-qingse"},
            config={},
        )
    )
    adapter.client = SimpleNamespace(
        request=AsyncMock(return_value={"data": {"audio": audio}})
    )

    with pytest.raises(ProviderError):
        await adapter.synthesize(TTSRequest(text="Hello"))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tts_request",
    [
        TTSRequest(text=""),
        TTSRequest(text="Hello", format="opus"),
    ],
)
async def test_minimax_tts_rejects_invalid_request_before_provider_call(tts_request):
    adapter = MiniMaxTTSAdapter(
        SimpleNamespace(
            provider=ModelProvider.MINIMAX,
            model_id="speech-2.8-hd",
            api_key="test-key",
            base_url=None,
            default_params={"voice": "male-qn-qingse"},
            config={},
        )
    )
    adapter.client = SimpleNamespace(request=AsyncMock())

    with pytest.raises(InvalidRequestError):
        await adapter.synthesize(tts_request)

    adapter.client.request.assert_not_awaited()


def test_minimax_tts_rejects_provider_speed_range():
    model = SimpleNamespace(
        provider=ModelProvider.MINIMAX,
        model_id="speech-2.8-hd",
        api_key="test-key",
        base_url=None,
        default_params={"voice": "male-qn-qingse"},
        config={},
    )
    adapter = MiniMaxTTSAdapter(model)

    with pytest.raises(InvalidRequestError):
        adapter._build_payload(TTSRequest(text="Hello", speed=3))


def test_volcengine_audio_factories():
    assert isinstance(
        create_tts_adapter(build_volcengine_model("seed-tts-2.0")),
        VolcengineTTSAdapter,
    )
    assert isinstance(
        create_audio_generation_adapter(build_volcengine_model("seed-audio-1.0")),
        VolcengineAudioGenerationAdapter,
    )


def test_volcengine_tts_builds_official_payload_with_speaker_precedence():
    adapter = VolcengineTTSAdapter(
        build_volcengine_model(
            "seed-tts-2.0",
            default_params={"speaker": "configured", "sample_rate": 48000},
        )
    )

    payload, audio_format = adapter._build_payload(
        TTSRequest(text="Hello", voice="runtime", speed=1.5, format="mp3")
    )

    assert payload["req_params"] == {
        "text": "Hello",
        "speaker": "runtime",
        "audio_params": {
            "format": "mp3",
            "sample_rate": 48000,
            "speech_rate": 50,
        },
    }
    assert audio_format == "mp3"
    assert adapter._headers()["X-Api-Resource-Id"] == "seed-tts-2.0"


def test_volcengine_tts_parses_audio_and_completion_events():
    adapter = VolcengineTTSAdapter(build_volcengine_model("seed-tts-2.0"))

    chunks, completed = adapter._consume_event(
        "352", '{"code":0,"message":"","data":"YQ=="}'
    )
    assert chunks == [b"a"]
    assert completed is False
    assert adapter._consume_event(
        "152", '{"code":20000000,"message":"OK","data":null}'
    ) == ([], True)


def test_volcengine_tts_rejects_provider_error_event():
    adapter = VolcengineTTSAdapter(build_volcengine_model("seed-tts-2.0"))
    with pytest.raises(ProviderError, match="permission denied"):
        adapter._consume_event("153", '{"code":45000000,"message":"permission denied"}')


def test_seed_audio_builds_documented_reference_payload():
    adapter = VolcengineAudioGenerationAdapter(build_volcengine_model("seed-audio-1.0"))
    payload, audio_format = adapter._build_payload(
        AudioGenerationRequest(
            prompt="Use @音频1 as a reference",
            audio_references=[AudioContent(base64="YQ==", format="wav")],
            format="ogg_opus",
        )
    )

    assert payload == {
        "model": "seed-audio-1.0",
        "text_prompt": "Use @音频1 as a reference",
        "audio_config": {"format": "ogg_opus", "sample_rate": 24000},
        "references": [{"audio_data": "YQ=="}],
    }
    assert audio_format == "ogg_opus"


def test_seed_audio_rejects_mixed_image_and_audio_references():
    adapter = VolcengineAudioGenerationAdapter(build_volcengine_model("seed-audio-1.0"))
    with pytest.raises(InvalidRequestError):
        adapter._build_payload(
            AudioGenerationRequest(
                prompt="Mixed references",
                image=ImageContent(url="https://example.com/reference.png"),
                audio_references=[AudioContent(base64="YQ==")],
            )
        )


def test_seed_audio_payload_uses_default_params_before_config_and_runtime_format():
    adapter = VolcengineAudioGenerationAdapter(
        build_volcengine_model(
            "seed-audio-1.0",
            default_params={"format": "wav", "sample_rate": 48000, "speech_rate": 1.1},
            config={"format": "mp3", "sample_rate": 16000, "speech_rate": 0.8},
        )
    )

    payload, audio_format = adapter._build_payload(
        AudioGenerationRequest(
            prompt="Ocean", format="mp3", extra_params={"speech_rate": 1.5}
        )
    )

    assert audio_format == "mp3"
    assert payload["audio_config"] == {
        "format": "mp3",
        "sample_rate": 48000,
        "speech_rate": 1.5,
    }


def test_seed_audio_rejects_invalid_model_format_and_sample_rate():
    adapter = VolcengineAudioGenerationAdapter(build_volcengine_model("other"))
    with pytest.raises(InvalidRequestError, match="requires seed-audio-1.0"):
        adapter._build_payload(AudioGenerationRequest(prompt="Ocean"))

    adapter = VolcengineAudioGenerationAdapter(
        build_volcengine_model("seed-audio-1.0", default_params={"sample_rate": 12345})
    )
    with pytest.raises(InvalidRequestError, match="sample rate"):
        adapter._build_payload(AudioGenerationRequest(prompt="Ocean"))


def test_seed_audio_converts_data_uri_and_rejects_invalid_image_file(tmp_path):
    adapter = VolcengineAudioGenerationAdapter(build_volcengine_model("seed-audio-1.0"))
    payload, _ = adapter._build_payload(
        AudioGenerationRequest(
            prompt="Ocean",
            image=ImageContent(base64="data:image/png;base64,YQ=="),
        )
    )
    assert payload["references"] == [{"image_data": "YQ=="}]

    invalid_file = tmp_path / "reference.txt"
    invalid_file.write_text("not an image")
    with pytest.raises(InvalidRequestError, match="image reference"):
        adapter._reference(ImageContent(file_path=str(invalid_file)), "image")


@pytest.mark.anyio
async def test_seed_audio_generate_maps_success_and_provider_responses():
    adapter = VolcengineAudioGenerationAdapter(build_volcengine_model("seed-audio-1.0"))
    response = httpx.Response(
        200,
        json={"code": 20000000, "audio": "YQ==", "duration": "1.25"},
        request=httpx.Request("POST", adapter.base_url),
    )
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client

    with patch("httpx.AsyncClient", return_value=client):
        result = await adapter.generate(AudioGenerationRequest(prompt="Ocean"))

    assert result.audio.base64 == "YQ=="
    assert result.audio.duration == 1.25
    assert result.audio.format == "mp3"

    response = httpx.Response(
        200,
        json={"code": 400, "message": "denied"},
        request=httpx.Request("POST", adapter.base_url),
    )
    client.post.return_value = response
    with (
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(ProviderError, match="denied"),
    ):
        await adapter.generate(AudioGenerationRequest(prompt="Ocean"))

    client.post.side_effect = httpx.TimeoutException("slow")
    with (
        patch("httpx.AsyncClient", return_value=client),
        pytest.raises(ProviderError, match="timeout"),
    ):
        await adapter.generate(AudioGenerationRequest(prompt="Ocean"))


@pytest.mark.anyio
async def test_model_manager_routes_audio_generation_model():
    model = SimpleNamespace(
        provider="volcengine",
        model_id="seed-audio-1.0",
    )
    response = AudioGenerationResponse(
        audio=AudioContent(base64="YXVkaW8=", format="mp3"),
        model="seed-audio-1.0",
    )
    adapter = SimpleNamespace(generate=AsyncMock(return_value=response))
    manager = ModelManager()
    manager._get_model_config = AsyncMock(return_value=model)

    with patch("app.llm.manager.create_audio_generation_adapter", return_value=adapter):
        result = await manager.generate_audio({"prompt": "Create ocean ambience"})

    manager._get_model_config.assert_awaited_once_with(None, ModelType.AUDIO_GENERATION)
    adapter.generate.assert_awaited_once()
    assert result == response
