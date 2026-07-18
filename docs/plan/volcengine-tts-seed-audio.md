# Volcengine TTS and Seed Audio Support

## Background & Goals

Volcengine Ark is already available for chat, embeddings, rerank, image, and video models. This work adds two separate OpenSpeech capabilities:

- Doubao TTS 2.0 (`tts`), converting text and a configured speaker ID to audio.
- Seed Audio 1.0 (`audio_generation`), creating audio from a prompt with optional references.

It excludes speech recognition. The existing `volcengine` provider code remains unchanged. `api_key` holds `X-Api-Key`, `model_id` holds `X-Api-Resource-Id`, and speaker/provider options remain in `default_params` or `config`.

## High-Level Design

OpenSpeech is not Ark `/api/v3`: dedicated audio adapters use OpenSpeech headers and capability-specific endpoints. The existing Ark bearer client remains only for image/video APIs.

`ModelType.AUDIO_GENERATION` is string-backed, so the existing `CharField(max_length=20)` stores the new value without a schema migration. The shared manager receives a provider-neutral request/response boundary; adapters remain storage-agnostic.

## Confirmed Contracts

### TTS

The official HTTP Chunked/SSE V3 page confirms:

- SSE endpoint: `POST https://openspeech.bytedance.com/api/v3/tts/unidirectional/sse`.
- Headers: `X-Api-Key`, `X-Api-Resource-Id`, and optional UUID `X-Api-Request-Id`; SSE responds with `Content-Type: text/event-stream`.
- Resource ID example: `seed-tts-2.0`.
- Request envelope:

```json
{
  "req_params": {
    "text": "你好，这是通过 HTTP 接口合成的语音。",
    "speaker": "zh_female_vv_uranus_bigtts",
    "audio_params": {
      "format": "mp3",
      "sample_rate": 24000
    }
  }
}
```

The SSE response uses `event:` and `data:` lines. Event `352` (`TTSResponse`) carries a JSON object whose `data` is base64 audio. Event `152` (`SessionFinish`) completes successfully with code `20000000`; event `153` is `SessionFailed`. Documented failures include text limit `40402003`, permission/concurrency `45000000`, and server error `55000000`.

Source: https://www.volcengine.com/docs/6561/1598757

### Seed Audio

The official Audio Generation HTTP page confirms:

- Endpoint: `POST https://openspeech.bytedance.com/api/v3/tts/create`.
- Authentication: `X-Api-Key`; optional UUID `X-Api-Request-Id`.
- Body: `model` (currently only `seed-audio-1.0`), `text_prompt`, optional `references`, and `audio_config`.
- References accept `audio_url`/`audio_data`/`speaker` or `image_url`/`image_data`. Image and audio references cannot be mixed. Limits are one image or three audio clips.
- `audio_config.format` accepts `wav`, `mp3`, `pcm`, or `ogg_opus`; sample rates are 8000, 16000, 24000, 32000, 44100, or 48000.
- The response contains `code`, `message`, base64 `audio`, optional two-hour `url`, `duration`, and `original_duration`.

Source: https://www.volcengine.com/docs/6561/2550782?lang=zh

## Implementation Plan

### Stage 1: Types and routing

- Add `audio_generation` model type, request/response types, adapter base/factory, and `ModelManager.generate_audio()`.
- Preserve OpenAI/Azure TTS and all STT behavior.

### Stage 2: TTS adapter

- Implement only after recording the current OpenSpeech streaming contract.
- Resolve speaker in order: request voice, `default_params.speaker`/`voice`, then `config`.
- Return a base64 `AudioContent`; never log credentials or audio payloads.

### Stage 3: Seed Audio adapter

- Implement only after recording the exact current HTTP request/response contract.
- Enforce one image and three audio-reference limits.
- Parse only documented output fields, never recursively search arbitrary responses for URLs/base64 strings.

### Stage 4: Connection testing and management UI

- Test minimal real TTS/audio calls, discard output, and disclose potential generation charges.
- Expose Volcengine for TTS and audio generation, not STT.
- Prevent the Ark default base URL from being populated for OpenSpeech model types.

## Testing Strategy

Mock OpenSpeech HTTP responses. Cover header/payload construction, speaker precedence, request limits, malformed/empty outputs, provider errors, manager routing, and model-test dispatch. Run backend format/lint/type checks, frontend translation generation/lint/build, and `git diff --check`. Do not use browser tests.

## Risks & Mitigation

- **Separate services**: never reuse Ark bearer client or alter the global Ark base URL.
- **Account-specific resources**: preserve manually entered resource and speaker IDs; do not add a catalog.
- **Billable probes**: make connection tests minimal and discard generated media.
- **Undocumented Seed Audio schema**: stop at the documented contract gate, rather than guessing.

## Rollback

Remove frontend exposure and the audio-generation routing/factory additions. Existing string rows remain inert; no database migration rollback is needed.
