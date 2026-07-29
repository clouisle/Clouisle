# PostgreSQL pg_search Lexical Retrieval Design Document

## Background & Goals

Clouisle currently stores authoritative knowledge-base records in PostgreSQL, dense vectors in Qdrant, and a duplicate lexical projection in OpenSearch. The lexical projection adds a separate service, index lifecycle, credentials, reconciliation, and failure mode even though its searchable content originates in PostgreSQL.

This change replaces OpenSearch with ParadeDB `pg_search` BM25 inside PostgreSQL. It is a direct cutover: there is no dual-write period, shadow traffic, or evaluation platform. Qdrant remains the dense retriever, and the existing retrieval service continues to combine dense and lexical ranks with weighted reciprocal-rank fusion (RRF).

### Goals

- Run authoritative relational data and lexical BM25 retrieval in the same PostgreSQL service.
- Preserve the current public and internal retrieval contracts rather than introducing a new search API.
- Preserve exact UUID identity and authorization scope through `team_id`, `kb_id`, `document_id`, and `chunk_id`.
- Preserve the current `vector`, `fulltext`, and `hybrid` modes, stage-specific scores/ranks, deterministic ordering, and weighted-RRF behavior.
- Support Chinese and mixed-language chunk text with the `pdb.jieba` tokenizer while retaining exact identifier retrieval.
- Remove OpenSearch only after PostgreSQL 17, the extension, schema, index, and integration checks are ready for one coordinated maintenance-window cutover.

### Success criteria

> Follow-up: the original Debian package image remains the verified baseline. The sub-500 MB Alpine/musl image work is tracked separately in [`postgres-pg-search-alpine-image.md`](postgres-pg-search-alpine-image.md) and must pass both native architectures before replacing this baseline.

- The database image is pinned to the project-built `clouisle-postgres-pg-search:0.24.3-pg17` image (`postgres:17` plus the checksum-verified pg_search 0.24.3 package); mutable or unqualified tags are not accepted.
- Existing PostgreSQL 16 installations follow a tested PostgreSQL major-version migration runbook using `pg_upgrade` or logical backup/restore; an existing PG16 data directory is never mounted directly into PG17.
- Database initialization runs `CREATE EXTENSION pg_search CASCADE` and verifies the installed extension version.
- PostgreSQL starts with `shared_preload_libraries` containing both `pg_search` and `pg_stat_statements` and both extensions load successfully after restart.
- Lexical searches use a `pg_search` BM25 index and `pdb.jieba` for Chinese and mixed-language text.
- Existing callers receive the same `RetrievalRequest`, `RetrievalTarget`, `RetrievalResponse`, result identifiers, score/rank fields, diagnostics, and weighted-RRF semantics.
- Integration tests cover lexical-only, hybrid, lifecycle, authorization, deletion, migration initialization, and degraded-channel behavior; no batch evaluation or evaluation platform is added.
- An AGPL-3.0 compliance review is approved and recorded before any production deployment.

## High-Level Design

### Components

- **ParadeDB PostgreSQL**: replace the current PostgreSQL image with the project-built `clouisle-postgres-pg-search:0.24.3-pg17` image (`postgres:17` plus the verified pg_search 0.24.3 package); retain all existing application tables and add the `pg_search` extension.
- **`knowledge_lexical_chunks` projection**: a PostgreSQL table containing one searchable row per authoritative `document_chunks.id`. It keeps the existing lexical field names and UUIDs: `chunk_id`, `document_id`, `kb_id`, `team_id`, `status`, `name`, `content`, `metadata`, `chunk_index`, `update_version`, `language`, `section`, `title`, and `identifiers`.
- **BM25 index `knowledge_lexical_chunks_bm25_idx`**: key field `chunk_id`; indexes the authorization/scope columns and searchable text. `content`, `title`, `name`, and `section` use `pdb.jieba` for Chinese and mixed-language tokenization. `identifiers` remains a separately queryable exact-identifier representation rather than relying on Chinese segmentation.
- **PostgreSQL lexical adapter**: keeps the existing `LexicalStore` boundary and `SearchHit(chunk_id, score, source)` behavior, but executes parameterized SQL against `pg_search` instead of HTTP requests to OpenSearch.
- **Knowledge lifecycle tasks**: upsert or delete the PostgreSQL lexical projection in the same existing document/chunk processing paths. The projection remains rebuildable from `knowledge_bases`, `documents`, and `document_chunks`; those existing tables remain authoritative.
- **`KnowledgeRetrievalService`**: unchanged orchestration boundary. Qdrant supplies dense candidates, PostgreSQL supplies lexical candidates, and the service retains current failure handling, result shaping, reranking, and context assembly.

