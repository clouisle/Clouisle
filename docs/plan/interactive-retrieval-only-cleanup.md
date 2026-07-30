# Retrieval Lab Interactive-Only Cleanup Design Document

> **Historical note:** OpenSearch references in this completed cleanup plan describe the lexical retrieval architecture in use at that time. Current lexical retrieval uses PostgreSQL with pg_search; the references below remain unchanged to preserve the cleanup record.

## Background & Goals

The Retrieval Lab currently combines immediate single-knowledge-base search with persistent datasets, relevance labeling, batch runs, run comparison, and parameter sweeps. The persistent evaluator always builds one retrieval target, while production Agent retrieval operates on a target set and performs cross-KB merging, truncation, reranking, diagnostics, and context assembly. The current batch results therefore cannot validate production behavior. Comparison and sweep code also reads metric shapes that the executor does not persist.

This change keeps only the useful interactive surface and removes the misleading evaluation stack and its residue.

Success criteria:

- The Retrieval Lab performs one direct search, or two direct searches in immediate A/B mode.
- Vector, full-text, hybrid, rerank, stage scores/ranks, diagnostics, timings, presets, and result inspection remain available.
- Dataset, labeling, batch run, comparison, sweep, and evaluation-report UI no longer exists.
- Evaluation APIs, models, services, tasks, translations, tests, and database tables are removed.
- Production Chat, Agent, Tool, Workflow, and direct knowledge-base retrieval remain unchanged.

## High-Level Design

The frontend continues to call the existing user/admin knowledge-base `search` endpoints. Those endpoints continue to use the shared production retrieval service. No replacement evaluation abstraction is introduced.

Removal proceeds from the product surface inward:

1. Collapse Retrieval Lab to direct interactive search/A-B.
2. Remove unused frontend API and i18n contracts.
3. Remove backend evaluation routes/runtime and worker wiring.
4. Remove Tortoise models and safely drop legacy evaluation tables.
5. Verify no source, OpenAPI, worker, model, translation, test, or documentation residue remains.

## Implementation Plan

### Stage 1: Frontend Interactive Boundary

- **Files modified**: `frontend/components/knowledge-bases/retrieval-lab/index.tsx`, `shared.tsx`, feature-only components and tests.
- **Specific logic**: remove dataset loading, query-scoped labels, candidate-pool searches, quality panels, batch/sweep modes, persistent run comparison, and reports. Preserve direct A/B request isolation and existing result rendering.
- **Validation**: a normal query sends one request; A/B sends two; no hidden pooling request occurs; either side may fail independently.

### Stage 2: Frontend Contracts and i18n

- **Files modified**: `frontend/lib/api/knowledge-bases.ts`, `frontend/lib/api/index.ts`, API tests, EN/ZH knowledge-base messages, generated i18n type.
- **Specific logic**: delete all Evaluation Dataset/Case/Run/Comparison/Sweep types and methods. Retain Search types, diagnostics, timings, and user/admin direct search methods. Remove only dead translation keys and regenerate types.
- **Validation**: focused API tests, strict translation lint, frontend lint and build.

### Stage 3: Backend Runtime Removal

- **Files modified**: evaluation endpoint/router registration, models/schemas/exports, evaluation-only services/tasks, Celery registration, tests, and backend messages.
- **Specific logic**: remove all dataset/case/import/export/suggestion/run/compare/sweep routes and code. Preserve `app/services/retrieval.py`, knowledge-base search schemas/endpoints, KB retrieval settings, and all production callers.
- **Validation**: OpenAPI and Celery contain no evaluation entries; direct search and multi-KB production retrieval tests pass.

### Stage 4: Legacy Schema Removal

- **Files modified**: `backend/app/core/init_data.py`, startup wiring, schema cleanup tests.
- **Specific logic**: stop creating evaluation tables. During a compatibility release, run a narrowly scoped idempotent cleanup before schema generation. Remove cross-links between runs and sweeps first, then drop `evaluation_case_results`, `evaluation_sweeps`, `evaluation_runs`, `evaluation_cases`, and `evaluation_datasets`. Do not use broad `CASCADE` and do not touch unrelated tables.
- **Validation**: cleanup succeeds against complete, partial, and already-clean schemas and never recreates evaluation tables.

### Stage 5: Documentation and Residual Cleanup

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/yun-117-knowledge-retrieval-lab.md`, API/design/operator documentation that mentions removed functionality. Delete obsolete tuning/evaluation plans and status reports.
- **Specific logic**: describe Retrieval Lab only as an interactive search/A-B inspection tool. Remove claims and validation results for persistent evaluation and offline learned-sparse gates.
- **Validation**: residual scans find retired symbols only in the temporary schema cleanup compatibility code and this migration record.

## Testing Strategy

Happy paths:

- User and admin Retrieval Lab routes execute Vector, Fulltext, Hybrid, reranked, and A/B searches.
- Direct search parameters and stage-aware results remain unchanged.
- Production multi-KB retrieval retains global merge/rerank/context behavior.

Error paths:

- One A/B side may fail without hiding the other side.
- Empty results and per-stage diagnostics remain localized.
- Legacy schema cleanup handles missing tables and historical cross-FKs idempotently.

Regression scope:

- Knowledge-base direct search endpoints and permissions.
- Chat AUTO RAG, Agentic knowledge search, Agent service retrieval, and Workflow knowledge nodes.
- Retrieval rollout, observability, OpenSearch/Qdrant fallback, and rerank behavior.

## Data Removal and Deployment

This cleanup permanently deletes evaluation datasets, labels, run history, case results, and sweep recommendations. Back up data before deployment if retention is required. Stop and drain old evaluation workers before dropping tables. A rollback requires both a pre-cleanup database snapshot and the prior application/worker image; reverting code alone cannot restore data.

## Risks & Mitigation

- **Uncommitted work loss**: use surgical edits only; do not reset, restore, or broadly revert the working tree.
- **Old workers writing removed tables**: remove ingress and drain workers before schema cleanup.
- **Foreign-key cycles**: remove known run/sweep cross-FKs before ordered table drops.
- **Production retrieval regression**: treat the shared retrieval service, direct search endpoint/schema, and production caller paths as a hard preservation boundary.
- **Confusing candidate terminology**: remove only the authoring candidate-pool feature; retain normal `rerank_candidate_k` behavior.
- **Hidden residue**: scan source, routes, task registry, Tortoise models, database catalog, i18n, tests, and docs rather than checking only the UI.

## Rollback Plan

- Before database cleanup: deploy the previous code revision.
- After database cleanup: stop new services, restore the database snapshot, then deploy the matching previous API and worker images.
- OpenSearch and Qdrant indexes are not modified by this change.
