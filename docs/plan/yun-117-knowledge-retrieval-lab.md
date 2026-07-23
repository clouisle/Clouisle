# YUN-117 Knowledge Retrieval Optimization and Evaluation Lab Design Document

## Background & Goals

Clouisle currently retrieves knowledge-base chunks through Qdrant dense search, a heuristic `jieba + icontains` lexical path, application-level RRF, and optional reranking. The existing knowledge-base search-test page exposes one-query parameter testing, but the platform cannot measure retrieval quality across a labeled dataset or reliably compare configurations.

The current implementation has these confirmed problems:

- `fulltext` is not BM25 and has no inverted-index ranking, corpus IDF, or document-length normalization.
- `score_threshold` is applied to incompatible score types across dense, lexical, RRF, and rerank stages.
- AUTO RAG skips lexical-only knowledge bases without an embedding model.
- Multi-knowledge-base AUTO retrieval is sequential and lacks global ranking and a global context bound.
- Lexical candidates are truncated without deterministic relevance ordering before application scoring.
- Search entry points call `VectorStore` directly and have diverging failure and aggregation behavior.
- The search-test UI formats scores with different semantics as percentages.

### Goals

1. Establish a reproducible retrieval-quality baseline before changing algorithms.
2. Centralize all knowledge retrieval through one service and one result contract.
3. Replace heuristic lexical matching with production BM25 while retaining Qdrant dense retrieval.
4. Fuse dense and lexical ranks without treating fusion scores as probabilities.
5. Apply reranking globally and assemble bounded, citation-safe context.
6. Upgrade the existing search test into an instant playground, A/B comparator, and batch evaluation lab.
7. Roll out through shadow traffic, observable feature flags, and reversible index aliases.

### Success criteria

- Recall@20 improves by at least 15% over the current hybrid baseline.
- nDCG@10 improves by at least 10%.
- Identifier-heavy Recall@10 is at least 95%.
- Citation correctness is at least 90% on the evaluation set.
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
- Evaluation services: immutable configuration snapshots, metric calculation, and asynchronous run orchestration.
- Retrieval Lab: uses the same retrieval service as production paths; it must not reproduce retrieval logic in the frontend.

### Score contract

Each result preserves stage-specific values:

- `dense_score` and `dense_rank`
- `lexical_score` and `lexical_rank`
- `fusion_score` and `fusion_rank`
- `rerank_score` and `rerank_rank`
- `final_score`, whose stage is explicitly identified

Dense thresholds apply only to dense recall. Lexical retrieval is controlled by rank/candidate count. Fusion scores are never presented as probabilities or filtered by the legacy similarity threshold. A calibrated rerank threshold may filter final results when a reranker is active.

### Initial evaluation parameters

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

These are evaluation baselines, not permanent hard-coded product limits.

## Implementation Plan

### Stage 1: Retrieval Evaluation Baseline ✅

- **Completed validation**: deterministic metric and snapshot contracts added; 6,246 backend tests passed at 97.82% line/95.11% branch coverage; 1,998 frontend tests passed at 97.77% line/95.04% function coverage; frontend source census and production build passed.
- **Files modified**: new backend evaluation metric module and focused tests; test fixture/data format under backend tests or a documented developer fixture location.
- **Specific logic**:
  - Define query cases with graded document/chunk relevance and expected-empty cases.
  - Calculate Recall@K, MRR@K, nDCG@K, empty-result accuracy, and latency summaries without a new metrics dependency.
  - Add a runner contract able to snapshot current vector/fulltext/hybrid/rerank results.
  - Start with representative checked-in synthetic cases; production evaluation datasets remain database records added in Stage 8.
- **Validation**:
  - Happy-path metric examples with known expected values.
  - Empty labels, duplicate retrieved IDs, fewer than K hits, and expected-empty negative tests.
  - Capture the current implementation's baseline before Stage 3 changes.

### Stage 2: Correct Current Retrieval Semantics ✅

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

### Stage 4: OpenSearch BM25 Indexing and Weighted Fusion

- **Files modified**: backend dependencies/config, a lexical-store service, document processing/rechunk/delete tasks, deployment manifests/Helm values, migrations if index state is persisted, and tests.
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

### Stage 5: Global Rerank and Bounded Context Assembly

- **Files modified**: retrieval service, RAG context builder, schemas/config, and tests.
- **Specific logic**:
  - Rerank the global fused candidate set once rather than reranking independently per KB.
  - Optionally expand one adjacent chunk on each side after ranking; adjacent chunks do not acquire artificial ranking scores.
  - Aggregate by document while retaining chunk-level citation provenance.
  - Enforce final top K, maximum documents, maximum chunks per document, and context token budget.
- **Validation**:
  - Rerank failure respects fail-open/fail-closed configuration.
  - Expansion does not cross unauthorized documents and does not exceed token budget.
  - Citations map to the content actually supplied to the answer model.

### Stage 6: Instant Retrieval Playground and A/B Comparison

- **Files modified**: existing platform/dashboard search-test clients, shared frontend API types, backend diagnostic response, English/Chinese translations and generated i18n types, and tests.
- **Specific logic**:
  - Rename/reframe the existing search test as Retrieval Lab without creating a separate search implementation.
  - Default UI exposes mode, final top K, and rerank toggle; advanced settings expose candidate/fusion/rerank parameters with precise labels.
  - Display stage scores as raw values and ranks, not universal percentages.
  - Show retriever channel, rank changes, keyword highlights, stage latency, and fallback reason.
  - Compare two configurations side by side and compute result overlap/rank movement.
  - Allow relevant/partially relevant/not relevant annotations and named configuration presets.
  - Applying a preset to production requires confirmation and `kb:update` authorization.
