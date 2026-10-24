# Backend Push Gate Repair Design Document

## Background & Goals
The branch's pre-push hook reported 13 backend failures. Preserve current multimodal authorization and required migration semantics, repair genuine serialization regressions, and pass existing backend/frontend test and coverage gates without exclusions or bypasses.

## High-Level Design
Keep production changes limited to Gemini optional media metadata compatibility and shared tool-result serialization. Update obsolete fixtures to canonical model modalities and awaitable ORM contracts. Reject missing media instead of silently sending a text-only request. Cover multimodal selection, resource transport, runtime transitions, and schema boundaries with deterministic tests.

## Implementation Plan
### Stage 1: Existing regression repair
- **Files modified**: Gemini adapter, AgentLoop, Agent/chat tool tests, Asset tests, WeChat model fixtures, initialization tests.
- **Specific logic**: Preserve optional metadata fallback and malformed-media rejection; restore get_tool_execution_payloads to prevent double JSON encoding; mock required migrations at the test boundary.
- **Validation**: Full backend pytest; invalid image input still raises InvalidRequestError.

### Stage 2: Coverage gate repair
- **Files modified**: Focused backend multimodal, Feishu runtime/input/resource, model validation, and chat-context tests; frontend delivery API/route tests.
- **Specific logic**: Exercise authorization failures, upload size/MIME limits, media selection ranges, cancellation, delivery states, repeated query filters, and encoded search parameters. Keep thresholds unchanged.
- **Validation**: Backend line and branch coverage >=95%; frontend line/function coverage >=95% and every eligible source represented in LCOV.

### Stage 3: Commit and delivery
- **Files modified**: None beyond verified repairs.
- **Specific logic**: Commit fixes and push the existing feature branch with hooks enabled.
- **Validation**: Successful git push output including remote ref update.

## Testing Strategy
- Happy path: native media serialization, extracted document context, valid channel delivery, migration bootstrap fixtures, delivery query serialization.
- Error paths: missing media, unauthorized resources, provider errors/redirects, oversized inputs, invalid modality limits, interrupted or revoked delivery.
- Regression: complete backend suite and frontend coverage command; final pre-push hook.

## Risks & Mitigation
- New tests must remain isolated from real credentials and external services; use existing SQLite/transport fixtures.
- Never suppress InvalidRequestError or weaken coverage to make old tests pass.
- Rollback: revert the repair commit; no database schema or persisted data is changed by this repair.

## Verification Status
- Frontend: 2921 passed; functions 95.61%, lines 97.91%; all 524 eligible source files included.
- Backend: 9260 passed, 4 skipped; line coverage 96.73%, branch coverage 95.13%; unchanged 95% gates passed.
- Remote push: pending final hook success.
