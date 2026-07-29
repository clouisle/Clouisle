# YUN-117 Knowledge Retrieval Optimization and Interactive Lab Design Document

## Background & Goals

Clouisle originally retrieved knowledge-base chunks through Qdrant dense search, a heuristic `jieba + icontains` lexical path, application-level RRF, and optional reranking. The existing knowledge-base search-test page exposed only one-query parameter testing and did not provide production-faithful diagnostics or immediate configuration comparison.

The current implementation has these confirmed problems:

- `fulltext` is not BM25 and has no inverted-index ranking, corpus IDF, or document-length normalization.
- `score_threshold` is applied to incompatible score types across dense, lexical, RRF, and rerank stages.
- AUTO RAG skips lexical-only knowledge bases without an embedding model.
- Multi-knowledge-base AUTO retrieval is sequential and lacks global ranking and a global context bound.
- Lexical candidates are truncated without deterministic relevance ordering before application scoring.
- Search entry points call `VectorStore` directly and have diverging failure and aggregation behavior.
- The search-test UI formats scores with different semantics as percentages.

### Goals

1. Centralize all knowledge retrieval through one service and one result contract.
2. Replace heuristic lexical matching with production BM25 while retaining Qdrant dense retrieval.
3. Fuse dense and lexical ranks without treating fusion scores as probabilities.
4. Apply reranking globally and assemble bounded, citation-safe context.
5. Upgrade the existing search test into an instant playground and immediate A/B comparator.
6. Roll out through shadow traffic, observable feature flags, and reversible index aliases.

### Success criteria

- Historical quality target (unverified): Recall@20 improves by at least 15% over the then-current hybrid baseline.
- Historical quality target (unverified): nDCG@10 improves by at least 10%.
- Historical quality target (unverified): identifier-heavy Recall@10 is at least 95%.
- Citation provenance maps to the chunks actually supplied to the answer model.
- P95 retrieval latency is below 300 ms without rerank and below 1.5 s with rerank.
- One retriever can fail open in hybrid mode; failure of all requested retrievers is an explicit error.
- Search test, Chat AUTO RAG, Agentic retrieval, Workflow retrieval, and internal Agent retrieval use the same service.

## High-Level Design

PostgreSQL remains authoritative. Qdrant and OpenSearch are disposable, versioned indexes rebuilt from valid PostgreSQL chunks.

```text
query
  -> normalization / optional conversational contextualization
  -> parallel Qdrant dense recall + OpenSearch BM25 recall
  -> authorization and status-scoped candidates
  -> weighted reciprocal-rank fusion by chunk ID
  -> global candidate truncation
  -> optional global reranker
  -> adjacent-chunk expansion and document aggregation
  -> global top K constrained by document, chunk, and token budgets
  -> citations and stage diagnostics
```

### Core responsibilities

- `VectorStore`: Qdrant storage and dense recall only.
- `LexicalStore`: OpenSearch index lifecycle and BM25 recall only.
- `KnowledgeRetrievalService`: scope validation, parallel recall, failure policy, fusion, rerank, global ranking, context expansion, and diagnostics.
- Retrieval Lab: uses the same retrieval service as production paths for immediate single-KB search and A/B inspection; it must not reproduce retrieval logic in the frontend.

### Score contract

Each result preserves stage-specific values:

- `dense_score` and `dense_rank`
- `lexical_score` and `lexical_rank`
- `fusion_score` and `fusion_rank`
- `rerank_score` and `rerank_rank`
- `final_score`, whose stage is explicitly identified

Dense thresholds apply only to dense recall. Lexical retrieval is controlled by rank/candidate count. Fusion scores are never presented as probabilities or filtered by the legacy similarity threshold. A calibrated rerank threshold may filter final results when a reranker is active.

### Initial retrieval parameters

- Dense candidate K: 40
- Lexical candidate K: 40
- Weighted RRF k: 60
- Dense/lexical weights: 1.0/1.0
- Fusion candidate K: 20
- Rerank candidate K: 20
- Final top K: 5
- Rerank fail-open: true
- Dense and rerank thresholds: disabled until model-specific calibration
- Maximum concurrent knowledge bases: 8

These are initial retrieval defaults, not permanent hard-coded product limits.

## Implementation Plan

### Stage 1: Correct Current Retrieval Semantics ✅