- **Validation**:
  - Search, empty, error, degraded, reranked, and no-reranker states.
  - A/B results remain independently attributable to each configuration.
  - Chinese IME Enter behavior and authenticated markdown media remain intact.
  - Frontend lint, build, and focused component/API tests pass.

### Stage 7: Evaluation Datasets and Batch Runs

- **Files modified**: new evaluation models/migration/schemas/API/service/Celery task; frontend Retrieval Lab batch tab; permissions/i18n; tests.
- **Specific logic**:
  - Persist datasets, graded cases, immutable run configuration/version snapshots, and per-case result IDs/ranks/scores/metrics.
  - Support manual cases and validated CSV/JSON import.
  - Run one or more configurations asynchronously with bounded concurrency and quota checks.
  - Display aggregate metrics, latency/cost, and failure-case filters.
  - Avoid duplicating chunk content in run records; resolve content under current authorization when viewed.
  - Never auto-publish a winning configuration.
- **Validation**:
  - Dataset CRUD authorization, import validation, cancel/failure/retry states, metric correctness, retention/deletion behavior, and KB cascade cleanup.

### Stage 8: Query Contextualization Experiment

- **Files modified**: retrieval request preparation, optional model prompt/config, diagnostics, evaluation cases, and tests.
- **Specific logic**:
  - Trigger only for AUTO RAG queries that are short, referential, or depend on previous entities.
  - Use the rewritten standalone query only for retrieval; preserve the original question for answering.
  - Fall back to the original query on timeout/error and forbid unsupported factual additions.
  - Do not add a second rewrite to Agentic tool queries by default.
- **Validation**:
  - Referential multi-turn cases improve without regressing standalone queries.
  - Failures have no effect on answer availability.

### Stage 9: Learned Sparse Evaluation Gate

- **Files modified**: evaluation-only adapter/config and benchmark documentation unless the production gate is met.
- **Specific logic**:
  - Compare Dense + BM25, Dense + learned sparse, and three-way retrieval on Chinese, English, and mixed cases.
  - Measure quality, P95, index size, rebuild time, and inference cost.
  - Do not add production indexing unless Recall/nDCG improves by at least 5% without language regression and operational limits are acceptable.
- **Validation**:
  - Reproducible benchmark report and explicit go/no-go decision.

### Stage 10: Rollout, Observability, and Documentation

- **Files modified**: feature flags/config, metrics/logging, deployment docs, operator docs, and relevant design docs.
- **Specific logic**:
  - Feature flags for Retrieval V2, OpenSearch lexical retrieval, weighted fusion, global rerank, and query contextualization.
  - Shadow execution records IDs/ranks/latency only and does not alter answers.
  - Structured metrics cover candidate counts, stage latency, fallbacks, empty results, model/index versions, and failures.
  - Roll out internal -> 5% -> 25% -> 50% -> 100% with documented rollback gates.
- **Validation**:
  - Turning off Retrieval V2 restores the old path.
  - OpenSearch alias and feature-flag rollback are exercised in staging.
  - Full backend and frontend pre-commit checks pass.

## Testing Strategy

### Happy path

- Dense-only, lexical-only, hybrid, and hybrid+rerank return deterministic stage-aware results.
- Chinese natural language, English natural language, mixed-language, and exact identifiers retrieve expected chunks.
- AUTO, Agentic, Workflow, API search, and Retrieval Lab share rankings.
- A/B and batch evaluation metrics match hand-calculated examples.

### Error and negative paths

- Empty/oversized queries, invalid search modes, unauthorized KB/document scopes.
- Missing embedding model in dense mode and valid lexical-only use.
- Qdrant, OpenSearch, embedding, and reranker timeout/failure combinations.
- Pending/error documents, failed chunks, inactive KBs, stale index records, and deleted documents.
- Invalid evaluation imports, duplicate labels, expected-empty cases, cancellation, and quota exhaustion.

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
- **Mitigation**: stage-specific labels, rank display, simple defaults, advanced controls hidden by default, and evaluation-backed presets.

### Latency and model cost

- **Risk**: larger candidate pools and contextualization increase latency/cost.
- **Mitigation**: parallel recall, bounded concurrency/timeouts, one global rerank call, token budgets, per-stage metrics, and feature flags.

### Chinese lexical quality

- **Risk**: an analyzer optimized for English underperforms on Chinese or mixed identifiers.
- **Mitigation**: language-specific evaluation, built-in analyzer baseline, identifier fields, maintainable domain dictionaries only after measured need, and no assumption that FastEmbed BM25 is Chinese-ready.

### Rollback plan

- Disable Retrieval V2 and OpenSearch lexical flags.
- Retain old endpoint compatibility and legacy config fields during rollout.
- Switch the OpenSearch alias to the prior index.
- Keep existing Qdrant collections and PostgreSQL records unchanged until the new path is stable.

## Deliberate Simplifications

- Learned Sparse, HyDE, multi-query generation, automatic tuning, and LLM-as-judge are outside the initial production baseline.
- Initial A/B comparison may execute two normal retrieval calls; shared embedding work is added only if measured cost warrants it.
- The first evaluation corpus can use checked-in synthetic fixtures while the product database model is built later.
