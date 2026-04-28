# Text-to-Image Defaults First Batch Design Document

## Background & Goals

- Problem to solve: text-to-image models can store provider-specific runtime defaults in `default_params`, but current image adapters mostly ignore those defaults and only read first-class request fields or `extra_params`. This makes admin-configured image settings ineffective at runtime.
- Success criteria:
  - Image adapters can read effective runtime params from `model_config.default_params` with clear precedence.
  - Explicit request fields still override model defaults.
  - OpenAI/Azure/Custom image payloads support the first batch of GPT Image defaults without breaking DALL-E behavior.
  - Google and Stability model dialogs expose the requested known params as first-class controls and persist them in `default_params`.
  - Targeted backend tests cover the new precedence and payload mapping.

## High-Level Design

This change adds a small shared helper at the image-adapter layer so text-to-image adapters can safely compute effective values from three sources:
1. explicit request fields
2. `request.extra_params`
3. `model_config.default_params`

Precedence remains: explicit request field or request `extra_params` wins over model defaults. The helper only reads known keys and returns object copies so adapters can merge provider-specific payloads locally.

Provider handling stays narrow:
- OpenAI / Azure OpenAI / Custom: support `background`, `output_format`, and `output_compression`, plus model-aware quality handling for GPT Image vs DALL-E.
- Google: keep existing explicit config mapping, but source values from merged effective params so stored defaults actually apply.
- Stability: keep current form-data shape, but source `style_preset` / `output_format` defaults from merged effective params.

Frontend changes stay in the existing model dialog, extending the current image section with conditional provider-specific controls and preserving unknown JSON extension keys.

## Implementation Plan

### Stage 1: Add planning docs and image runtime merge helper
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/text-to-image-defaults-first-batch.md`, `backend/app/llm/adapters/image/base.py`
- **Specific logic**:
  - Register this feature in the implementation index.
  - Add a small shared helper in the image adapter base for effective default lookup and merged provider param access.
  - Keep the helper limited to image adapters rather than introducing a broader cross-media abstraction.
- **Validation**:
  - Confirm the helper expresses precedence clearly in code.
  - Confirm existing adapters can adopt it with small local changes.

### Stage 2: Update OpenAI-family image payload behavior
- **Files modified**: `backend/app/llm/adapters/image/openai.py`, `backend/app/llm/tools/builtin/media.py`
- **Specific logic**:
  - Merge OpenAI-family image defaults from `default_params` and `extra_params`.
  - Support `background`, `output_format`, and `output_compression` for GPT Image style models.
  - Keep DALL-E-specific behavior such as `response_format=url`, style handling, and narrower quality semantics where required.
  - Make tool-side quality normalization model-aware so GPT Image accepts broader quality values without weakening DALL-E validation.
- **Validation**:
  - Assert GPT Image payload includes defaulted params when request omits them.
  - Assert explicit request values still win.
  - Assert unsupported DALL-E quality values are still rejected.

### Stage 3: Flow defaults through Google and Stability adapters
- **Files modified**: `backend/app/llm/adapters/image/google.py`, `backend/app/llm/adapters/image/stability.py`
- **Specific logic**:
  - Source Google image config values from effective merged params while preserving explicit overrides and nested `image_config` behavior.
  - Source Stability `style_preset` and `output_format` defaults from effective merged params.
  - Avoid expanding into unrelated providers.
- **Validation**:
  - Assert Google config mapping reads from `default_params`.
  - Assert Stability form payload reads stored defaults while allowing explicit overrides.

### Stage 4: Extend frontend model dialog for first-batch image providers
- **Files modified**: `frontend/app/(dashboard)/models/_components/model-dialog.tsx`, `frontend/i18n/en/models.json`, `frontend/i18n/zh/models.json`, generated `frontend/i18n/types/models.ts`
- **Specific logic**:
  - Keep the existing generic image fields.
  - Add conditional provider-specific sections for OpenAI/Azure/Custom, Google, and Stability.
  - Load/reset/save these values through `model.default_params`.
  - Expand `MANAGED_DEFAULT_PARAM_KEYS` so JSON extension preservation still works.
- **Validation**:
  - Re-open an edited model and verify dedicated fields round-trip.
  - Verify unmanaged keys remain in the JSON extension area.

### Stage 5: Add targeted tests and run focused checks
- **Files modified**: `backend/tests/llm/test_media_adapters.py`, `backend/tests/llm/test_media_builtin_tools.py`
- **Specific logic**:
  - Add payload/default precedence tests for OpenAI GPT Image, Google, and Stability.
  - Add media tool tests for model-aware quality normalization.
  - Run requested backend and frontend checks where the environment allows.
- **Validation**:
  - Backend: `uv run mypy app/llm/adapters/image app/llm/tools/builtin/media.py`
  - Backend: `uv run pytest backend/tests/llm/test_media_adapters.py backend/tests/llm/test_media_builtin_tools.py backend/tests/llm/test_chat_media_tool_summaries.py`
  - Frontend: `node scripts/gen-i18n-types.ts`, `node scripts/lint-translations.ts --strict`, `bun run lint`

## Testing Strategy

### Happy Path Tests
- OpenAI GPT Image model with admin `default_params` for `background`, `output_format`, and `output_compression` should include them in the generated payload.
- Google image model with stored `aspect_ratio`, `image_size`, `person_generation`, `prominent_people`, `output_mime_type`, and `output_compression_quality` should map them into `image_config`.
- Stability model with stored `style_preset` / `output_format` should emit matching form fields.
- Reopening a frontend model config should show saved provider-specific values.

### Error Path Tests
- DALL-E/OpenAI-compatible tool quality validation should still reject unsupported values when the model family requires the old behavior.
- Invalid JSON in frontend default-params extension should still fail validation.
- Explicit request overrides should beat stored defaults for all touched providers.

### Regression Scope
- Existing generic image fields (`size`, `style`, `quality`) continue to save and apply.
- Unmanaged `default_params` JSON keys remain preserved after edit/save.
- Unrelated image providers stay untouched.

## Risks & Mitigation

- Possible side effect: provider defaults could accidentally override explicit request values.
  - Mitigation: centralize precedence in the shared helper and cover it with tests.
- Possible side effect: GPT Image and DALL-E quality rules diverge incorrectly.
  - Mitigation: keep model-family branching local and test both paths.
- Possible side effect: frontend dedicated fields could strip unknown keys.
  - Mitigation: extend managed-key filtering only for known first-class fields and keep JSON extension merging intact.

- Rollback plan: revert the shared helper adoption per adapter and remove the dedicated frontend fields if provider semantics prove incorrect.