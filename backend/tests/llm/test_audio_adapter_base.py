import pytest

from app.llm.adapters.audio.base import (
    BaseAudioGenerationAdapter,
    BaseSTTAdapter,
    BaseTTSAdapter,
)
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