- **Completed validation**: strict mode and score-stage contracts, corrected threshold/failure/state semantics, and bounded global AUTO RAG added; 6,255 backend tests passed at 97.82% line/95.09% branch coverage; 1,998 frontend tests passed at 97.77% line/95.04% function coverage; frontend source census and production build passed.
- **Files modified**: `backend/app/schemas/knowledge_base.py`, `backend/app/services/vector_store.py`, current RAG entry points, focused tests, and affected API types.
- **Specific logic**:
  - Validate search mode as a strict enum while accepting the existing API values.
  - Preserve distinct stage scores and ranks.
  - Stop applying the legacy threshold to hybrid RRF scores.
  - Filter active knowledge bases, completed documents, and embedded chunks consistently.
  - Raise a user-visible failure in vector-only mode when embedding fails; allow hybrid to fall back to lexical.
  - Permit lexical-only AUTO RAG without an embedding model.
  - Retrieve multiple knowledge bases concurrently with a bounded semaphore, then rank and truncate globally.
- **Validation**:
  - Invalid modes fail fast.
  - Vector-only failure and hybrid fallback are separately tested.
  - Pending/error documents and chunks never appear.
  - Multiple KBs produce one deterministic global top K.

### Stage 3: Unified Retrieval Service ✅

- **Completed validation**: unified authorization-safe retrieval contracts, bounded concurrency and target timeouts, structured diagnostics and failure isolation, deterministic global ranking/truncation, caller migration, document-scope narrowing, and workflow team scoping added; 6,267 backend tests passed at 97.81% line/95.07% branch coverage; 1,998 frontend tests passed at 97.77% line/95.04% function coverage; frontend 470/470 source census and production build passed.
- **Files modified**: new backend retrieval service/contracts; `chat_rag.py`, `chat_tools.py`, `services/agent.py`, workflow knowledge executor, knowledge-base search endpoint, and tests.
- **Specific logic**:
  - Introduce one retrieval request/response contract.
  - Move orchestration, global ranking, reranking, and diagnostics out of endpoint modules.
  - Retain each caller's presentation layer: citation prompt, tool JSON, workflow output, or search response.
  - Add per-stage timeout and fallback diagnostics without logging full queries or chunk content.
- **Validation**:
  - Equivalent requests through all entry points produce the same ranked chunk IDs.
  - Authorization scope cannot be widened by caller-supplied KB or document IDs.
  - Timeout and dual-retriever failure paths are explicit.

### Stage 4: OpenSearch BM25 Indexing and Weighted Fusion — Historical/Superseded ✅

- **Historical implementation (superseded)**: OpenSearch lexical store, versioned aliases, BM25 search, bulk indexing, scoped deletes, lifecycle dual writes/deletes, resumable backfill/reconciliation, weighted RRF, and deployment support completed. The planned direct cutover to ParadeDB `pg_search` is defined in `docs/plan/postgresql-pg-search-lexical.md`. Backend gates passed with 6,294 tests, 97.71% line coverage, and 95.02% branch coverage. Frontend gates passed with 97.77% line coverage, 95.04% function coverage, 470/470 source census, lint, license check, and production build. Deployment static validation passed for Compose, qdrant cluster Compose, raw Kubernetes YAML/dry-run, pinned Qdrant 1.18.3, and OpenSearch 3.7.0; Helm CLI was unavailable, so Helm lint/template remains unexecuted.
- **Files modified**: backend config, lexical-store service, document processing/rechunk/delete tasks, deployment manifests/Helm values, environment examples, deployment docs, and tests.
- **Specific logic**:
  - Pin verified OpenSearch and Qdrant image versions rather than `latest`.
  - Create a versioned OpenSearch index and stable read/write aliases.
  - Index chunk ID, document/KB/team IDs, status, title, section path, document name, display content, identifiers, language, chunk index, and update version.
  - Use language-aware fields; begin with built-in Chinese analysis and benchmark domain dictionaries before adding plugins.
  - Extract identifiers conservatively for errors, paths, versions, UUIDs, configuration keys, and code-style names.
  - Bulk index new/reprocessed chunks and delete by document/KB scope.
  - Add an idempotent backfill command/task, count validation, incremental dual writes, and alias cutover.
  - Fuse dense and lexical ranks with weighted RRF in the retrieval service.
- **Validation**:
  - Index creation is idempotent.
  - Create, update, rechunk, failed indexing, document delete, and KB delete paths are covered.
  - Chinese, English, and exact-identifier examples retrieve expected chunks.
  - OpenSearch outage degrades hybrid to dense; Qdrant outage degrades hybrid to lexical.
  - Alias rollback restores the prior index without database mutation.

### Stage 5: Global Rerank and Bounded Context Assembly ✅

