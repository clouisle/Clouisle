# Knowledge Base Management

This guide covers how to manage knowledge bases as an administrator.

## Overview

As an administrator, you can:

- **View all knowledge bases**: Access KBs across all teams
- **Create knowledge bases**: Set up KBs for teams
- **Manage documents**: Upload, process, and organize documents
- **Monitor indexing**: Track document processing and embeddings
- **Configure search**: Optimize search settings
- **Set limits**: Control storage and document limits
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
- **Status** (Active, Indexing, Error)
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
   - **Embedding Model**: Choose embedding model
   - **Chunking Strategy**: Select chunking method

3. Configure settings:
   - **Chunk Size**: Token count per chunk
   - **Chunk Overlap**: Overlap between chunks
   - **Separator**: Chunk separator
   - **Metadata**: Enable metadata extraction

4. Set permissions:
   - **Visibility**: Private (team only) or Public
   - **Allow sharing**: Enable KB sharing

5. Click **Create Knowledge Base**

### Knowledge Base Configuration

**Basic Settings:**
```yaml
Name: Product Documentation
Description: Complete product documentation and guides
Team: Support Team
Status: Active
Visibility: Private
```

**Embedding Configuration:**
```yaml
Embedding Model: text-embedding-3-small
Dimensions: 1536
Batch Size: 100
```

**Chunking Strategy:**
```yaml
Strategy: Semantic
Chunk Size: 512 tokens
Chunk Overlap: 50 tokens
Min Chunk Size: 100 tokens
Max Chunk Size: 1000 tokens
Separator: "\n\n"
```

**Search Settings:**
```yaml
Default Top K: 5
Score Threshold: 0.7
Rerank: Enabled
Rerank Model: bge-reranker-large
Hybrid Search: Enabled
Keyword Weight: 0.3
```

## Document Management

### Upload Documents

**Single Upload:**
1. Select knowledge base
2. Click **Upload Document**
3. Choose file
4. Enter metadata (optional):
   - Title
   - Category
   - Tags
   - Custom fields
5. Click **Upload**

**Bulk Upload:**
1. Select knowledge base
2. Click **Bulk Upload**
3. Choose multiple files or ZIP
4. Configure batch settings:
   - Default category
   - Default tags
   - Processing priority
5. Click **Upload All**

**Supported Formats:**
- PDF
- DOCX, DOC
- XLSX, XLS
- TXT
- MD (Markdown)
- CSV
- JSON
- HTML
- XML
- PPTX, PPT

### Document Processing

**Processing Pipeline:**
```
Upload → Extract Text → Clean → Chunk → Generate Embeddings → Index
```

**Processing Status:**
- **Pending**: Waiting in queue
- **Processing**: Currently processing
- **Completed**: Successfully indexed
- **Failed**: Processing error
- **Retrying**: Retry after failure

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
1. Select document
2. Click **Reprocess**
3. Choose options:
   - Re-extract text
   - Re-chunk
   - Re-generate embeddings
4. Confirm reprocess

**Bulk Reprocess:**
1. Select multiple documents
2. Click **Bulk Actions** → **Reprocess**
3. Choose reprocess options
4. Confirm bulk reprocess

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

**Overview Metrics:**
- Total documents
- Total size
- Total chunks
- Total embeddings
- Storage used
- Processing queue

**Usage Metrics:**
- Search queries (24h, 7d, 30d)
- Average response time
- Cache hit rate
- Top queries
- Failed queries

### View Statistics

1. Select knowledge base
2. Click **Statistics** tab
3. View metrics:
   - **Documents**: Count, size, status
   - **Search**: Queries, performance
   - **Storage**: Used, available, trend
   - **Processing**: Queue, success rate

4. Filter by date range
5. Export statistics

### Document Analytics

**Per-Document Metrics:**
- View count
- Search appearances
- Average relevance score
- Last accessed
- Access frequency

**View Document Analytics:**
1. Select knowledge base
2. Click **Documents** tab
3. Click **Analytics** column
4. View document metrics

## Search Configuration

### Search Settings

**Vector Search:**
```yaml
Enabled: true
Top K: 5
Score Threshold: 0.7
Distance Metric: Cosine
```

**Keyword Search:**
```yaml
Enabled: true
Analyzer: Standard
Min Score: 0.5
Boost Fields:
  title: 2.0
  content: 1.0
```

**Hybrid Search:**
```yaml
Enabled: true
Vector Weight: 0.7
Keyword Weight: 0.3
Fusion Method: RRF
```

**Reranking:**
```yaml
Enabled: true
Model: bge-reranker-large
Top N: 10
Rerank Top K: 5
```

### Update Search Settings

