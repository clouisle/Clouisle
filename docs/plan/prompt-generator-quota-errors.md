# Prompt Generator Quota Errors Design Document

## Background & Goals
- Reported provider HTTP 402: `Insufficient token quota`. This is a provider billing/quota failure, not template formatting.
- Generation and optimization select the enabled global default chat model. Both currently replace provider failures with unknown-error SSE payloads; the dialog then replaces even those messages with generic generation failure.
- Success: explicit provider 402 or an existing typed insufficient-quota error returns the existing model-quota business code/message, visible in the dialog. Unknown errors remain sanitized. No retries, model switching or quota bypass.

## High-Level Design
- A local shared payload helper serves both prompt SSE endpoints: map explicit HTTP 402 and typed `InsufficientQuotaError` to `MODEL_QUOTA_EXCEEDED`; retain the generic fallback for other errors.
- The dialog displays backend SSE error messages directly and exits generation through the existing finally block. Raw provider error text is never returned by the backend.

## Implementation Plan

### Stage 1: Preserve safe error semantics
- **Files modified**: `backend/app/api/v1/endpoints/prompt_generator.py`, `frontend/components/ai-elements/prompt-generate-dialog.tsx`.
- **Specific logic**: Add local error-payload mapping and reuse at generate/optimize catches. Display safe SSE message in the dialog without converting it back to a generic exception.
- **Validation**: Use actual SDK HTTP 402 exceptions without contacting the provider; confirm generic errors remain sanitized.

### Stage 2: Verify and document
- **Files modified**: existing generator/dialog tests, `docs/guide/api-reference/endpoints/prompts.md`, `docs/IMPLEMENTATION_PLAN.md`, this plan.
- **Specific logic**: Cover quota errors on both endpoints and visible dialog reporting; remove obsolete generic-wording assertions. Document global default model selection and quota recovery.
- **Validation**: Focused backend/frontend suites, lint/format checks, offline in-process ASGI smoke including successful streaming and quota failure. No service/browser start or live provider retry.

## Testing Strategy
- Happy path: unchanged content streaming/completion.
- Error paths: HTTP 402 maps to quota; typed quota maps identically; other provider errors do not leak details; no completion event on failure; dialog restores controls and shows safe SSE message.
- Regression scope: prompt generation and optimization endpoints, dialog generation/copy/retry behavior.

## Risks & Mitigation
- Correct error reporting cannot restore supplier quota. Operator must fund/configure the provider account or explicitly choose a different default model.
- Do not classify ordinary rate limiting as quota depletion; generic unknown failures stay unchanged.
- Rollback: revert this isolated change; no migrations or saved prompts are affected.

## Verification Status
- Completed: both prompt endpoints return safe quota code/message for HTTP 402 and typed insufficient-quota failures; the dialog displays safe SSE errors and restores generation controls.
- Backend generator suite: 14 passed (`--no-cov`). Frontend prompt API/dialog suites: 14 passed. Ruff lint/format and targeted ESLint passed.
- Offline ASGI smoke exercised generate and optimize with actual SDK-shaped 402/429 exceptions and successful streaming: 402 returned 6103; ordinary 429 retained generic 1000; failures had no completion event or provider-secret leakage; successes preserved content length and completion. The start event identified the selected configured default model.
- No live provider call, application service or browser was used. The reported provider quota remains an external operational issue; no balance, API key or default model was changed.