- **Completed validation**: one cross-KB rerank pass, fail-open/fail-closed and rerank-threshold behavior, authorization-safe adjacent expansion, document aggregation with chunk-level provenance, and document/chunk/token budgets completed. Backend gates passed with 6,305 tests, 97.71% line coverage, and 95.02% branch coverage. Frontend gates passed with 1,998 tests, 97.77% line coverage, 95.04% function coverage, 470/470 source census, lint, license check, and production build.
- **Files modified**: retrieval service and focused service tests.
- **Specific logic**:
  - Rerank the global fused candidate set once rather than reranking independently per KB.
  - Optionally expand one adjacent chunk on each side after ranking; adjacent chunks do not acquire artificial ranking scores.
  - Aggregate by document while retaining chunk-level citation provenance.
  - Enforce final top K, maximum documents, maximum chunks per document, and context token budget.
- **Validation**:
  - Rerank failure respects fail-open/fail-closed configuration.
  - Expansion does not cross unauthorized documents and does not exceed token budget.
  - Citations map to the content actually supplied to the answer model.

### Stage 6: Instant Retrieval Playground and A/B Comparison ✅

- **Completed validation**: shared production-faithful Retrieval Lab, route-specific `kb:test` permissions, raw stage scores/ranks, backend timings and diagnostics, independently attributable A/B calls, local relevance grades and named presets, and confirmed authorized production apply completed. Backend gates passed with 6,311 tests, 97.72% line coverage, and 95.02% branch coverage. Frontend gates passed with 2,001 tests, 97.80% line coverage, 95.14% function coverage, 470/470 source census, lint, translation and license checks, and production build.
- **Files modified**: existing platform/dashboard search-test clients, shared frontend API types, backend diagnostic response, English/Chinese translations and generated i18n types, and tests.
- **Specific logic**:
  - Rename/reframe the existing search test as Retrieval Lab without creating a separate search implementation.
  - Default UI exposes mode, final top K, and rerank toggle; advanced settings expose candidate/fusion/rerank parameters with precise labels.
  - Display stage scores as raw values and ranks, not universal percentages.
  - Show retriever channel, rank changes, keyword highlights, stage latency, and fallback reason.
  - Compare two configurations side by side and compute result overlap/rank movement. Comparison uses one batch envelope with independent per-side outcomes and shares only the invocation-local query embedding when team/model/query identity matches.
  - Allow relevant/partially relevant/not relevant annotations and named configuration presets.
  - Applying a preset to production requires confirmation and `kb:update` authorization.
- **Validation**:
  - Search, empty, error, degraded, reranked, and no-reranker states.
  - A/B results remain independently attributable to each configuration.
  - Chinese IME Enter behavior and authenticated markdown media remain intact.
  - Frontend lint, build, and focused component/API tests pass.

### Stage 8: Query Contextualization Experiment ✅

- **Completed validation**: default-off query contextualization is limited to short referential AUTO RAG queries and uses the six most recent user/assistant messages from the active branch. It reuses the agent's authorized chat model with a two-second timeout, accepts only a structured rewrite grounded by an exact history substring, uses the result for retrieval only, and falls back without exposing query or exception content. Non-stream, stream, edit, and regenerate paths preserve the original answer question; Agentic tool queries remain unchanged. Backend gates passed with 6,357 tests, 97.70% line coverage, and 95.03% branch coverage. Frontend gates passed with 2,008 tests, 97.81% line coverage, 95.15% function coverage, 471/471 source census, lint, license check, and production build.
- **Files modified**: retrieval request preparation, optional model prompt/config, diagnostics, and tests.
- **Specific logic**:
  - Trigger only for AUTO RAG queries that are short, referential, or depend on previous entities.
  - Use the rewritten standalone query only for retrieval; preserve the original question for answering.
  - Fall back to the original query on timeout/error and forbid unsupported factual additions.
  - Do not add a second rewrite to Agentic tool queries by default.
- **Validation**:
  - Referential multi-turn cases improve without regressing standalone queries.
  - Failures have no effect on answer availability.

### Stage 10: Rollout, Observability, and Documentation ✅

