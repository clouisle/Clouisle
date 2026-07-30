# Retrieval Query Embedding Reuse Design Document

## Background & Goals

Agent multi-knowledge-base retrieval currently embeds the same query once per dense target, even when the targets share a team and embedding model. Retrieval Lab A/B comparison sends two HTTP requests and repeats the same work.

Success criteria:

- Reuse one in-flight query embedding for the same exact query, team, and embedding model within one logical retrieval invocation.
- Cover multi-target Agent retrieval, primary/shadow passes, and Retrieval Lab A/B comparison.
- Preserve independent target/variant scopes, recall, fusion, thresholds, truncation, reranking, diagnostics, timings, failures, and context assembly.
- Keep existing single-search callers backward compatible.

## High-Level Design

The retrieval service owns an invocation-local singleflight map keyed by `(query, team_id, embedding_model_id)`. It stores `asyncio.Task` objects so concurrent consumers share in-flight work and await it through `asyncio.shield`. It is not a cross-request or distributed cache.

`VectorStore.search()` accepts an optional precomputed query embedding. Dimension validation and knowledge-base/document filters remain target-specific.

Retrieval Lab comparison uses one `POST /{kb_id}/search/batch` request containing identified configurations. Every configuration runs as an independent retrieval variant and returns a fulfilled or sanitized rejected outcome. Only query embeddings are shared; candidate lists and reranking are never shared across variants.

## Implementation Plan

### Stage 1: Precomputed vector seam

- **Files modified**: `backend/app/services/vector_store.py`, vector-store tests
- **Specific logic**: Add an optional precomputed embedding to vector search, skip provider embedding when supplied, and retain dimension validation.
- **Validation**: Test provider call counts, Qdrant invocation, mismatch failure, and full-text bypass.

### Stage 2: Request-scoped singleflight

- **Files modified**: `backend/app/services/retrieval.py`, retrieval and rollout tests
- **Specific logic**: Share embedding tasks across matching dense targets and primary/shadow passes. Shield shared tasks from consumer cancellation.
- **Validation**: Test same/different team-model keys, skipped targets, shared failure diagnostics, dimension isolation, and unchanged global rerank.

### Stage 3: Batch service and endpoint

- **Files modified**: `backend/app/schemas/knowledge_base.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/app/services/retrieval.py`, API tests
- **Specific logic**: Add bounded identified configurations, per-variant outcomes, one access check, and independent retrieval execution with shared embedding context.
- **Validation**: Test partial success, input order, duplicate IDs, explicit rerank overrides, sanitized errors, and one embedding with independent reranks.

### Stage 4: Retrieval Lab adoption

- **Files modified**: `frontend/lib/api/knowledge-bases.ts`, `frontend/components/knowledge-bases/retrieval-lab/shared.tsx`, `frontend/components/knowledge-bases/retrieval-lab/index.tsx`, related tests
- **Specific logic**: Keep single mode on `/search`; send A/B through one batch request and map outcomes to existing side-aware state and toasts.
- **Validation**: Test one batch call, no comparison-time single calls, partial success, retries, overlap, and rank movement.

### Stage 5: Documentation and full verification

- **Files modified**: `docs/dev/design/ai-data/KNOWLEDGE_BASE_SPEC.md`, `docs/plan/yun-117-knowledge-retrieval-lab.md`, this document, `docs/IMPLEMENTATION_PLAN.md`
- **Specific logic**: Record cache identity/lifetime, batch semantics, and rerank boundaries.
- **Validation**: Run focused backend/frontend tests, lint, formatting, typing, build, and manual A/B verification.

## Testing Strategy

- Happy path: shared-model multi-KB Agent retrieval embeds once; A/B embeds once and returns independent results.
- Error path: different tenant/model never shares; dimension errors remain local; shared provider failures are sanitized; one failed variant does not cancel another.
- Regression scope: direct search, Agent AUTO/Agentic RAG, workflow retrieval, rollout/shadow, global rerank, and Retrieval Lab single/A/B modes.

## Risks & Mitigation

- Concurrent duplicate work: cache in-flight tasks rather than completed values.
- Cancellation propagation: await shared tasks with `asyncio.shield`.
- Tenant leakage: include team and model UUID in the key and keep the map invocation-local.
- A/B semantic drift: share only embeddings, never recall or rerank candidates.
- Error leakage: reuse controlled category/stage mapping and omit raw provider details.

Rollback requires only code reversion: `/search` remains intact, precomputed embeddings are optional, and no persistent state or migration is introduced.
