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

## Team Sharing

A knowledge base can be shared with other teams as **read-only**:

1. Open **Knowledge Base** (`/app/kb`) and choose **Share** from a KB card's **⋯** menu. The action is only shown for KBs your team owns and only to team Owners/Admins.
2. In the **Share** dialog, select the target team. The permission level is fixed to **Read Only** — the receiving team can view, retrieve, and associate the KB with its agents, but cannot edit it.
3. Click **Share**. The dialog's **Shared With** list shows the current shares, and each can be revoked.

Effects and rules:

- Sharing requires the team Owner/Admin role on the KB's own team; private KBs cannot be shared.
- On the KB list, a KB your team owns that others use shows a **"Shared with N teams"** badge; a KB shared to your team shows a **"From {team}"** badge.
- A shared KB appears in the receiving team's `/app/kb` list, can be searched and used by its agents, and is read-only: its settings, documents, and upload/edit actions are disabled.

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

Documents: PDF, DOCX, DOC, TXT, MD, HTML, CSV, XLSX, XLS, JSON, PNG, JPG/JPEG, GIF, WEBP, plus web pages added by URL.

ZIP/TAR/GZ archive auto-extraction is not supported.

### Image understanding

Image understanding is an optional administrator-managed feature and is **off by default**. To use it, an administrator must enable it and select a vision-capable chat model that is enabled and authorized for the relevant team. Users cannot enable or select this model from the knowledge-base settings.

When enabled, document processing can send image content to the configured model provider to extract readable text and describe visual content. This external processing may incur model-provider charges and may send document image data outside your Clouisle deployment. Follow your organization's data-handling rules before processing sensitive content.

For PDFs with both selectable text and image content, image understanding may send a whole page to the vision model. The page's extracted text can overlap with its existing text layer, and duplicate content may remain; complete deduplication is not guaranteed.

External image fetching is controlled separately and **disabled by default**. It only applies when image understanding is enabled; image URLs are not fetched for analysis unless an administrator explicitly enables external image access.

The feature applies to documents processed after it is enabled and configured. **Existing documents are not automatically reprocessed**; reprocess them manually to apply image understanding.

### Processing Flow

1. Upload (or add by URL) → document status `pending`
2. Start **Process** from the document action/editor → text and, when configured, image understanding → chunking → embedding → `completed`
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

**Last Updated**: 2026-10-30
