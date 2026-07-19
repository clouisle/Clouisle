# MiniMax Media Integration Design Document

## Background & Goals

MiniMax is already a registered provider, and Clouisle already has provider-neutral image, video, and TTS model types. The missing layer is MiniMax's proprietary media API adapters; its OpenAI-compatible text adapter cannot call the image, video, or speech endpoints.

Success criteria:

- MiniMax `image-01` and `image-01-live` support text and reference-image generation.
- MiniMax Hailuo models support text and first-frame video generation through existing polling.
- MiniMax Speech models support synchronous TTS.
- Admin model management exposes MiniMax for image, video, and TTS.
- Existing image/video workflow nodes work without provider-specific changes.

Out of scope: workflow TTS, asynchronous TTS, WebSocket/SSE, callbacks, voice cloning/design, STT, and prompt-to-audio.

## High-Level Design

```text
Model / TeamModel
  -> ModelManager
  -> existing adapter factory
  -> MiniMax HTTP adapter
  -> existing Image/Video/TTS response types
  -> existing asset normalization and workflow execution
```

A small shared MiniMax HTTP client owns Bearer authentication, base URL normalization, transport failures, and `base_resp` application errors. Each media adapter owns its payload and response contract.

The configured model `base_url` wins. The fallback remains the existing domestic MiniMax URL, `https://api.minimax.chat/v1`, without changing chat or embedding defaults. `default_params` and `config` carry provider-specific options; no schema or migration is needed.

## Implementation Plan

### Stage 1: Shared MiniMax HTTP Client

- **Files modified**: `backend/app/llm/adapters/minimax_client.py`
- **Specific logic**:
  - Use existing `httpx` with Bearer and JSON headers.
  - Resolve explicit `base_url` before the domestic fallback.
  - Map HTTP and `base_resp.status_code` failures to existing LLM errors.
  - Keep endpoint-specific parsing out of the client.
- **Validation**: unit checks for URL/header construction, explicit URL override, auth, rate limit, task-not-found, timeout, and application errors.

### Stage 2: Image Generation

- **Files modified**: `backend/app/llm/adapters/image/minimax.py`, `backend/app/llm/adapters/image/__init__.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - POST `/image_generation`.
  - Map prompt, count, seed, dimensions/aspect ratio and allowlisted MiniMax options.
  - Convert existing references to `subject_reference` with `image_content_to_data_uri`.
  - Parse URL and base64 output into `ImageGenerationResponse`.
- **Validation**: text/reference payloads, precedence, URL/base64 parsing, malformed and empty responses.

### Stage 3: Video Generation

- **Files modified**: `backend/app/llm/adapters/video/minimax.py`, `backend/app/llm/adapters/video/__init__.py`, `backend/tests/llm/test_media_adapters.py`
- **Specific logic**:
  - POST `/video_generation` and require `task_id`.
  - Map prompt, duration, first frame, and allowlisted resolution/provider options.
  - GET `/query/video_generation`, normalize statuses, then GET `/files/retrieve` for a successful `file_id`.
  - Do not translate workflow aspect ratio into resolution.
- **Validation**: creation, first frame, all statuses, task/file IDs, final URL, and failure paths.

### Stage 4: Synchronous TTS

- **Files modified**: `backend/app/llm/adapters/audio/minimax_tts.py`, `backend/app/llm/adapters/audio/__init__.py`, `backend/tests/llm/test_audio_generation.py`
- **Specific logic**:
  - POST non-streaming `/t2a_v2` with hex output.
  - Map voice, speed, format and allowlisted voice/audio settings using request-over-default precedence.
  - Validate MiniMax-specific boundaries and convert hex audio to `AudioContent.base64`.
- **Validation**: payload, precedence, hex decoding, required voice, speed/format limits, empty or invalid audio.

### Stage 5: Admin Exposure and i18n

- **Files modified**: `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, backend English/Chinese message catalogs, legacy catalog only if required by synchronization tooling.
- **Specific logic**:
  - Add MiniMax to existing image/video/TTS provider allowlists.
  - Add only error keys used by the adapters in both locales.
- **Validation**: model dialog provider filtering plus catalog synchronization checks.

### Stage 6: Validation

- **Files modified**: focused tests above and this design/index status.
- **Specific logic**: run focused pytest, Ruff, mypy, frontend lint/build, and i18n checks; run paid end-to-end calls only with authorized credentials.
- **Validation**: create/test three MiniMax model types; run image and video through the existing workflow; synthesize and decode a short TTS sample.

## Testing Strategy

Happy paths:

- Text-to-image and reference-image generation.
- Text-to-video and first-frame video generation through polling.
- Synchronous MP3 TTS from hex output.
- MiniMax availability in admin model type filters.

Error paths:

- Missing/invalid key, rate limit, timeout, HTTP 200 with failed `base_resp`.
- Missing image output, video task/file/download URL, and TTS audio.
- Invalid MiniMax image option and TTS voice/speed/format.

Regression scope:

- Existing MiniMax chat/embedding URLs remain unchanged.
- Existing providers' factory branches and model filters remain unchanged.
- Existing provider-neutral image/video workflows continue to pass.

## Risks & Mitigation

- **Domestic API contract uncertainty**: prefer explicit model `base_url`, retain the repository's domestic fallback, and confirm endpoint paths with authorized domestic documentation/account before live verification.
- **Temporary provider URLs**: continue through the existing media asset normalization layer; do not duplicate object storage in adapters.
- **Per-model video constraints**: let MiniMax validate changing duration/resolution combinations instead of hard-coding a stale matrix.
- **Paid calls**: mock contract tests by default; execute real calls only with user-provided authorization.

Rollback: remove the three MiniMax factory branches and adapter/client files, then remove the three frontend allowlist entries and MiniMax-specific translation keys. No data migration is involved.
