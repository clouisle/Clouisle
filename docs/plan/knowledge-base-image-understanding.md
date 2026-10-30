# Knowledge Base Image Understanding Design Document

## Background & Goals

New knowledge-base documents need safe image display, searchable visual content, scanned-PDF OCR, and configurable site-wide model and external-resource policies. Existing documents are not migrated or automatically reprocessed. Keep team authorization and model quotas intact; do not require per-knowledge-base configuration.

## High-Level Design

Extract bounded, validated image assets and source locations during ingestion. Site administrators configure a default vision model and external-image policy. Resolve that model under the owning team's authorization. Generate faithful OCR and visual descriptions as explicitly attributed untrusted content, then index alongside surrounding text using existing retrieval. Keep protected image URLs for authenticated display, not semantic embedding. Publish new processed versions only after all required components succeed; preserve prior versions on failure and prevent stale workers from publishing.

## Implementation Plan

### Stage 1: Display, safety and preview
- **Files modified**: `frontend/components/ui/chunk-markdown.tsx`, existing authenticated asset utilities, `backend/app/services/document_processor.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, related tests.
- **Specific logic**: Authenticate protected media, preserve sanitization, align preview markdown dispatch, bound and validate embedded images, prevent raw data URIs and unsafe SVG from entering indexed output.
- **Validation**: Exercise authenticated and unauthorized images, unsupported formats, resource bounds and preview/processing parity.

### Stage 2: Site configuration and image understanding
- **Files modified**: site settings schemas/defaults/API/admin UI/i18n, `backend/app/services/wechat_media.py`, document ingestion and tests.
- **Specific logic**: Configure site-default vision model and explicit limits; resolve model with team authorization and quotas. Reuse model invocation; extract visible text and factual description for DOCX/PPTX images with source metadata and bounded concurrency.
- **Validation**: Cover model selection, disabled/unavailable/unauthorized model, prompt injection, failures, image limits and searchable content.

### Stage 3: PDF OCR
- **Files modified**: document processor, PDF parsing dependencies, ingestion tasks and tests.
- **Specific logic**: Extract page text and render needed pages under bounded resources, supporting scans, mixed pages and charts; preserve page references without duplicating text.
- **Validation**: Exercise mixed and scanned pages, charts, encrypted and oversized files, and processing failures.

### Stage 4: Additional image sources
- **Files modified**: document processor, upload endpoints and frontend, site settings and tests.
- **Specific logic**: Extract XLSX embedded images with sheet/anchor metadata; support standalone images; optionally fetch external images under explicit default-off site policy with SSRF, redirect, byte, time and concurrency limits.
- **Validation**: Cover supported and unsupported images, workbook positions, disabled and malicious external links and redirect rebinding.

### Stage 5: Safe publication and status
- **Files modified**: knowledge-base tasks, storage/vector and lexical index integration, document status API/UI and tests.
- **Specific logic**: Stage versions and switch only after processing succeeds, with stale-task protection and cleanup. Expose partial image failures and processing progress without silently claiming success.
- **Validation**: Exercise failed reprocessing, stale tasks, cancellation, partial image failures, authorization and orphan cleanup.

### Stage 6: Documentation and verification
- **Files modified**: knowledge-base user/admin documentation and changelogs.
- **Specific logic**: Document configuration, model authorization, cost/privacy, limits, supported formats and historical-document exclusion.
- **Validation**: Run targeted regression suites and non-server end-to-end smoke scenarios; report browser-visual verification limitation.

## Testing Strategy

Test faithful OCR and image descriptions, page/slide/sheet attribution, indexing and retrieval, protected display, model authorization and quotas, unsupported inputs, SSRF/redirect checks, resource exhaustion, stale workers and rollback. Regress existing text-only ingestion, WeChat collection, Feishu synchronization, sharing and storage modes. No server or browser is started without explicit permission.

## Risks & Mitigation

Vision models can hallucinate or follow image instructions: separate recognition from descriptions, treat output as untrusted and retain source references. Model calls incur cost, latency and external data exposure: site configuration, bounded concurrency and explicit operator guidance. OCR may duplicate native PDF text: process per page and merge deliberately. Storage, relational and vector stores lack a shared transaction: stage immutable versions, guard publication and clean up safely. Rollback by disabling the site feature and reverting code while retaining original files and the last committed index.

## Implemented Contract

### Site configuration (`knowledge_base_images`, private)

| Key | Default | Bounds / meaning |
|---|---|---|
| `kb_image_understanding_enabled` | `false` | Requires a vision model and/or an OCR model |
| `kb_image_understanding_model_id` | `""` | UUID of an enabled chat model supporting image input |
| `kb_image_ocr_model_id` | `""` | Optional OCR-only image chat model; empty reuses the vision model if present |
| `kb_image_understanding_allow_external` | `false` | Separate opt-in for fetching external image URLs |
| `kb_image_understanding_max_images` | `8` | 1–20 images per document |
| `kb_image_understanding_max_image_bytes` | `10485760` | 1–52428800 |
| `kb_image_understanding_max_image_pixels` | `20000000` | 1–40000000 |
| `kb_image_understanding_concurrency` | `2` | 1–8, per document/process |

Admin page: `/site-settings/parsing`. Backend validation reuses `get_effective_input_capabilities` so provider defaults are honored. Enabling requires a vision model, an OCR model, or both; clearing the last remaining model while enabled is rejected.

### Ingestion

- `backend/app/services/kb_image_ingestion.py` provides `image_settings()`, `prepare_document()`, `ingest_pdf_pages()`, `ingest_xlsx_images()`, `ingest_external_images()`, and `enrich_document_images()`.
- `DocumentType.IMAGE` accepts PNG/JPEG/GIF/WebP uploads; processing requires image understanding, otherwise it fails explicitly instead of indexing an empty document.
- DOCX/PPTX images flow through MarkItDown data URIs. PDF pages are processed per page (native text + bounded render); XLSX drawings are extracted with sheet/anchor metadata.
- Image assets remain served through the authenticated KB media endpoint. Indexed text contains the model's OCR and factual description; internal media URLs are stripped from embedding input while alt text is retained.

### Safety and performance

- Embedded assets: MIME allowlist, byte/pixel/count caps, Pillow verification, deduplication by content hash.
- External images: central SSRF validation, pinned resolution, redirect re-validation, no proxy/cookies, byte and pixel caps.
- Vision calls: team model authorization, quota accounting, 60 s timeout, bounded output, prompt-injection hardening, untrusted output sanitized before indexing. When a distinct OCR model is configured, OCR uses an OCR-only prompt and the vision model uses a description-only prompt; both calls share one normalized image and run concurrently. With only an OCR model, text is indexed and the description annotation is omitted.
- Preview: Redis single-flight cache (15-minute TTL, user/version-bound, 5 MiB cap) so `process-with-chunks` reuses the preview's OCR instead of calling the model again.
- Publication: completed documents keep their published chunks, lexical projection and media until a hidden `rechunk_staging` replacement is fully embedded. Promotion switches PostgreSQL chunks/counters and pg_search in one transaction; Qdrant re-tagging and old-media cleanup are journaled and retryable. Stale tasks never publish, and staging documents are rejected by document/media/chunk endpoints and excluded from lists and stats.

### Scope

Only documents processed after enabling the feature gain image understanding. No historical migration, automatic reindex, or backfill is performed.

### Verification

- Backend: `python -m pytest --no-cov tests -q -p no:cacheprovider` → 11035 passed, 4 skipped.
- Frontend: `bunx tsc --noEmit` clean; knowledge-base/retrieval/site-settings suites → 356 passed (59 files), plus upload-dialog and admin page tests.
- Ruff on changed backend modules → clean.
- Browser end-to-end verification completed on 2026-10-30 against the running local stack (see below); test data and temporary settings were removed afterwards.
- Split-model path verified with real providers: `DeepSeek V4.1 Flash` as the OCR model and `gemini-3.8-flash` as the description model. OCR returned the exact visible text (`OCR-SPLIT-9001`), and the description model described only the non-text visual content.
- OCR-only path verified with `DeepSeek V4.1 Flash`: text `OCR ONLY 4711` was extracted and the description stayed empty; standalone images with no extracted text fail with `image_no_text_extracted` instead of indexing an empty document.

### Browser End-to-End Verification (2026-10-30)

Tested against the running local stack (Next.js dev server, FastAPI server, Celery worker, PostgreSQL, Redis, Qdrant) with a superuser session:

1. Site settings: enabled image understanding, selected an image-capable chat model, saved; values persisted and survived reload.
2. Created a Demo Team knowledge base with BGE M3 embedding and BGE reranker.
3. Uploaded DOCX (embedded image), PDF (text + vector chart), XLSX (anchored image), and standalone PNG; all four accepted.
4. Batch preview produced chunks containing the protected media URL plus `Image description:` and `Image text:` from the vision model for every document (after retrying three documents whose first preview hit a transient provider failure).
5. Processed all four documents: all reached `completed` with 1 chunk each.
6. Document detail rendered the embedded image through the authenticated media endpoint (blob URL, non-zero natural size) next to the OCR text.
7. Retrieval query `CLAIMS-CODE-7788` (present only in image OCR) returned all four documents with image results; the result panel rendered the authenticated image.
8. Reprocessed a completed DOCX through the preview editor: the published chunk stayed searchable during processing, then the chunk ID changed atomically, the document remained `completed`, preview keys were removed, and the media pointer stayed valid.
9. Inserted a synthetic `rechunk_staging` document: detail returned 404 and lists excluded it.

Bugs found and fixed during this pass:

- Preview cache rejected any metadata key named `url`, breaking every preview with media assets; removed the over-broad key restriction (query-token/data-URI checks remain).
- `kb_rechunk_staging` imported the `app.services.vector_store` singleton instead of the module, so post-promotion Qdrant cleanup failed and left the journal behind; switched to direct function imports and added a regression test.
- `process-with-chunks` on completed documents dispatched the replacement but then returned HTTP 500 because the response document lacked the `uploaded_by` relation; reload before serialization.
- The dashboard upload dialog hardcoded supported formats without images; now derives the label from the shared accepted-types constant.
- Deleting a knowledge base left Qdrant points and stored source/media files behind; deletion now purges vectors, lexical rows, media directories, and original files before the relational cascade, with a regression test.
- Vision provider failures surfaced as a generic preview/processing error; preview now returns a localized `image_understanding_failed` message with the provider error code, and task processing records the same actionable message.

Final regression after the fixes: backend full suite and frontend typecheck/related tests were rerun; test data and temporary settings created for this verification were removed.
