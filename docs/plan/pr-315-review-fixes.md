# PR 315 Review Fixes Design Document

## Background & Goals

PR 315 introduces unified dense/lexical retrieval, rollout controls, a Retrieval Lab, and a PostgreSQL pg_search image. Review found correctness failures across index lifecycle, retrieval semantics, UI request handling, and deployment publication.

Success criteria:
- Deleted or newer chunk content cannot be restored by stale lexical work.
- Retrieval honors effective modes, channel weights, rerank policy, cancellation, and stable diagnostics.
- Knowledge-base mutations do not report failure after committing an unreconciled primary mutation.
- AUTO and agentic retrieval preserve bounded history, metadata, and serializable results.
- Retrieval Lab requests are permission-aware, bounded, race-safe, and visibly report failures.
- PostgreSQL images publish idempotently under validated version tags and deployment manifests pull the published artifact.
- Current documentation matches the shipped PostgreSQL/pg_search and fail-closed retrieval contracts.

## High-Level Design

Keep PostgreSQL authoritative. Lexical writes use document/chunk existence checks plus monotonic update timestamps, and deletion ordering preserves searchable projections until authoritative deletion succeeds. Retrieval resolves and validates one effective configuration per target before rollout and backend dispatch. Frontend requests use stable callbacks and request generations so only the latest invocation can update state. Deployment publication validates its release tag and treats matching architecture tags as reusable inputs to an immutable manifest.

## Implementation Plan

### Stage 1: Lexical lifecycle and API consistency
- **Files modified**: `backend/app/services/lexical_store.py`, `backend/app/tasks/knowledge_base.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, focused tests.
- **Specific logic**: use `updated_at` as lexical version; condition conflict updates on newer payloads; prevent writes for deleted rows; make broker publication retryable; reorder deletion; reconcile chunk create/update failures; map configuration mismatches and validate inherited zero weights.
- **Validation**: stale-write, delete-race, dispatch-failure, partial-delete, duplicate-create, and batch-error tests.

### Stage 2: Retrieval and chat semantics
- **Files modified**: `backend/app/services/retrieval.py`, `backend/app/services/retrieval_rollout.py`, `backend/app/api/v1/endpoints/chat.py`, `chat_rag.py`, `chat_helpers/rag_utils.py`, `chat_tools.py`, focused tests.
- **Specific logic**: validate effective target settings; ignore zero-weight channels; resolve rerank deterministically; honor configured rerank behavior; attribute diagnostics correctly; classify rollout from effective modes; clean up orphan embedding tasks; short-circuit rollout modes; bound contextualization history; preserve metadata and JSON-safe identifiers.
- **Validation**: weighted-channel, multi-KB order, rerank failure, rollout setting failure, cancellation, history budget, metadata, and serialization tests.

### Stage 3: Retrieval Lab and frontend API
- **Files modified**: Retrieval Lab component/wrappers/tests, frontend API barrel/client, localization catalogs/types.
- **Specific logic**: stabilize callbacks; gate the lab by test permission; export batch types; report outer request failures; reject stale loads/searches; clamp imported settings; fall back to category-level error messages.
- **Validation**: frontend type-check plus focused load-loop, concurrent-search, rejected-request, permission, and localization tests.

### Stage 4: Image publication and documentation
- **Files modified**: PostgreSQL image workflow, deployment manifests/defaults, current retrieval specifications and implementation index.
- **Specific logic**: validate release tags against the built image; reuse matching architecture tags after partial publication; publish one immutable manifest; use a registry-qualified deployment image; make SQL examples rerunnable; retire removed evaluation/OpenSearch contracts.
- **Validation**: workflow and shell syntax/static checks, manifest rendering/config inspection, documentation consistency review.

### Stage 5: Dependency refresh and compatibility
- **Files modified**: backend/frontend dependency manifests and lockfiles, Redis/MCP/email/sandbox compatibility paths, frontend primitives and tooling scripts, focused tests.
- **Specific logic**: upgrade current direct and transitive dependencies; adapt changed Redis, MCP, SMTP, React, Radix, and TypeScript APIs; preserve exception tracebacks; make lint and license policies deterministic under the refreshed toolchains.
- **Validation**: warning-strict backend suite, full frontend suite, independent coverage gates, Ruff, mypy, TypeScript, ESLint, i18n checks, and production dependency license audits.

## Testing Strategy

- Happy paths: fulltext/hybrid retrieval, global rerank, AUTO RAG, Retrieval Lab A/B, image release assembly.
- Error paths: stale backfill, concurrent deletion, broker outage, provider/reranker failure, timeout/cancellation, 422/500/network frontend failures, partial image publication.
- Regression scope: existing lexical, retrieval, knowledge-base endpoint, chat RAG/tool, Retrieval Lab/API, i18n, and deployment image tests.

## Risks & Mitigation

- Conditional lexical upserts can suppress legitimate updates if versioning is not monotonic. Use authoritative `updated_at` and test equal/older/newer payloads.
- Cancellation cleanup must not cancel embeddings still shared by live A/B variants. Track invocation lifetime and gather all variants before cleanup.
- Permission gating differs between admin and platform routes. Reuse each route's existing permission hook rather than inventing a shared authorization source.
- Registry values may be environment-specific. Use the same published ACR repository already established by the workflow and expose an override in chart values.
- Rollback: revert the focused stage; PostgreSQL remains authoritative and lexical data can be rebuilt by the existing backfill task.

## Validation Evidence

- Backend full suite: 6,363 tests passed and 3 skipped with `DeprecationWarning`, `RuntimeWarning`, and `PytestWarning` promoted to errors; 97.67% line and 95.00% branch coverage. Ruff, formatting, mypy, i18n checks, and the 186-package license audit passed.
- Frontend full suite: 2,009 tests passed. Production TypeScript (`tsc --noEmit`), repository ESLint, translation lint, and the 770-package production license audit passed; three unused optional Next image packages were intentionally excluded because image optimization is disabled.
- Focused retrieval regressions remain covered across Retrieval Lab, both route wrappers, API client, lexical storage, retrieval, rollout, chat RAG/tools, and knowledge-base lifecycle/schema/task handling.
- Frontend smoke: the changed admin route compiled and loaded through the running Next.js development server without a page exception; authenticated visual state was unavailable in the smoke environment.
- Deployment: workflow YAML and deployment manifests parsed; image script shell syntax passed; development Compose rendered with required secrets supplied. Production Compose correctly failed closed when the required `.env` file was absent.
