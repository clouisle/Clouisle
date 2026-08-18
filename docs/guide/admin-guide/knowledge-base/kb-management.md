# Knowledge Base Management

This guide covers how to manage knowledge bases as an administrator.

## Overview

As an administrator, you can:

- **View all knowledge bases**: Access KBs across all teams
- **Create knowledge bases**: Set up KBs for teams
- **Manage documents**: Upload, process, and organize documents
- **Monitor indexing**: Track document processing and embeddings
- **Configure search**: Optimize search settings
- **Troubleshoot**: Debug indexing and search issues

## Accessing Knowledge Base Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Knowledge Bases**
3. View KB management interface

### Knowledge Base List View

The KB list shows:

- **KB name and description**
- **Team ownership**
- **Document count**
- **Total size**
- **Embedding model**
- **Status** (`active`, `processing`, `error`, or `archived`)
- **Last updated**
- **Created date**

**Filters:**
- Team
- Status
- Embedding model
- Date range

**Search:**
- Search by KB name or description

## Creating Knowledge Bases

### Create Knowledge Base for Team

1. Click **Create Knowledge Base** button
2. Fill in KB details:
   - **Name**: KB display name
   - **Description**: KB purpose and content
   - **Team**: Select team owner
   - **Embedding Model**: Choose a team-authorized embedding model, or rely on the configured default; `embedding_model_id` cannot be changed after creation
   - **Rerank Model**: Choose rerank model (optional)

3. Configure settings:
   - **Chunk Size**: Characters per chunk (default 1000)
   - **Chunk Overlap**: Overlap between chunks (default 100)
   - **Separator**: Custom chunk separator (optional)
   - **Rerank**: Enable reranking for retrieval
   - **Search Mode**: `vector`, `fulltext`, or `hybrid` (default `hybrid`)

4. Click **Create Knowledge Base**

### Knowledge Base Configuration

**Basic Settings:**
```yaml
Name: Product Documentation
Description: Complete product documentation and guides
Team: Support Team
Status: active
```

**Embedding Configuration:**
```yaml
Embedding Model: text-embedding-3-small (TeamModel of type embedding)
Rerank Model: bge-reranker-large (optional)
```

**Chunking Strategy:**
```yaml
Chunk Size: 1000 characters
Chunk Overlap: 100 characters
Separator: "\n\n"
```

**Search Settings:**
```yaml
Default Search Mode: hybrid   # vector, fulltext, or hybrid
Top K: 5
Score Threshold: 0.0
Rerank: Enabled
Dense Weight: 1.0
Lexical Weight: 1.0
RRF K: 60
```

## Document Management

### Upload Documents

**Single Upload:**
1. Select knowledge base
2. Click **Upload Document**
3. Choose one or more supported files
4. Click **Upload**

Documents are uploaded via `POST /api/v1/knowledge-bases/{kb_id}/documents/upload` (multipart). Upload creates each document with status `pending`; it does **not** start extraction or embedding automatically.

After upload, select a pending document and click **Configure** to open the preview/editor. Review or adjust chunk settings, click **Preview Chunks**, then click **Process** to start extraction, chunking, embedding, and indexing. **Quick Process** starts processing with the current/default settings. URL imports also open the preview/editor after import.

**Bulk Actions:** Select documents in the table to run **Quick Process** for pending documents, **Retry Failed Chunks** for error documents, or **Delete** for selected documents. There is no ZIP/multi-file upload; files are uploaded individually.

**Supported Formats:**
- PDF
- DOCX, DOC
- XLSX, XLS
- TXT
- MD, Markdown
- CSV
- JSON
- HTML
- PPTX

### Document Processing

**Processing Pipeline:**
```
Upload → Extract Text → Clean → Chunk → Generate Embeddings → Index
```

**Processing Status:**
- **Pending**: Uploaded and waiting for an administrator to start processing
- **Processing**: Currently extracting, chunking, embedding, or indexing
- **Completed**: Successfully indexed
- **Error**: Processing error; inspect the error message and retry or reprocess

**View Processing Status:**
1. Select knowledge base
2. Click **Documents** tab
3. View document list with status
4. Click document for details

**Processing Details:**
```yaml
Document: product-guide.pdf
Status: Completed
Uploaded: 2026-02-11 14:30:00
Started: 2026-02-11 14:30:05
Completed: 2026-02-11 14:31:20
Duration: 75 seconds

Processing Steps:
  - Text Extraction: 5s (Success)
  - Text Cleaning: 2s (Success)
  - Chunking: 3s (Success, 45 chunks)
  - Embedding Generation: 60s (Success)
  - Indexing: 5s (Success)

Statistics:
  Pages: 120
  Characters: 245,680
  Chunks: 45
  Embeddings: 45
  Size: 2.4 MB
```

### Reprocess Documents