1. Select knowledge base
2. Click **Settings** → **Search**
3. Configure search options:
   - Vector search
   - Keyword search
   - Hybrid search
   - Reranking
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
   - Filters
5. View results:
   - Matched chunks
   - Relevance scores
   - Source documents
6. Adjust settings if needed

## Embedding Management

### Embedding Models

**Available Models:**
- OpenAI text-embedding-3-small (1536 dims)
- OpenAI text-embedding-3-large (3072 dims)
- OpenAI text-embedding-ada-002 (1536 dims)
- Custom models

**Model Comparison:**
```yaml
text-embedding-3-small:
  Dimensions: 1536
  Cost: $0.02 / 1M tokens
  Performance: Good
  Speed: Fast

text-embedding-3-large:
  Dimensions: 3072
  Cost: $0.13 / 1M tokens
  Performance: Excellent
  Speed: Medium
```

### Change Embedding Model

**Warning:** Changing embedding model requires reindexing all documents.

1. Select knowledge base
2. Click **Settings** → **Embeddings**
3. Choose new embedding model
4. Review impact:
   - Documents to reindex
   - Estimated time
   - Estimated cost
5. Confirm change
6. Monitor reindexing progress

### Reindex Knowledge Base

**Full Reindex:**
1. Select knowledge base
2. Click **Reindex**
3. Choose options:
   - Re-generate embeddings
   - Re-chunk documents
   - Update metadata
4. Confirm reindex
5. Monitor progress

**Reindex Status:**
```yaml
Status: In Progress
Started: 2026-02-11 15:00:00
Progress: 45/120 documents (37.5%)
Estimated Time: 15 minutes
Errors: 0
```

## Storage Management

### Storage Statistics

**Storage Overview:**
```yaml
Total Storage: 10 GB
Used Storage: 6.2 GB (62%)
Available: 3.8 GB (38%)
Document Count: 1,245
Average Document Size: 5.1 MB
```

**Storage by Team:**
```yaml
Support Team: 2.5 GB (40%)
Sales Team: 1.8 GB (29%)
Engineering Team: 1.9 GB (31%)
```

### Storage Limits

**Set Team Limits:**
1. Navigate to **Teams** → Select team
2. Go to **Limits** tab
3. Configure storage limits:
   - Max storage per team
   - Max documents per KB
   - Max document size
   - Max KBs per team

4. Save limits

**Limit Configuration:**
```yaml
Max Storage: 10 GB
Max Documents per KB: 1000
Max Document Size: 100 MB
Max KBs per Team: 10
```

### Storage Cleanup

**Cleanup Options:**
- Delete orphaned chunks
- Remove old versions
- Compress embeddings
- Archive old documents

**Run Cleanup:**
1. Navigate to **Admin** → **Storage**
2. Click **Cleanup**
3. Select cleanup options
4. Review impact
5. Confirm cleanup
6. Monitor progress

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

4. **Check Qdrant:**
   ```bash
   Admin → System → Services
   Check Qdrant status
   View Qdrant logs
   ```

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

4. **Set limits:**
   - Max documents per KB
   - Max embeddings per day
   - Cost alerts

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
   ```bash
   Admin → System → Services
   View Qdrant metrics
   Check resource usage
   ```

4. **Scale Qdrant:**
   - Increase resources
   - Add replicas
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

**Available Actions:**
- Upload documents
- Delete documents
- Reprocess documents
- Update metadata
- Change category
- Add tags
- Export documents

**Perform Bulk Action:**
```bash
1. Select documents (checkbox)
2. Click "Bulk Actions"
3. Choose action
4. Configure options
5. Review changes
6. Confirm execution
```

### Import/Export

**Export Knowledge Base:**
```bash
1. Select knowledge base
2. Click "Export"
3. Choose format:
   - JSON (with embeddings)
   - JSON (without embeddings)
   - CSV (metadata only)
4. Download file
```

**Import Knowledge Base:**
```bash
1. Click "Import"
2. Upload file (JSON)
3. Review KB configuration
4. Map team
5. Choose import options:
   - Import documents
   - Import embeddings
   - Import settings
6. Confirm import
```

## API Access

### Manage Knowledge Bases via API

See [Knowledge Bases API](../../api-reference/endpoints/knowledge-bases.md) for details.

**Common Operations:**
```python
# List all KBs (admin)
kbs = api.get("/api/v1/knowledge-bases", params={"all_teams": True})

# Create KB for team
kb = api.post("/api/v1/knowledge-bases", json={
    "name": "Product Docs",
    "team_id": "team-123",
    "embedding_model": "text-embedding-3-small"
})

# Upload document
with open("document.pdf", "rb") as f:
    doc = api.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
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