### Data flow

```text
authoritative PostgreSQL knowledge_bases/documents/document_chunks
  -> existing process/reprocess/rechunk/delete lifecycle
  -> knowledge_lexical_chunks upsert/delete in PostgreSQL
  -> pg_search BM25 index

RetrievalRequest(query, targets, vector|fulltext|hybrid, weights, rrf_k, ...)
  -> Qdrant dense recall when requested
  -> PostgreSQL pg_search lexical recall when requested
       scoped by team_id + kb_id + optional document_id
  -> existing lexical SearchHit/result normalization
  -> existing weighted RRF keyed by chunk_id
  -> existing optional rerank and bounded context assembly
  -> RetrievalResponse(results, diagnostics, timings)
```

### Contract preservation

The cutover must not rename or reinterpret current retrieval identifiers and fields:

- Request/target scope: `query`, `targets`, `kb_id`, `team_id`, `allowed_document_ids`, `document_ids`, `search_mode`, `top_k`, `score_threshold`, `timeout_seconds`, `dense_weight`, `lexical_weight`, and `rrf_k`.
- Modes: `vector`, `fulltext`, and `hybrid`.
- Identity: `chunk_id` is the lexical key and the weighted-RRF merge key; `document_id`, `kb_id`, and `team_id` remain UUID strings at the result boundary.
- Lexical output: `score`, `lexical_score`, `lexical_rank`, `search_type="fulltext"`, and `final_score_stage="lexical"`.
- Hybrid output: `fusion_score`, `fusion_rank`, `search_type="hybrid"`, and `final_score_stage="fusion"`, calculated as the current sum of `weight / (rrf_k + rank)` per `chunk_id`.
- Deterministic ties continue to order by score descending, then `document_id`, then `chunk_id`.
- Dense score thresholds remain dense-only. Raw BM25 and RRF values are not probabilities.

### Database and index definition

The implementation migration must use stable, explicit identifiers and be idempotent:

```sql
CREATE EXTENSION pg_search CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE TABLE knowledge_lexical_chunks (
    chunk_id uuid PRIMARY KEY,
    document_id uuid NOT NULL,
    kb_id uuid NOT NULL,
    team_id uuid NOT NULL,
    status text NOT NULL,
    name text NOT NULL,
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    chunk_index integer NOT NULL,
    update_version bigint NOT NULL,
    language text,
    section text,
    title text NOT NULL,
    identifiers text[] NOT NULL DEFAULT ARRAY[]::text[]
);

CREATE INDEX knowledge_lexical_chunks_bm25_idx
ON knowledge_lexical_chunks
USING bm25 (
    chunk_id,
    team_id,
    kb_id,
    document_id,
    status,
    (content::pdb.jieba),
    (title::pdb.jieba),
    (name::pdb.jieba),
    (section::pdb.jieba),
    identifiers,
    chunk_index,
    update_version
)
WITH (key_field = 'chunk_id');
```

The migration must validate this exact DDL against `pg_search` 0.24.3 before adoption, including nullable `section` and `text[]` support. If 0.24.3 requires a documented expression or type adjustment, update this design and the migration together; do not silently change application-facing field names. Query construction must preserve the current field intent: `content` recall, boosted `title` and `name`, `section`, and exact `identifiers`, with mandatory `team_id` plus requested `kb_id`/`document_id` filters applied inside SQL.

### Cutover sequence

This is a maintenance-window direct cutover, not a gradual rollout:

