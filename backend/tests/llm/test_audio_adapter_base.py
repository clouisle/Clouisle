from types import SimpleNamespace

import pytest

from app.llm.adapters import audio
from app.llm.adapters.audio.base import (
    BaseAudioGenerationAdapter,
    BaseSTTAdapter,
    BaseTTSAdapter,
)
from app.llm.errors import UnsupportedOperationError
from app.llm.types import (
    AudioContent,
    AudioGenerationRequest,
    AudioGenerationResponse,
    STTRequest,
    STTResponse,
    TTSRequest,
    TTSResponse,
)


@pytest.mark.parametrize(
    "adapter_class",
    [BaseTTSAdapter, BaseAudioGenerationAdapter, BaseSTTAdapter],
)
def test_audio_adapter_bases_require_concrete_implementations(
    adapter_class: type,
) -> None:
    with pytest.raises(TypeError, match="abstract method"):
        adapter_class()


@pytest.mark.asyncio
async def test_concrete_audio_adapter_implementations_are_awaitable() -> None:
    tts_response = TTSResponse(
        audio=AudioContent(base64="YQ==", format="mp3"), model="test"
    )
    generation_response = AudioGenerationResponse(
        audio=AudioContent(base64="YQ==", format="mp3"), model="test"
    )
    stt_response = STTResponse(text="hello", model="test")

    class TTSAdapter(BaseTTSAdapter):
        async def synthesize(self, request: TTSRequest) -> TTSResponse:
            assert request.text == "hello"
            return tts_response

    class AudioGenerationAdapter(BaseAudioGenerationAdapter):
        async def generate(
            self, request: AudioGenerationRequest
        ) -> AudioGenerationResponse:
            assert request.prompt == "hello"
            return generation_response

    class STTAdapter(BaseSTTAdapter):
        async def transcribe(self, request: STTRequest) -> STTResponse:
            assert request.audio.base64 == "YQ=="
            return stt_response

    assert await TTSAdapter().synthesize(TTSRequest(text="hello")) is tts_response
    assert (
        await AudioGenerationAdapter().generate(AudioGenerationRequest(prompt="hello"))
        is generation_response
    )
    assert (
        await STTAdapter().transcribe(
            STTRequest(audio=AudioContent(base64="YQ==", format="mp3"))
        )
        is stt_response
    )


@pytest.mark.parametrize(
    ("factory_name", "provider", "adapter_name"),
    [
        ("create_tts_adapter", "openai", "OpenAITTSAdapter"),
        ("create_tts_adapter", "azure_openai", "OpenAITTSAdapter"),
        ("create_tts_adapter", "volcengine", "VolcengineTTSAdapter"),
        ("create_tts_adapter", "minimax", "MiniMaxTTSAdapter"),
        (
            "create_audio_generation_adapter",
            "volcengine",
            "VolcengineAudioGenerationAdapter",
        ),
        ("create_stt_adapter", "openai", "OpenAISTTAdapter"),
        ("create_stt_adapter", "azure_openai", "OpenAISTTAdapter"),
    ],
)
def test_audio_factories_select_adapter_without_calling_provider(
    monkeypatch: pytest.MonkeyPatch,
    factory_name: str,
    provider: str,
    adapter_name: str,
) -> None:
    config = SimpleNamespace(provider=provider)
    created: list[object] = []

    def adapter_factory(model_config: object) -> object:
        created.append(model_config)
        return adapter_name

    monkeypatch.setattr(audio, adapter_name, adapter_factory)

    assert getattr(audio, factory_name)(config) == adapter_name
    assert created == [config]


@pytest.mark.parametrize(
    ("factory_name", "provider", "operation"),
    [
        ("create_tts_adapter", "unsupported", "text_to_speech"),
        ("create_audio_generation_adapter", "openai", "audio_generation"),
        ("create_stt_adapter", "unsupported", "speech_to_text"),
    ],
)
def test_audio_factories_reject_unsupported_providers(
    factory_name: str, provider: str, operation: str
) -> None:
    with pytest.raises(UnsupportedOperationError) as exc_info:
        getattr(audio, factory_name)(SimpleNamespace(provider=provider))

    assert exc_info.value.operation == operation
    assert exc_info.value.provider == provider
