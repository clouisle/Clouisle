from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.llm.adapters.audio import (
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
