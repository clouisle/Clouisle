# Retrieval Failure Handling Design Document

## Background & Goals

Knowledge-base searches can currently fail before the first lexical indexing operation because the OpenSearch aliases do not exist. Aggregate retrieval failures also hide useful channel classification in server logs, while clients receive a vector-specific message containing an unresolved `{error}` placeholder.

Success means:

- A first lexical search initializes the existing versioned index and aliases and can return no hits normally.
- Retrieval diagnostics expose stable exception classifications, not raw provider or infrastructure responses.
- The search endpoint logs sanitized target diagnostics and preserves dimension-mismatch mapping.
- Clients receive generic localized retrieval-failure copy without interpolation artifacts.

## High-Level Design

`LexicalStore.search()` reuses the idempotent `ensure_index()` path before querying the read alias. The unified retrieval service converts caught failures to safe exception-class details; hybrid failures continue to report channel plus exception class. The knowledge-base endpoint logs these structured diagnostics and maps only dimension mismatches to the validation error, while all other failures use a generic `BusinessError`. Existing English, Chinese, and legacy translations remain synchronized.

## Implementation Plan

### Stage 1: Lexical initialization

- **Files modified**: `backend/app/services/lexical_store.py`, `backend/tests/services/test_lexical_store.py`
- **Specific logic**: Call `ensure_index()` before lexical search and cover missing-index, missing-alias, idempotent, and empty-result behavior with the existing OpenSearch stub.
- **Validation**: Run the lexical store test module and verify the expected request sequence.

### Stage 2: Safe diagnostics and endpoint mapping

- **Files modified**: `backend/app/services/retrieval.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/tests/services/test_retrieval.py`, `backend/tests/api/test_knowledge_base_boundaries_issue255.py`
- **Specific logic**: Store exception class names instead of raw exception strings, log target diagnostics as structured sanitized values, use retrieval-neutral logging, and retain direct/wrapped dimension mismatch handling.
- **Validation**: Exercise provider failure, hybrid dual failure, wrapped dimension mismatch, and generic error mapping; assert raw exception messages do not reach API diagnostics or client copy.

### Stage 3: Preserve dual-channel classifications

- **Files modified**: `backend/app/services/retrieval.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/tests/services/test_retrieval.py`, `backend/tests/api/test_knowledge_base_boundaries_issue255.py`
- **Specific logic**: Carry the already-sanitized dense and lexical exception class names through an internal dual-channel exception and serialize them deterministically. Recognize an exact `DimensionMismatchError` class token in this controlled representation.
- **Validation**: Assert both channel classifications survive, raw exception messages remain absent, endpoint logs retain the controlled detail, and nested dimension mismatches still map to validation errors.

### Stage 4: Localized client failure copy

- **Files modified**: `backend/app/locales/en/LC_MESSAGES/messages.po`, `backend/app/locales/zh/LC_MESSAGES/messages.po`, `backend/app/core/i18n_legacy.py`
- **Specific logic**: Keep the existing key but replace vector-specific interpolated text with a generic retrieval failure in both languages.
- **Validation**: Assert localized output contains neither `{error}` nor provider details.

### Stage 5: Operational verification

- **Files modified**: `backend/app/core/config.py`, local environment configuration, `docs/IMPLEMENTATION_PLAN.md`
- **Specific logic**: Support the self-signed TLS certificate used by the built-in OpenSearch service through an explicit SSL verification setting, configure local development to use HTTPS and existing basic authentication, then retry hybrid retrieval.
- **Validation**: Focused tests and Ruff checks pass; live lexical search initializes the aliases; reconciliation identified 184 completed PostgreSQL chunks missing from OpenSearch, the existing backfill path indexed all 184, and a scoped lexical search returned hits. Fulltext retrieval returned five results with no retrieval diagnostics. Existing dirty frontend files remain unchanged.

### Stage 6: Actionable client guidance

- **Files modified**: `backend/app/api/v1/endpoints/knowledge_bases.py`, `frontend/components/knowledge-bases/retrieval-lab.tsx`, `frontend/lib/api/knowledge-bases.ts`, English/Chinese frontend translations, and focused endpoint/component tests.
- **Specific logic**: Convert only exact, sanitized exception-class tokens into a small public `retrieval_error_category` allowlist carried in `BusinessError.data`. Preserve direct and wrapped dimension-mismatch validation, classify unknown or mixed failures generically, and never return raw diagnostics. Preserve each A/B rejection as a controlled per-side frontend failure and render localized corrective guidance while retaining successful comparison results. True no-response failures remain connectivity errors.
- **Validation**: Focused backend tests passed (71 tests), focused Retrieval Lab/client tests passed (17 tests), backend Ruff check/format passed, targeted frontend ESLint passed, and frontend i18n generation/strict translation lint passed. Coverage includes network, configuration, authentication, quota, model, lexical, provider, mixed, and unknown failures; independent A/B guidance, successful retry cleanup, and non-leakage assertions are covered. The repository-wide TypeScript command remains blocked by 1,743 existing test typing errors (including missing `bun:test` declarations); no production-file diagnostic was reported for `retrieval-lab.tsx` or `knowledge-bases.ts`.

### Stage 7: Search response serialization repair