- **Files modified**: retrieval environment config, private `SiteSetting` defaults, the shared retrieval entry point, a retrieval-specific Redis collector, deployment examples/manifests, operator docs, and focused tests.
- **Specific logic**:
  - `RETRIEVAL_HYBRID_KILL_SWITCH=true` has highest precedence and immediately forces vector-only retrieval. Mutable private settings then select `enabled`, `disabled`, or `rollout`; explicit team inclusion precedes deterministic SHA-256 percentage assignment.
  - Shadow execution runs only for rollout-excluded hybrid requests, never replaces or mutates the primary vector answer, and retains a bounded Redis list containing only chunk IDs, ranks, retrieval/index versions, and latency.
  - Fail-open Redis metrics use the existing seven-day retention and latency histogram buckets for candidates, recall/rerank/context/total latency, fallbacks, empty results, diagnostics/errors, and lexical index version signals.
  - Roll out internal -> 5% -> 25% -> 50% -> 100%. Advance only when interactive and shadow observations show no cohort regression, retrieval error/fallback rates do not regress, and P95 total latency remains within the approved service objective.
- **Rollback**:
  - Set `RETRIEVAL_HYBRID_KILL_SWITCH=true` for immediate environment rollback, or set private `retrieval_hybrid_mode=disabled` for mutable rollback. Disable `RETRIEVAL_SHADOW_ENABLED` independently.
  - For lexical index rollback, call the existing atomic `LexicalStore.cutover(previous_version)`; retained versioned indexes let both read and write aliases move back together.
- **Validation**:
  - Focused tests cover deterministic assignment and precedence, setting-store failure, privacy-safe bounded telemetry, metric failure isolation, vector-primary shadow isolation, and shadow failure isolation.
  - OpenSearch alias cutover/rollback remains covered by the existing atomic alias tests. Backend gates passed with 6,371 tests, 97.70% line coverage, and 95.03% branch coverage. Frontend gates passed with 2,008 tests, 97.81% line coverage, 95.15% function coverage, 471/471 source census, lint, license check, and production build. Compose validation requires a local `deploy/.env`; Helm and `kubectl` rendering were skipped because those CLIs are not installed in this environment.

## Testing Strategy

### Happy path

- Dense-only, lexical-only, hybrid, and hybrid+rerank return deterministic stage-aware results.
- Chinese natural language, English natural language, mixed-language, and exact identifiers retrieve expected chunks.
- AUTO, Agentic, Workflow, API search, and Retrieval Lab share rankings.
- Immediate A/B results remain independently attributable and match direct search responses.

### Error and negative paths

- Empty/oversized queries, invalid search modes, unauthorized KB/document scopes.
- Missing embedding model in dense mode and valid lexical-only use.
- Qdrant, OpenSearch, embedding, and reranker timeout/failure combinations.
- Pending/error documents, failed chunks, inactive KBs, stale index records, and deleted documents.

### Regression scope

- Document processing/reprocessing/rechunking/deletion.
- Agent AUTO and Agentic RAG, streaming/regenerate paths, workflow retrieval, citations, and message persistence.
- Knowledge-base admin/platform route isolation and permissions.
- Existing search-test authenticated markdown rendering and i18n.
- Qdrant dimension management and existing embeddings.

## Risks & Mitigation

### Added OpenSearch infrastructure

- **Risk**: deployment and operational cost increase.
- **Mitigation**: version pinning, health checks, resource defaults, feature flag, dense-only fallback, and alias rollback.

### Dual-index inconsistency

- **Risk**: PostgreSQL, Qdrant, and OpenSearch disagree.
- **Mitigation**: PostgreSQL authority, idempotent writes/deletes, explicit per-index status/version, reconciliation metrics, and rebuild tooling.

### Misleading scores and configuration overload

- **Risk**: users interpret rank scores as probabilities or tune internals without evidence.
- **Mitigation**: stage-specific labels, rank display, simple defaults, and advanced controls hidden by default.

### Latency and model cost

- **Risk**: larger candidate pools and contextualization increase latency/cost.
- **Mitigation**: parallel recall, bounded concurrency/timeouts, one global rerank call, token budgets, per-stage metrics, and feature flags.

### Chinese lexical quality

- **Risk**: an analyzer optimized for English underperforms on Chinese or mixed identifiers.
- **Mitigation**: language-specific interactive checks, built-in analyzer baseline, identifier fields, maintainable domain dictionaries only after measured need, and no assumption that FastEmbed BM25 is Chinese-ready.

### Rollback plan

- Disable Retrieval V2 and OpenSearch lexical flags.
- Retain old endpoint compatibility and legacy config fields during rollout.
- Switch the OpenSearch alias to the prior index.
- Keep existing Qdrant collections and PostgreSQL records unchanged until the new path is stable.

## Deliberate Simplifications

- Learned Sparse, HyDE, multi-query generation, automatic tuning, and LLM-as-judge are outside the initial production baseline.
- Immediate A/B comparison executes independent retrieval variants in one batch envelope; only matching invocation-local query embeddings are shared.
