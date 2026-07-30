# PR 315 Review Fixes Design Document

## Background & Goals

PR 315 introduces unified dense/lexical retrieval, rollout controls, AUTO-RAG contextualization, a Retrieval Lab, and an Alpine PostgreSQL pg_search image. Follow-up review found unresolved correctness and operability gaps across projection recovery, distributed mutations, global ranking, optional chat behavior, response latency, nested settings updates, UI validation, and deployment publication.

Success criteria:
- PostgreSQL remains authoritative; Qdrant and `knowledge_lexical_chunks` converge through idempotent repair.
- Stale lexical work cannot overwrite newer chunks, and backfill/reconciliation are bounded, resumable, and identity-aware.
- Document/chunk mutations are atomic or explicitly compensated, and broker/projection failures cannot leave misleading lifecycle state.
- Multi-KB channels are fused globally, truncated once, reranked once, and assembled in document order.
- Shadow retrieval and telemetry are fail-open and outside the primary response latency path.
- AUTO-RAG uses bounded contiguous branch history and fails open without weakening explicit retrieval APIs.
- Sparse retrieval-setting updates preserve chunking fields, and the Retrieval Lab blocks invalid hybrid weights responsively and with i18n.
- Active deployment defaults reference one validated amd64/arm64 immutable pg_search image.

## High-Level Design

PostgreSQL is the source of truth. Chunk mutation timestamps guard lexical projection writes; bounded backfill and identity/version reconciliation provide eventual convergence. Celery wrappers reuse the worker event loop, while projection repair is independent from authoritative completion. Lifecycle transitions use ownership-aware dispatch compensation, and manual chunk operations lock authoritative aggregates and compensate Qdrant.

Retrieval retains dense and lexical channel candidates across targets, performs one deterministic global fusion and rerank, then orders selected adjacent context by document position. Shadow retrieval owns an independent background context, and Redis telemetry uses one fail-open pipeline. AUTO chat alone catches retrieval failures and reads bounded branch-aware history. Backend sparse merging and frontend preservation/validation protect settings. Image publication verifies tested architecture digests and both existing and new manifests before deployment adoption.

## Implementation Plan

### Stage 1: Authoritative lexical versions and convergent repair
- **Files modified**: `backend/app/models/knowledge_base.py`, `backend/app/core/init_data.py`, `backend/app/services/lexical_store.py`, `backend/app/tasks/knowledge_base.py`, focused tests.
- **Specific logic**: add and backfill `DocumentChunk.updated_at`; use it as a strictly monotonic guarded projection version; report actual writes; batch large documents; self-chain keyset backfill; reconcile missing, mismatched, and extraneous rows by identity/version within tenant scope.
- **Validation**: fresh/upgrade/rerun schema tests, equal/older/newer writes, delete/update races, replayed checkpoints, continuation failure, equal-count identity mismatch, and cross-tenant isolation.

