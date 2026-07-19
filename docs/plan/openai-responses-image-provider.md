# OpenAI Responses Image Provider Design Document

## Background & Goals

The media tool already treats reference images as optional. The reported `call_methods must include images` error is instead an upstream protocol-capability mismatch: the configured compatible gateway does not accept the request through its current Images API route.

Add an explicit `openai_responses` provider for text-to-image models. It selects the OpenAI Responses API and hosted `image_generation` tool without model-name detection or error-driven fallback. Existing `openai` models keep using `/images/generations` unchanged.

Success criteria:
- Prompt-only generation remains valid.
- Optional URL/base64/file reference images are sent as Responses `input_image` content.
- Responses image outputs normalize into the existing media result types.
- The provider is selectable only for image models.
- Existing OpenAI Images API behavior does not change.

## High-Level Design

The model provider is the protocol boundary:

- `openai` → existing OpenAI Images API adapter.
- `openai_responses` → new Responses API image adapter.

`ModelManager.generate_image()` continues resolving a text-to-image model and calling the existing image-adapter factory. The new adapter converts `ImageGenerationRequest` into Responses input, calls the hosted image tool, and returns `ImageGenerationResponse`. Existing media asset persistence and frontend/workflow consumers remain provider-neutral.

No database migration is needed because provider identifiers are stored in a varchar. Responses chat, LangChain integration, Images API edits, and protocol fallback are outside this change.

## Implementation Plan

### Stage 1: Provider Registration and Routing

- **Files modified**: `backend/app/models/model.py`, `backend/app/schemas/model.py`, `backend/app/llm/adapters/image/__init__.py`
- **Specific logic**:
  - Add `openai_responses` to both provider enums and provider defaults.
  - Route only this provider to `OpenAIResponsesImageAdapter`.
  - Keep `openai`, `azure_openai`, and `custom` on `OpenAIImageAdapter`.
- **Validation**:
  - Factory test asserts both new and legacy routes.
  - Confirm no migration or seed change is generated.

### Stage 2: Responses Image Adapter

- **Files modified**: `backend/app/llm/adapters/image/openai_responses.py`
- **Specific logic**:
  - Use the installed OpenAI SDK Responses client.
  - Convert the prompt to `input_text`; append style and negative-prompt directives using `append_prompt_directives()`.
  - Convert optional references with `image_content_to_data_uri()` and add `input_image` parts only when present.
  - Build a strict, verified hosted `image_generation` tool payload using existing image default/request precedence helpers.
  - Parse `image_generation_call.result` into `GeneratedImage` values.
  - Raise `InvalidRequestError` when no usable image is returned.
  - Generate multiple requested images sequentially when the API provides no count option, stopping as soon as enough results exist.
- **Validation**:
  - Test prompt-only and referenced requests.
  - Test parameter location/precedence, output parsing, empty output, and image count behavior.
  - Trigger invalid input to confirm fail-fast errors.

### Stage 3: Frontend Provider Exposure

- **Files modified**: `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, `frontend/i18n/en/models.json`, `frontend/i18n/zh/models.json`, generated `frontend/i18n/types/models.ts`
- **Specific logic**:
  - Show `openai_responses` in the international provider group only for image models.
  - Reuse current image controls only for Responses-supported settings.
  - Restrict size/quality choices to Responses-supported values.
  - Add synchronized provider labels and regenerate i18n types.
- **Validation**:
  - Verify the provider is absent for chat/rerank/audio/video.
  - Save/reopen an image model and verify defaults round-trip.
  - Run translation generation and strict translation lint.

### Stage 4: Regression and Quality Checks

- **Files modified**: `backend/tests/llm/test_media_adapters.py`, `docs/IMPLEMENTATION_PLAN.md`
- **Specific logic**:
  - Add focused adapter/factory regression tests.
  - Re-run existing media-tool optional-reference tests.
  - Run backend static checks and frontend lint/build.
  - Mark the implementation index complete only after checks pass.
- **Validation**:
  - Existing OpenAI image tests prove `/images/generations` behavior remains intact.
  - Responses-compatible endpoint validates prompt-only and reference-image generation end to end.

## Testing Strategy

### Happy Path

- Configure an `openai_responses` text-to-image model.
- Generate from a prompt without images.
- Generate from a prompt with URL and base64 reference images.
- Request multiple images and receive exactly that count.
- Preserve configured output format and supported tool defaults.

### Error Path

- Invalid Responses-only enum values fail before the remote request.
- A reference without URL/base64/file path fails through the shared converter.
- A completed response without an image result raises `InvalidRequestError`.
- Upstream authentication, rate-limit, bad-request, and transport failures map to existing LLM errors without protocol fallback.

### Regression Scope

- Existing `openai`, Azure OpenAI, and custom image routing.
- Built-in media tool optional `images` schema.
- Workflow and Agent reference selection.
- Admin provider grouping and model-default persistence.
- Frontend translation type alignment.

## Risks & Mitigation

- **Gateway lacks Responses image support**: surface its error; never fall back to another protocol.
- **SDK/API shape changes**: confirm installed SDK types and official documentation, then lock the payload with tests.
- **Images API parameters leak into Responses**: use a strict allowlist and provider-specific frontend choices.
- **Multiple requests increase cost/rate usage**: use a sequential early-stopping loop.
- **Legacy behavior changes**: keep adapters separate and retain a legacy factory assertion.

Rollback removes the new provider route and provider records. Existing `openai` records and runtime behavior remain untouched.