1. Pass the AGPL-3.0 compliance gate and rehearse restore procedures.
2. Stop API and worker writes; drain knowledge-processing tasks.
3. Take and verify a PostgreSQL 16 backup and retain the old data directory unchanged.
4. Upgrade PG16 data to PG17 with a rehearsed `pg_upgrade`, or initialize PG17 and restore a logical backup. Run `ANALYZE` and application migration checks afterward.
5. Start the project-built `clouisle-postgres-pg-search:0.24.3-pg17` image (`postgres:17` plus the verified pg_search 0.24.3 package) with `shared_preload_libraries = 'pg_search,pg_stat_statements'` (merge with any other required libraries rather than overwriting them), then restart and verify both libraries/extensions.
6. Run `CREATE EXTENSION pg_search CASCADE`, create the projection and BM25 index, and backfill it once from authoritative completed/active knowledge records while writes remain stopped.
7. Validate counts, UUID scopes, BM25 queries, lifecycle integration, and the integration suite.
8. Deploy the PostgreSQL lexical adapter and remove OpenSearch configuration/services in the same release; resume workers and API only after health checks pass.

There is deliberately no interval in which the application writes to or reads from both OpenSearch and PostgreSQL lexical stores.

## Implementation Plan

### Stage 1: PostgreSQL 17 Migration and Compliance Readiness

- **Files modified**: deployment Compose/Kubernetes/Helm values and templates, PostgreSQL initialization/configuration, environment examples, operator deployment documentation, and focused deployment integration fixtures.
- **Specific logic**:
  - Complete an AGPL-3.0 compliance review of distributing and operating ParadeDB/`pg_search`; make written approval a blocking pre-deployment gate.
  - Pin every supported deployment path to the project-built `clouisle-postgres-pg-search:0.24.3-pg17` image (`postgres:17` plus the verified pg_search 0.24.3 package).
  - Configure `shared_preload_libraries` to include `pg_search` and `pg_stat_statements`, preserving any additional required libraries, and require a PostgreSQL restart after changes.
  - Add an explicit PG16-to-PG17 runbook. Existing PG16 data must move via tested `pg_upgrade` or logical backup/restore; direct reuse of a PG16 data directory by PG17 is forbidden.
  - Specify maintenance-window prerequisites, write/task drain, backup verification, storage capacity, extension checks, `ANALYZE`, and restore checkpoints.
- **Validation**:
  - Start a fresh pinned PG17 container and verify image/version, preload settings, database readiness, and extension availability.
  - Rehearse both the selected upgrade method and backup restore using representative PG16 data.
  - Intentionally attempt startup without required preload entries and confirm the readiness check fails before application traffic.
  - Confirm production deployment remains blocked without recorded AGPL-3.0 approval.

### Stage 2: pg_search Extension, Lexical Relation, and BM25 Index

- **Files modified**: backend database migrations/initialization, knowledge-base models only if the projection is ORM-managed, and migration integration tests.
- **Specific logic**:
  - Install with `CREATE EXTENSION pg_search CASCADE` and retain `pg_stat_statements` initialization.
  - Create `knowledge_lexical_chunks` with the exact columns and types defined above; `chunk_id` is the UUID primary key and BM25 `key_field`.
  - Create `knowledge_lexical_chunks_bm25_idx` using `pdb.jieba` for `content`, `title`, `name`, and `section`; index `identifiers` separately for exact matching and include scope/filter columns.
  - Populate one row per eligible authoritative chunk: active knowledge base, completed document, and the same chunk-status eligibility currently used by retrieval/indexing.
  - Make schema creation and one-time backfill restart-safe and idempotent while application writes are stopped.
- **Validation**:
  - Apply migrations on an empty database and an upgraded/restored database.
  - Verify extension version, table constraints, index validity, row counts, UUID equality, and query plans using the BM25 index.
  - Verify Chinese, English, mixed Chinese/English, UUID, path, version, error code, and configuration-key searches.
  - Trigger duplicate `chunk_id`, missing scope IDs, and interrupted backfill cases and verify fail-fast or idempotent recovery behavior.

### Stage 3: PostgreSQL Lexical Adapter and Lifecycle Integration