**Reprocess Single Document:**
1. Select a completed or error document
2. Click **Reprocess** to open the preview/editor
3. Review or change chunk settings and click **Preview Chunks**
4. Click **Process** to reprocess and regenerate embeddings

**Retry Failed Chunks:**
1. Select an error document
2. Click **Retry Failed Chunks**
3. Confirm or monitor the processing status

Bulk reprocessing is not a separate action. Use the selection toolbar for bulk quick processing of pending documents or bulk retry of failed chunks.

### Delete Documents

**Delete Single Document:**
1. Select document
2. Click **Delete**
3. Confirm deletion

**Bulk Delete:**
1. Select multiple documents
2. Click **Bulk Actions** → **Delete**
3. Confirm bulk deletion

## Monitoring and Statistics

### Knowledge Base Statistics

`GET /api/v1/knowledge-bases/{kb_id}/stats` returns per-KB statistics, including:

- Total documents
- Total chunks
- Total embeddings
- Processing status counts
- Embedding configuration and dimension

### View Statistics

1. Select knowledge base
2. Click **Statistics** tab
3. View metrics

> **Note:** Not implemented / Roadmap: search-query analytics (queries, response times, cache hit rate, top queries), storage usage trends, and statistics export are not available.

### Document Analytics

> **Note:** Not implemented / Roadmap. There is no per-document analytics (view count, search appearances, relevance scores, access frequency).

## Search Configuration

### Search Settings

Retrieval is configured per KB via the KB settings:

**Search Mode:**
```yaml
Search Mode: hybrid   # vector, fulltext, or hybrid
Top K: 5
Score Threshold: 0.0
```

**Hybrid Search:**
```yaml
Dense Weight: 1.0     # dense RRF weight
Lexical Weight: 1.0   # lexical RRF weight
RRF K: 60
```

**Reranking:**
```yaml
Rerank Enabled: true
Rerank Score Threshold: (optional)
```

### Update Search Settings

1. Select knowledge base
2. Click **Settings** → **Search**
3. Configure search options:
   - Search mode (`vector`, `fulltext`, `hybrid`)
   - Top K and score threshold
   - Dense/lexical weights and RRF K for hybrid fusion
   - Reranking toggle
4. Test search
5. Click **Save Changes**

### Test Search

**Test Search Query:**
1. Select knowledge base
2. Click **Test Search**
3. Enter query
4. Configure search parameters:
   - Search mode
   - Top K
5. View results:
   - Matched chunks
   - Relevance scores
   - Source documents
6. Adjust settings if needed

## Embedding Management

### Embedding Models

Embedding models are regular platform models with `model_type = embedding` (for example OpenAI `text-embedding-3-small` or compatible local models), granted to teams via model authorization. A KB references one embedding model (`embedding_model_id`) and optionally a rerank model (`rerank_model_id`).

### Embedding Model Lock

The embedding model is fixed when the knowledge base is created because stored vectors depend on that model. The admin edit form does not allow changing `embedding_model_id` after creation; attempting to update it is rejected. To use another embedding model, create a new knowledge base and process its documents with the new model.

### Reprocess Documents Through the API

Documents are (re)processed through document endpoints rather than a single KB-level “reindex” action:

- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/process` — process a pending document
- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/process-with-chunks` — process with supplied chunk settings
- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/reprocess` — reprocess a document
- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/rechunk` — re-chunk a document
- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/retry-failed-chunks` — retry failed chunk embeddings
- `POST /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks/{chunk_id}/retry-embedding` — retry a single chunk

## Storage Management

> **Note:** Not implemented / Roadmap. There is no storage dashboard, per-team storage limits, or storage cleanup for knowledge bases. The only storage-related configuration is the maximum upload size (`kb_document_max_upload_size_mb`) in **Site Settings** → **Storage**.

## Troubleshooting

### Document Processing Failed

**Symptoms:**
- Document status is "Failed"
- Error message in logs

**Solutions:**

1. **Check document format:**
   - Verify file is not corrupted
   - Check file size
   - Ensure format is supported

2. **Check processing logs:**
   ```bash
   Admin → Knowledge Bases → Select KB
   Documents → Select document
   View processing logs
   ```

3. **Common errors:**
   - **Text extraction failed**: File corrupted or unsupported format
   - **Chunking failed**: Invalid chunk settings
   - **Embedding failed**: API key invalid or rate limit
   - **Indexing failed**: Qdrant connection issue

4. **Retry processing:**
   ```bash
   Select failed document
   Click "Retry"
   Optionally adjust settings
   Confirm retry
   ```

### Search Not Working

**Symptoms:**
- Search returns no results
- Relevant documents not found
- Search errors

**Solutions:**

1. **Check indexing status:**
   - Verify documents are indexed
   - Check for indexing errors

2. **Test search:**
   ```bash
   Admin → Knowledge Bases → Select KB
   Click "Test Search"
   Enter query
   View results and scores
   ```

3. **Check search settings:**
   - Verify score threshold not too high
   - Check top K value
   - Test different search modes

4. **Check the vector store:**
   - Verify the Qdrant service is healthy and reachable
   - Check Qdrant logs

5. **Reindex if needed:**
   ```bash
   Select knowledge base
   Click "Reindex"
   Monitor progress
   ```

### High Embedding Costs

**Symptoms:**
- Unexpected high costs
- Cost alerts triggered

**Solutions:**

1. **Review usage:**
   ```bash
   Admin → Knowledge Bases → Statistics
   View embedding usage
   Identify high-usage KBs
   ```

2. **Optimize chunking:**
   - Increase chunk size
   - Reduce overlap
   - Filter unnecessary content

3. **Use cheaper models:**
   - Switch to text-embedding-3-small
   - Reduce dimensions if possible

4. **Review usage:**
   - Check KB statistics for embedding counts
   - Remove or reprocess unnecessary documents

> **Note:** Not implemented / Roadmap: per-KB document limits, daily embedding quotas, and cost alerts are not available.

### Slow Search Performance

**Symptoms:**
- Search takes too long
- Timeouts

**Solutions:**

1. **Check metrics:**
   ```bash
   Admin → Knowledge Bases → Statistics
   View search performance
   Identify slow queries
   ```

2. **Optimize search:**
   - Reduce top K
   - Disable reranking for simple queries
   - Enable caching
   - Use filters

3. **Check Qdrant performance:**
   - Review Qdrant resource usage (CPU/memory) and indexes
   - Check Qdrant metrics and logs

4. **Scale Qdrant:**
   - Increase resources or add replicas at the infrastructure level
   - Optimize indexes

## Best Practices

### Document Management

**✅ Do:**
- Organize documents with categories and tags
- Use descriptive document names
- Add metadata for better search
- Remove outdated documents
- Monitor processing status
- Test search after uploads
- Backup important documents

**❌ Don't:**
- Upload duplicate documents
- Use unclear file names
- Skip metadata
- Keep outdated content
- Ignore processing errors
- Forget to test search
- Delete without backup

### Chunking Strategy

**✅ Do:**
- Choose appropriate chunk size for content type
- Use semantic chunking for narrative content
- Use fixed chunking for structured data
- Test different strategies
- Monitor chunk quality
- Adjust based on search performance

**❌ Don't:**
- Use same strategy for all content
- Make chunks too small or too large
- Ignore chunk overlap
- Skip testing
- Forget to optimize

### Search Optimization

**✅ Do:**
- Use hybrid search for best results
- Enable reranking for accuracy
- Set appropriate score thresholds
- Monitor search performance
- Collect user feedback
- Iterate based on metrics

**❌ Don't:**
- Rely only on vector search
- Set threshold too high
- Ignore performance metrics
- Skip user feedback
- Forget to optimize

## Bulk Operations

### Bulk Actions

The Documents table supports selection-based actions:

- **Quick Process** selected documents whose status is `pending`.
- **Retry Failed Chunks** selected documents whose status is `error`.
- **Delete** selected documents.

There is no ZIP/multi-file bulk upload or bulk metadata update. Upload files individually, then use the preview/editor or the selection toolbar to process them.

### Import/Export

> **Note:** Not implemented / Roadmap. There is no knowledge base import/export (JSON/CSV, with or without embeddings).

## API Access

### Manage Knowledge Bases via API

See [Knowledge Bases API](../../api-reference/endpoints/knowledge-bases.md) for details.

**Common Operations:**
```python
# List KBs — filters: team_id, search, status, own_only (no all_teams parameter)
kbs = api.get("/api/v1/knowledge-bases", params={"team_id": "team-123"})

# Create KB for team
kb = api.post("/api/v1/knowledge-bases", json={
    "name": "Product Docs",
    "team_id": "team-123",
    "embedding_model_id": "model-456",
    "settings": {"chunk_size": 1000, "chunk_overlap": 100, "search_mode": "hybrid"}
})

# Upload document
with open("document.pdf", "rb") as f:
    doc = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/upload",
        files={"file": f}
    )

# Search KB
results = api.post(f"/api/v1/knowledge-bases/{kb_id}/search", json={
    "query": "How to reset password?",
    "top_k": 5
})
```

## Related Documentation

- [Knowledge Bases API](../../api-reference/endpoints/knowledge-bases.md) - API reference
- [Uploading Documents](../../user-guide/knowledge-base/uploading-documents.md) - User guide
- [Searching](../../user-guide/knowledge-base/searching.md) - User guide
- [Team Management](../teams/team-management.md) - Team admin

---

**Last Updated**: 2026-02-11