- **Files modified**: `backend/app/services/retrieval.py`, `backend/tests/services/test_retrieval.py`, `backend/tests/api/test_knowledge_base_boundaries_issue255.py`, `frontend/lib/api/client.issue255.test.ts`
- **Specific logic**: Normalize the lexical index source field `name` to the API-required `document_name` at the retrieval boundary. This keeps the established OpenSearch schema intact while preventing FastAPI `ResponseValidationError` failures after successful fulltext retrieval. Lock the client boundary down so a non-envelope HTTP 500 retains code 500 rather than being classified as the no-response code `-1`.
- **Validation**: The focused backend suite passed 59 tests and targeted Ruff check/format passed. The API client suite passed 4 tests and Retrieval Lab suite passed 13 tests independently. The regression tests validate lexical normalization, the declared `Response[SearchResponse]` model, timeout/no-response classification, and HTTP 500 classification. Live retrieval returned five fulltext results and five hybrid results with zero diagnostics; every result included a valid `document_name`.

### Stage 8: Remove rerank fail-open and add stage-aware errors

- **Files modified**: 
  - Backend: `backend/app/services/vector_store.py`, `backend/app/services/retrieval.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/app/schemas/knowledge_base.py`
  - Frontend: `frontend/components/knowledge-bases/retrieval-lab.tsx`, `frontend/lib/api/knowledge-bases.ts`, `frontend/i18n/en/knowledgeBases.json`, `frontend/i18n/zh/knowledgeBases.json`
  - Tests: `backend/tests/services/test_retrieval.py`, `backend/tests/api/test_knowledge_base_boundaries_issue255.py`, `frontend/components/knowledge-bases/retrieval-lab.test.tsx`, `frontend/lib/api/client.issue255.test.ts`

- **Specific logic**:
  
  **Backend changes:**
  1. Remove `fail_open` parameter from `VectorStore._rerank_results()` — always propagate rerank exceptions
  2. Remove `rerank_fail_open` from stored KB settings resolution in `_resolve_rerank_config()`
  3. Remove `rerank_fail_open` from request overrides processing
  4. Wrap rerank calls in `_retrieve_once()` to catch exceptions and convert them to stage-aware `RetrievalError`
  5. Add `stage` field to `RetrievalDiagnostic` with controlled taxonomy: `dense_recall`, `lexical_recall`, `fusion`, `rerank`, `context`, `unknown`
  6. Map rerank LLM exceptions to existing safe categories with explicit `stage="rerank"`
  7. Preserve recall-stage exception mapping with `stage="dense_recall"` or `stage="lexical_recall"`
  8. Update endpoint to serialize `stage` alongside `retrieval_error_category`
  9. Remove `rerank_fail_open` from `SearchRequest` schema
  
  **Frontend changes:**
  1. Remove `rerank_fail_open` from `Config` type and `DEFAULT_CONFIG`
  2. Remove `rerank_fail_open` from `SearchParams` interface
  3. Remove `rerank_fail_open` from request body construction
  4. Remove inline error rendering from the results area
  5. Remove `{ silent: true }` from Retrieval Lab search requests
  6. Add stage-specific toast messages using `retrieval_error_category` + `stage` from backend response
  7. Add A/B-aware toast labels when comparison mode is enabled
  8. Add translations for stage-specific error messages covering all stage/category combinations
  9. Regenerate i18n types after adding translations

- **Validation**:
  
  **Backend tests:**
  - Rerank provider 403/authentication failure now propagates as `RetrievalError` with `stage="rerank"` and `category="provider_authentication"`
  - Rerank timeout propagates with correct stage
  - Successful recall followed by rerank failure produces no results (not degraded recall results)
  - Stage field is correctly set for dense recall, lexical recall, and fusion failures
  - Raw provider responses never leak in `RetrievalDiagnostic`
  - Dimension mismatch retains validation error mapping
  - Endpoint response includes both `retrieval_error_category` and `stage`
  
  **Frontend tests:**
  - No error UI appears in hit/result area
  - Toast notifications display on failure with localized, stage-specific messages
  - A/B comparison failures show side-specific toasts (e.g., "Configuration A: Reranking failed...")
  - Successful side remains visible when other side fails
  - Unknown/raw exception text never appears in UI
  - Network failures remain distinct from backend retrieval failures
  - Retry clears previous failure state
  
  **Integration:**
  - Run focused backend retrieval + endpoint tests
  - Run focused frontend Retrieval Lab + client tests
  - Backend Ruff check/format
  - Frontend ESLint on touched files
  - Frontend i18n generation + strict lint
  - Live test: trigger rerank 403 and verify stage-specific toast appears instead of silent success

## Testing Strategy

- **Happy path**: First lexical query creates index/aliases and returns an empty hit list; hybrid retrieval can return an empty successful response when one channel is healthy.
- **Error path**: Provider and OpenSearch failures produce stable exception class diagnostics; both hybrid channels failing produces an aggregate error; direct and wrapped dimension mismatches retain the validation response. Rerank failures now produce stage-aware retrieval errors rather than silently returning recall results.
- **Regression scope**: Existing lexical indexing/cutover behavior, unified vector/fulltext/hybrid retrieval, knowledge-base search endpoint mapping, English/Chinese error rendering, and A/B comparison independence.

## Risks & Mitigation

- Calling `ensure_index()` per lexical query adds OpenSearch metadata requests. This is accepted for correctness until a measured startup or caching optimization is justified.
- Sanitizing diagnostic details reduces raw troubleshooting text in API responses. Server exception logs and stable classifications retain actionable context without leaking URLs, credentials, or provider bodies.
- No empty-KB database short circuit is added because counters can be stale and a short circuit could hide index corruption.
- Removing fail-open means rerank failures will now fail the entire search. This is the explicitly requested behavior: users want to know when reranking fails rather than silently receiving unranked results. The trade-off is accepted for operational visibility.
- Stage-aware errors increase the response contract surface. The stage taxonomy is kept minimal and controlled; new stages require explicit backend/frontend coordination.
- Rollback is localized: restore fail-open parameter, remove stage field, restore inline error rendering, and restore silent requests independently if needed.