- **Files modified**: `backend/app/services/lexical_store.py`, `backend/app/services/retrieval.py` only if adapter wiring requires it, existing knowledge-base processing/deletion tasks and endpoints, backend configuration, and focused integration tests.
- **Specific logic**:
  - Retain the `LexicalStore`/`SearchHit` boundary but replace OpenSearch HTTP/index-alias operations with parameterized PostgreSQL BM25 queries and projection upsert/delete/count/reconcile operations.
  - Preserve current source keys exactly: `chunk_id`, `document_id`, `kb_id`, `team_id`, `status`, `name`, `content`, `metadata`, `chunk_index`, `update_version`, `language`, `section`, `title`, and `identifiers`.
  - Enforce mandatory `team_id`, requested `kb_id`, and optional `document_id` scopes within the SQL query before ranking/limiting.
  - Preserve lifecycle semantics for process, retry, reprocess, rechunk, document deletion, chunk deletion, and knowledge-base deletion without application-level dual writes.
  - Preserve sanitized timeout/failure diagnostics and hybrid degradation: PostgreSQL lexical failure may degrade hybrid to Qdrant dense, while requested lexical-only failure remains explicit.
- **Validation**:
  - Integration tests use a real ParadeDB PG17 service, not mocked SQL or an evaluation harness.
  - Verify upsert idempotency, changed content, rechunk replacement, retry, document/KB/chunk deletes, scoped counts, and reconciliation.
  - Verify unauthorized team/KB/document IDs cannot widen scope and SQL parameters reject injection payloads.
  - Stop or invalidate `pg_search` during tests and verify lexical-only and hybrid failure contracts.

### Stage 4: Direct Cutover and OpenSearch Removal

- **Files modified**: backend dependency/configuration files, deployment Compose/Kubernetes/Helm manifests, environment examples, OpenSearch-specific tests, and operator documentation.
- **Specific logic**:
  - Execute the maintenance-window sequence above with writes stopped; create/backfill/validate PostgreSQL BM25 before resuming traffic.
  - Switch the sole lexical implementation to PostgreSQL in the same release that removes OpenSearch services, credentials, health checks, aliases, backfill commands, and client dependencies.
  - Remove OpenSearch version/alias observability and replace it with PostgreSQL extension/index health signals without changing retrieval response contracts.
  - Do not retain a feature flag, dual write, shadow request, OpenSearch fallback, or parallel lexical index.
- **Validation**:
  - Static-render all deployment variants and prove no OpenSearch image, endpoint, credential, volume, or dependency remains.
  - Run one full maintenance-window rehearsal from PG16 backup through PG17 start, schema/backfill, application start, and smoke retrieval.
  - Verify workers cannot resume before migration, extension, index, and count checks succeed.

### Stage 5: Integration Validation and Operator Documentation

- **Files modified**: backend integration tests and existing deployment/operator documentation.
- **Specific logic**:
  - Add integration coverage only; do not recreate datasets, labeling, batch runs, parameter sweeps, quality targets, or any evaluation platform.
  - Document installation, PG16-to-PG17 migration, extension/preload verification, BM25 index inspection/rebuild, count reconciliation, backup, restore, and failure diagnosis.
  - Record the exact production cutover checklist, owners, maintenance window, acceptance evidence, and rollback decision point.
- **Validation**:
  - Run fresh-install and upgraded-database integration suites against the project-built `clouisle-postgres-pg-search:0.24.3-pg17` image (`postgres:17` plus the verified pg_search 0.24.3 package).
  - Exercise `fulltext` and `hybrid` through the actual retrieve endpoint and production callers, checking exact IDs, score/rank fields, RRF, diagnostics, citations, and bounded context.
  - Confirm Retrieval Lab remains a production-faithful interactive caller and no evaluation routes, models, tasks, or UI are introduced.
  - Complete a restore drill before approving production cutover.

## Testing Strategy

### Happy path tests

