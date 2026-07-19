# Admin Video Model Generation Test Design Document

## Background & Goals

The admin video model “connection test” currently validates only basic API-key shape and adapter construction. It performs no provider request, so invalid credentials, endpoints, or model access can be reported as successful.

Success criteria:

- Testing a `text_to_video` model creates one real video-generation task.
- The test polls the provider until a terminal status and succeeds only with video content.
- It uses the configured duration, or the existing five-second request default when absent.
- Both saved and unsaved model test entry points behave identically.
- Admins explicitly confirm the potentially billable operation before it starts.

## High-Level Design

```text
Admin confirmation
  -> create_video_adapter()
  -> generate(VideoGenerationRequest)
  -> get_status(task_id) until terminal
  -> COMPLETED with VideoContent
```

The admin endpoint reuses the provider-neutral adapter interface. Polling remains local to the model-test helper because provider clients are inconsistent and MiniMax has no wait helper. No provider-specific duration table is added: configured values pass through the existing common and provider validation boundaries.

## Implementation Plan

### Stage 1: Real Generation and Polling

- **Files modified**: `backend/app/api/v1/admin/endpoints/models.py`
- **Specific logic**:
  - Make `_test_video_model` asynchronous and pass `default_params` from saved and unsaved test routes.
  - Build the temporary model with defaults and config, then generate one simple text-to-video request.
  - Use configured duration/aspect ratio when present and existing request defaults otherwise.
  - Poll `get_status()` with the existing `poll_interval_ms` and `poll_timeout_s` conventions.
  - Accept only completed responses with non-empty video content; fail on provider failure, cancellation, missing content, or timeout.
- **Validation**: mocked immediate completion, multi-step polling, terminal failures, missing output, and timeout.

### Stage 2: Billable-Operation Confirmation

- **Files modified**: `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, `frontend/app/(dashboard)/models/_components/models-client.tsx`, `frontend/i18n/en/models.json`, `frontend/i18n/zh/models.json`
- **Specific logic**:
  - Use a native confirmation before either video test request enters its loading state.
  - State that the test generates a real video, may incur provider charges, and can take time.
  - Include the current video duration and aspect ratio in the unsaved test payload.
  - Keep non-video model tests unchanged.
- **Validation**: cancellation sends no request; confirmation sends one request; English and Chinese catalogs remain aligned.

### Stage 3: Regression Coverage

- **Files modified**: `backend/tests/llm/test_admin_model_test_config.py`
- **Specific logic**:
  - Mock adapters rather than calling paid provider APIs.
  - Cover request defaults/configuration, model config forwarding, polling, terminal states, empty output, timeout, and endpoint routing.
- **Validation**: focused pytest, Ruff, frontend lint/build, translation checks, and `git diff --check`.

## Testing Strategy

Happy paths:

- Configured shortest supported duration reaches the adapter.
- No configured duration uses the existing five-second default.
- Immediate and polled completion with video content report success.

Error paths:

- Invalid common duration fails before provider submission.
- Provider failure/cancellation and completed-without-video report failure.
- Pending tasks exceeding the configured deadline report timeout.
- Cancelling the frontend warning sends no request.

Regression scope:

- Image, TTS, chat, embedding, rerank, STT, and audio-generation model tests remain unchanged.
- Existing video adapters and workflow generation continue using the same contracts.

## Risks & Mitigation

- **Provider charges**: require explicit confirmation and submit only one task.
- **Different model constraints**: use configured duration and provider validation; do not hard-code one second.
- **Long-running tasks**: use the existing configurable polling window and return a clear timeout failure.
- **Temporary output URLs**: verify content presence only; do not persist the test asset.

Rollback: restore constructor-only `_test_video_model`, remove the two confirmations and translation key, and remove the focused tests. No schema or migration is involved.