### Stage 2: Celery repair and lifecycle consistency
- **Files modified**: `backend/app/tasks/knowledge_base.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, Celery guide, focused task/endpoint tests.
- **Specific logic**: reuse the persistent worker event loop; remove `asyncio.run()` and direct decorated-task calls; keep successful dense/document completion when lexical repair fails; lock and compensate process/reprocess/rechunk state when broker publication fails; never delete lexical state before authoritative rows change.
- **Validation**: open/closed/missing loop behavior, stale delivery ownership, lexical outage, repair dispatch outage, and broker compensation without overwriting a newer task.

### Stage 3: Transactional manual chunk mutations
- **Files modified**: knowledge-base endpoints, vector-store compensation seam if required, focused lifecycle tests.
- **Specific logic**: lock document/KB/affected chunk ranges; atomically change rows, indexes, and counters; compensate Qdrant create/update when the other side fails; commit authoritative deletes before idempotent projection cleanup; enqueue lexical repair after successful primary mutations.
- **Validation**: concurrent insertion/update/delete, exact counters/indexes, vector failure before commit, database failure after vector success, failed compensation recovery, and lexical fail-open.

### Stage 4: Global retrieval, context order, and rollout latency
- **Files modified**: `backend/app/services/retrieval.py`, `backend/app/services/retrieval_rollout.py`, focused retrieval/rollout tests.
- **Specific logic**: retain target channel candidates and fuse them once globally with deterministic tenant-safe keys; truncate once and rerank once; preserve stage provenance; sort selected adjacent chunks by document position after relevance-budget selection; run shadow retrieval in an owned background context; pipeline Redis telemetry.
- **Validation**: adversarial multi-KB ordering, target-specific settings, deterministic ties/reranker selection, one candidate cut/rerank, ordered context, cancellation/cleanup, shadow latency isolation, and pipeline failure.

### Stage 5: Bounded fail-open AUTO-RAG
- **Files modified**: `backend/app/api/v1/endpoints/chat_rag.py`, `chat.py`, `backend/app/services/message_branching.py`, focused chat tests.
- **Specific logic**: keep explicit retrieval strict while optional AUTO chat fails open; query a bounded branch-aware eligible history; stop at token/failure boundaries to preserve a contiguous newest suffix; reuse loaded history across the four stream/non-stream new/edit/regenerate paths; preserve metadata/provenance and safe diagnostics.
- **Validation**: all four AUTO failure paths, explicit API failure, failed/noncanonical message exclusion, pagination underfill, branch correctness, token/count bounds, query reuse, and provenance retention.

### Stage 6: Sparse settings and Retrieval Lab UX
- **Files modified**: knowledge-base schema/endpoint, Retrieval Lab component/shared logic, frontend API client, i18n catalogs/types when needed, focused tests.
- **Specific logic**: merge only supplied nested settings and validate the effective model; merge frontend presets over current settings; use nullish API defaults; localize the existing rerank placeholder; cap the settings popover to the viewport; block every invalid hybrid zero/zero search/save/apply path independently for A/B while allowing vector/fulltext.
- **Validation**: omission versus explicit null, preservation of chunk/unknown settings, effective schema validation, localized controls, responsive classes, and all keyboard/button/preset submission paths.

### Stage 7: Verified PostgreSQL image publication and adoption
- **Files modified**: `.github/workflows/postgres-image.yml`, a small testable manifest validator if needed, active Compose/Helm/Kubernetes defaults, and immediate operator docs.
- **Specific logic**: standardize `0.24.3-pg17-alpine1`; verify artifact labels, PostgreSQL major, pg_search version, and architecture; reuse only matching immutable architecture digests; build from validated digests; require existing and new manifests to contain exactly matching `linux/amd64` and `linux/arm64` descriptors.
- **Validation**: malformed/missing/duplicate/extra/digest-mismatch fixtures, valid-existing and partial-retry publication paths, native image tests, and rendered deployment defaults.

### Stage 8: Full validation and evidence
- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, this document, and only behavior-specific retrieval/deployment docs.
- **Specific logic**: run focused checks after each logical segment, then complete backend/frontend/infrastructure gates; record only observed evidence; mark the implementation index complete only after all required checks pass.
- **Validation**: Ruff, format check, mypy, full pytest, i18n generation/lint when applicable, frontend lint/build/tests, image/manifest checks, deployment renders, and `git diff --check`.
- **Observed backend evidence (2026-07-30)**: `uv run ruff check .` passed; `uv run ruff format --check .` reported 913 files formatted; `uv run mypy app/` reported no issues in 315 source files; CI-equivalent `uv run pytest` passed with 6,396 tests passed, 3 skipped, 7 warnings, 97.67% line coverage, and 95.01% branch coverage; the independent `uv run python scripts/check_coverage.py` gate passed both 95% thresholds; `git diff --check` and `git diff --cached --check` passed. Unrelated concurrent repository documentation changes were not included.

## Testing Strategy

- Happy paths: idempotent schema rollout, bounded repair convergence, completed dense indexing with delayed lexical repair, compensated lifecycle dispatch, transactional chunk mutations, global multi-KB retrieval/rerank, detached shadow, bounded AUTO-RAG, sparse settings, Retrieval Lab A/B, and dual-architecture image assembly.
- Error paths: stale/equal projection work, concurrent authoritative deletion, broker outage, Qdrant failure before/after commit, compensation failure, lexical/Redis outage, timeout/cancellation, failed/oversized chat history, invalid hybrid weights, and malformed or mismatched image manifests.
- Regression scope: initialization, lexical, knowledge-base tasks/endpoints, retrieval/rollout, chat RAG/branching, Retrieval Lab/API/i18n, and deployment image/render tests.

## Risks & Mitigation

- Projection repair could cross a tenant boundary. Keep team/KB/document predicates in every scoped scan/write/delete and test adversarial cross-tenant rows.
- External vector operations under locks can increase contention. Lock only the affected aggregate/range and keep explicit compensation local rather than adding a generic distributed-transaction framework.
- Compensation can itself fail. PostgreSQL stays authoritative; retain operation identity and enqueue idempotent repair.
- Global fusion intentionally changes result order. Preserve diagnostic ranks/scores, deterministic ties, rollout controls, and golden multi-KB tests.
- Detached shadow work can leak on cancellation/shutdown. Give it an independent context, owned task registry, observed exceptions, and cancel/gather cleanup.
- A filtered DB limit can underfill rewrite history. Page backward within a hard scan cap while retaining a contiguous branch-correct suffix.
- Sparse setting updates can expose clients that assumed replacement. Test sparse/full payloads and omission/explicit-null separately.
- An immutable image tag may already contain different content. Hard fail and use a new revision; never overwrite or silently accept it.

Rollback:
- Leave the additive chunk timestamp column in place if application code rolls back.
- Disable repair/backfill or shadow rollout first; rebuild projections from PostgreSQL after correction.
- Revert global fusion independently without changing authoritative indexes.
- Disable contextualization to retain original-query AUTO behavior.
- Roll deployment references back atomically to a previously verified PostgreSQL 17 + pg_search multi-architecture tag.

## Validation Evidence

Implementation is in progress. The previous evidence described the pre-remediation PR head and is not accepted as proof for these additional P0–P3 changes. Focused and full results will be recorded here only after they run on the final branch state.
