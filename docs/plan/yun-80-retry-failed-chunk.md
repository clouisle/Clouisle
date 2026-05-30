# YUN-80 Retry Failed Chunk Design Document

## Background & Goals
- Knowledge-base vectorization can partially fail at the chunk level.
- Users need to retry one failed chunk without reprocessing the whole document or retrying every failed chunk.
- Success criteria: failed chunks are visible in failed documents; one failed chunk can be retried; document status reflects remaining failed chunks.

## High-Level Design
- Reuse existing `DocumentChunk.status` and `DocumentChunk.error_message` fields.
- Add one Celery task that embeds a single failed chunk through `VectorStore.add_chunk_vector`.
- Add one backend route under the existing document chunk resource.
- Expose the API through the shared frontend knowledge-base client.
- Keep dashboard/admin and platform/user UIs separate but behaviorally aligned.

## Implementation Plan

### Stage 1: Backend chunk retry task and API
- **Files modified**: `backend/app/tasks/knowledge_base.py`, `backend/app/api/v1/endpoints/knowledge_bases.py`, `backend/app/locales/en/LC_MESSAGES/messages.po`, `backend/app/locales/zh/LC_MESSAGES/messages.po`
- **Specific logic**: Add `retry_failed_chunk_task`, add `POST /{kb_id}/documents/{doc_id}/chunks/{chunk_id}/retry-embedding`, reject non-failed chunks, dispatch async retry, and update document state based on remaining failures.
- **Validation**: Run backend lint/type checks and targeted API/task tests if practical.

### Stage 2: Frontend API and detail-page controls
- **Files modified**: `frontend/lib/api/knowledge-bases.ts`, dashboard/platform document detail components, `frontend/i18n/en/knowledgeBases.json`, `frontend/i18n/zh/knowledgeBases.json`
- **Specific logic**: Add `retryFailedChunk`, load chunks for failed documents, show failed chunk status/error, add per-chunk retry buttons, and keep retry-all available.
- **Validation**: Regenerate i18n types, run translation lint, frontend lint, and build.

### Stage 3: Document-list recovery access
- **Files modified**: dashboard/platform documents table components
- **Specific logic**: Allow failed documents to open the chunk editor; add platform retry-all action parity.
- **Validation**: Confirm failed documents can navigate to detail pages from both route groups.

## Testing Strategy
- Happy path: retrying a single failed chunk marks that chunk embedded and completes the document when no failed chunks remain.
- Error path: retrying a non-failed chunk returns a validation error; retry failure leaves the chunk failed and preserves a visible error message.
- Regression scope: existing retry-all, reprocess, chunk edit/delete/create, and document polling flows still work.

## Risks & Mitigation
- Concurrent retries could conflict with document processing; the API rejects documents already in `processing`.
- Failed document detail pages previously hid chunk content; the UI now renders the same chunk list for `error` and `completed` states while gating editing actions to completed documents.
- Rollback: remove the new endpoint/client method and per-chunk controls; existing document-level retry remains intact.