- Fresh PG17 initialization loads `pg_search` and `pg_stat_statements`, applies schema, and creates a valid BM25 index.
- Restored/upgraded PG16 records retain UUIDs and relationships in PG17.
- Process, retry, reprocess, and rechunk operations leave exactly one current projection row per eligible `chunk_id`.
- Lexical-only retrieval returns deterministic `SearchHit` and lexical result fields for Chinese, English, mixed-language, and exact-identifier queries.
- Hybrid retrieval fuses Qdrant and PostgreSQL candidates with the unchanged weighted-RRF formula and deterministic tie ordering.
- Retrieve endpoint, AUTO RAG, Agentic retrieval, Workflow retrieval, internal Agent retrieval, and Retrieval Lab preserve their current request/response behavior.

### Error path tests

- Missing `pg_search`, missing preload libraries, invalid BM25 index, or incompatible extension version blocks readiness/cutover.
- A PG16 data directory presented to PG17 is rejected by the runbook/preflight rather than modified.
- Empty or invalid scope, unauthorized `team_id`/`kb_id`/`document_id`, SQL injection-shaped query text, and deleted/inactive records return no widened results.
- Projection upsert conflict, interrupted backfill, failed lifecycle transaction, PostgreSQL timeout, and BM25 query failure produce bounded, sanitized behavior.
- Lexical-only failure is explicit; hybrid lexical failure degrades to dense under the existing retrieval failure contract; loss of both channels remains an explicit retrieval error.

### Regression scope

- Existing PostgreSQL application data and migrations across the PG17 major upgrade.
- Qdrant vector-only retrieval and embedding lifecycle.
- Weighted RRF, rerank, adjacent expansion, bounded context, and citation provenance.
- Knowledge document upload, processing, retry, reprocessing, rechunking, and deletion.
- Team/KB/document authorization and dashboard/platform route isolation.
- Retrieval Lab interactive search and A/B calls, without evaluation-platform behavior.
- Deployment health checks, backup/restore, worker startup ordering, and observability.

## Risks & Mitigation

### PostgreSQL major-version migration

- **Risk**: the image change also moves PostgreSQL 16 to 17; existing data files are not binary-compatible across majors.
- **Mitigation**: require a maintenance window, tested `pg_upgrade` or logical backup/restore, verified backups, retained PG16 data, post-upgrade `ANALYZE`, extension/index checks, and a completed restore drill.

### Shared database resource contention

- **Risk**: BM25 indexing and queries now compete with transactional application traffic for PostgreSQL CPU, memory, I/O, locks, connections, and disk.
- **Mitigation**: establish resource and connection budgets, tune index creation separately, observe query/index latency through PostgreSQL statistics, bound retrieval timeouts, and rehearse backfill with writes stopped.

### Chinese and mixed-language behavior

- **Risk**: `pdb.jieba` segmentation may be slower or may split domain identifiers unexpectedly.
- **Mitigation**: use `pdb.jieba` for natural-language fields, retain a separate exact `identifiers` field, and cover representative Chinese/mixed/identifier cases with integration tests rather than unverified quality claims.

### Projection consistency

- **Risk**: authoritative chunk rows and `knowledge_lexical_chunks` can diverge if a lifecycle operation fails between writes.
- **Mitigation**: use PostgreSQL transactions where lifecycle boundaries permit, idempotent upsert/delete operations, scoped count reconciliation, and a rebuild procedure sourced only from authoritative knowledge tables.

### Licensing

- **Risk**: ParadeDB/`pg_search` is AGPL-3.0 and deployment or distribution obligations may conflict with product policy.
- **Mitigation**: legal/compliance approval is a mandatory pre-deployment gate. No production cutover occurs until obligations and required notices/source availability are documented and approved.

### Rollback plan

- Set a final go/no-go checkpoint before resuming application writes on PG17. Before that checkpoint, stop the PG17 environment and restart the retained PG16 application/database and prior OpenSearch deployment.
- After writes resume, rollback requires another maintenance window: stop writes, preserve the failed PG17 state for diagnosis, restore the verified PG16-compatible backup (or an approved reverse logical export) into the prior stack, restore the prior application/deployment release, rebuild OpenSearch from authoritative PostgreSQL data if its retained index is unusable, and validate counts/retrieval before reopening traffic.
- Do not attempt to mount the PG17 data directory in PG16, and do not treat OpenSearch as a live rollback target during normal operation; direct cutover intentionally provides no dual-write safety net.
