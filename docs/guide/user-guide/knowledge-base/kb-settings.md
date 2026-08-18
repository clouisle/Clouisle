# Knowledge Base Settings

This guide explains how to configure knowledge base settings for optimal performance and accuracy.

## Overview

Knowledge base settings control how documents are processed, indexed, and retrieved. Proper configuration ensures accurate search results and efficient RAG (Retrieval-Augmented Generation).

## Accessing Settings

1. In the platform header, select **Knowledge Base** (`/app/kb`).
2. Select a knowledge base to open `/app/kb/{id}`.
3. Open the knowledge-base settings/edit action.

## General Settings

### Basic Information

**Name:**
- Knowledge base display name (max 100 chars)
- Must be unique within the team

**Description:**
- Optional description (max 500 chars)

**Icon:**
- Optional icon name or emoji (max 50 chars)

**Status:** `active`, `processing`, `error`, or `archived`. A KB is `active` by default.

> **Note:** Knowledge bases belong to a team and are visible to that team's members. There is no per-KB public visibility setting.

## Embedding Settings

### Embedding Model

The embedding model used to vectorize document chunks. Available models are the ones configured by your administrator and authorized for your team. `embedding_model_id` is set on the KB; the embedding dimension is recorded after the first document is processed.

### Rerank Model

An optional rerank model (`rerank_model_id`) can be configured to re-score retrieval results.

## Chunking Settings

Documents are split into chunks for embedding and retrieval:

```yaml
Chunk Size: 1000
Chunk Overlap: 100
Separator: (optional custom separator)
```

**Chunk Size:**
- Default: 1000 characters (min 100)
- Larger chunks = more context per retrieval, less precise
- Smaller chunks = more precise retrieval, may lose context

**Chunk Overlap:**
- Default: 100 characters (0 = no overlap)
- Prevents information loss at boundaries

**Separator:**
- Optional custom text separator used as a hard split boundary

## Search Settings

### Search Mode

- **vector**: Semantic (dense) search only
- **fulltext**: Keyword / lexical search only
- **hybrid**: Combines vector and fulltext via RRF (default)

### Top K

- Default: 5 results (range 1-20 for search requests)

### Score Threshold

- Default: **0.0** (no filtering)
- Raise it to require higher minimum similarity

### Reranking

- `rerank_enabled` (default true) enables re-scoring results with the rerank model
- `rerank_candidate_k`: candidate pool size before reranking (default 10)
- `rerank_score_threshold`: optional minimum rerank score

### Weight Tuning (hybrid)

- `dense_weight` and `lexical_weight` control the RRF contribution of vector vs fulltext scores
- `rrf_k`: RRF rank constant (default 60)

## Document Processing

### Supported Formats

Documents: PDF, DOCX, DOC, TXT, MD, HTML, CSV, XLSX, XLS, JSON, plus web pages added by URL.

> **Note:** OCR for scanned documents/images and archive auto-extraction (ZIP/TAR/GZ) are **not implemented**. Upload only text-extractable files, and process the document after upload.

### Processing Flow

1. Upload (or add by URL) → document status `pending`
2. Start **Process** from the document action/editor → text extraction → chunking → embedding → `completed`
3. Failures leave the document in `error` status with an error message

## RAG Settings

RAG behavior is configured per **agent**, not per knowledge base. An agent's RAG mode is one of:

- **off**: No retrieval, even if knowledge bases are configured
- **auto**: Traditional RAG — automatically retrieve on every message
- **agentic**: Agentic RAG — the agent decides when to search (default)

Per-KB retrieval parameters for agents: `retrieval_top_k` (default 5), `score_threshold` (default 0.3), `search_mode` (vector/fulltext/hybrid).

## Best Practices

### Chunking

**✅ Do:**
- Start with the defaults (1000 / 100)
- Test different chunk sizes against your content
- Monitor chunk quality

**❌ Don't:**
- Use very small chunks (< 300)
- Use very large chunks (> 2000) unless necessary
- Skip overlap entirely

### Search

**✅ Do:**
- Use hybrid search for general queries
- Enable reranking for better relevance
- Retrieve 3-5 results for RAG

**❌ Don't:**
- Set the score threshold too high
- Retrieve too many results

## Troubleshooting

### Poor Search Results

**Problem:** Search returns irrelevant results

**Solutions:**
1. Increase the score threshold
2. Enable reranking
3. Reduce top K
4. Check chunk quality
5. Review document content

### Slow Processing

**Problem:** Document processing is slow

**Solutions:**
1. Check document size
2. Reduce chunk count by using larger chunks
3. Check the embedding/rerank model status

### Missing Context

**Problem:** Retrieved chunks lack context

**Solutions:**
1. Increase chunk size
2. Increase overlap
3. Review chunk boundaries

## Related Documentation

- [Uploading Documents](./uploading-documents.md) - Upload documents
- [Document Metadata](./document-metadata.md) - Metadata configuration
- [Agent Configuration](../agents/agent-configuration.md) - RAG setup

---

**Last Updated**: 2026-02-11
