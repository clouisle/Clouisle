# Model Provider Params Extension Design Document

## Background & Goals

**Problem**: The admin model-management dialog currently exposes only a small fixed set of model parameters. Known provider-specific parameters such as DeepSeek/xAI `reasoning_effort`, Anthropic/Gemini thinking controls, and OpenAI-compatible `extra_body` cannot be configured consistently. In addition, editing an existing model rebuilds `default_params` / `config` from only known fields, silently dropping unknown keys.

**Success Criteria**:
- Known provider-specific params have dedicated UI fields where they are already understood.
- Unknown/future params can still be configured via JSON extension areas.
- Editing an existing model preserves unknown keys in `default_params` and `config`.
- Test Connection uses both `default_params` and `config`, so runtime params are validated before save.
- Chat adapters safely support provider-specific passthrough where the SDK/request shape allows it.

## High-Level Design

This change introduces a split model-config strategy:
1. **`default_params`** stores runtime request defaults and provider-specific request knobs.
2. **`config`** stores provider metadata / transport configuration and compatibility fields.
3. **Dedicated form fields** cover known provider params.
4. **JSON extension areas** preserve future flexibility for unknown params.
5. **Adapter-side normalization** applies consistent precedence: runtime kwargs > `default_params` > fallback `config`.

OpenAI-like providers (OpenAI, OpenAI-compatible, DeepSeek, xAI, Anthropic via SDK support) can safely use `extra_body` with reserved-key filtering. Gemini remains explicit mapping only because its request shape is nested and not a flat OpenAI-compatible body.

## Implementation Plan

### Stage 1: Extend Admin Test API and Base Adapter Param Helpers
**Files modified**:
- `backend/app/schemas/model.py`
- `backend/app/api/v1/admin/endpoints/models.py`
- `backend/app/llm/adapters/chat/base.py`

**Specific logic**:
- Add `default_params` to `ModelTestRequest`.
- Pass `default_params` into temporary test models and persisted model test calls.
- Add shared helpers in `BaseChatAdapter` for:
  - reading effective params with precedence
  - normalized `reasoning_effort`
  - normalized `extra_body`
  - normalized `thinking`
  - reserved-key filtering for passthrough payloads

**Validation**:
- Verify `/admin/models/test` accepts `default_params`.
- Verify adapter temp models can read `default_params`, `config`, and `max_output_tokens`.

### Stage 2: Add OpenAI-like Provider Runtime Param Support
**Files modified**:
- `backend/app/llm/adapters/chat/deepseek_adapter.py`
- `backend/app/llm/adapters/chat/openai_adapter.py`
- `backend/app/llm/adapters/chat/openai_compatible_adapter.py`
- `backend/app/llm/adapters/chat/xai_adapter.py`

**Specific logic**:
- DeepSeek: support `reasoning_effort`, `extra_body`, and `top_p`.
- OpenAI: support `reasoning_effort` and `extra_body` using SDK support.
- OpenAI-compatible: support `reasoning_effort`, `extra_body`, and `top_p`.
- xAI: normalize existing `reasoning_effort` through shared helper and add `extra_body`.
- Merge explicit request params first, then safe passthrough payload last with reserved-key filtering.

**Validation**:
- Add adapter-level payload assertions.
- Run model test calls using stored `default_params` values.

### Stage 3: Normalize Anthropic and Gemini Known Params
**Files modified**:
- `backend/app/llm/adapters/chat/anthropic_adapter.py`
- `backend/app/llm/adapters/chat/gemini_adapter.py`

**Specific logic**:
- Prefer `default_params.thinking` over `config.thinking`, while keeping `config` backward-compatible.
- Anthropic: retain explicit thinking/output_config behavior and add safe `extra_body` passthrough.
- Gemini: keep explicit mapping only; do not introduce blind passthrough.

**Validation**:
- Verify Anthropic `thinking` + `output_config` incompatibility still behaves correctly.
- Verify Gemini thinking budget is still mapped to `generation_config` correctly.

### Stage 4: Upgrade Admin Model Dialog for Known + Unknown Params
**Files modified**:
- `frontend/app/(dashboard)/models/_components/model-dialog.tsx`
- `frontend/lib/api/admin/models.ts`
- `frontend/i18n/en/models.json`
- `frontend/i18n/zh/models.json`
- generated `frontend/i18n/types/models.ts`

**Specific logic**:
- Add provider-specific dedicated fields:
  - DeepSeek / xAI `reasoning_effort`
  - Anthropic / Google(Gemini) thinking controls
  - OpenAI-like `extra_body` support hints
- Add `default_params` JSON extension area.
- Add `config` JSON extension area.
- Preserve unknown keys by splitting known keys from remainder JSON during load and merging on save.
- Extend Test Connection payload to send `default_params` in addition to `config`.
- Validate JSON extension text as object-only and prevent collisions with dedicated managed keys.

**Validation**:
- Save/edit model with unknown keys and verify they survive.
- Validate invalid JSON / conflicting reserved keys.
- Verify Test Connection sends merged params.

### Stage 5: Regression and Quality Checks
**Files modified**:
- Relevant backend/frontend tests
- Implementation plan index updates

**Specific logic**:
- Add targeted adapter and endpoint tests.
- Run frontend i18n generation/lint and standard checks.
- Run backend static checks for touched backend files.

**Validation**:
- Backend: `ruff check`, `ruff format --check`, `mypy app/`
- Frontend: `node scripts/gen-i18n-types.ts`, `node scripts/lint-translations.ts --strict`, `bun run lint`, `bun run build`

## Testing Strategy

### Happy Path
- Create DeepSeek model with `reasoning_effort=high` and `extra_body`.
- Create Anthropic/Gemini model with thinking params.
- Re-open saved model and verify unknown params remain.
- Test Connection should use the same runtime defaults.

### Error Path
- Invalid JSON in extension area.
- Non-object JSON in extension area.
- Reserved key conflict between dedicated UI and JSON extension.
- Anthropic `thinking` plus `output_config` incompatibility.

### Regression Scope
- Existing fixed fields continue to save correctly.
- Existing `config.thinking` historical data still reads correctly.
- Azure/OpenAI-compatible path remains functional.

## Risks & Mitigation

**Risk**: Generic passthrough could inject invalid request fields.
**Mitigation**: Filter reserved keys, validate object shape, and limit blind passthrough to adapters with flat payloads.

**Risk**: Editing existing models may still drop unknown keys.
**Mitigation**: Preserve original objects and merge remainder JSON explicitly.

**Risk**: Gemini request nesting is easy to break.
**Mitigation**: Keep Gemini on explicit mapping only.
