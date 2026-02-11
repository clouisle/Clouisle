# Knowledge Base Settings

This guide explains how to configure knowledge base settings for optimal performance and accuracy.

## Overview

Knowledge base settings control how documents are processed, indexed, and retrieved. Proper configuration ensures accurate search results and efficient RAG (Retrieval-Augmented Generation).

## Accessing Settings

1. Navigate to **Knowledge Bases**
2. Select a knowledge base
3. Click **Settings** tab

## General Settings

### Basic Information

**Name:**
- Knowledge base display name
- Must be unique within team
- 3-100 characters

**Description:**
- Optional description
- Helps team members understand purpose
- Supports markdown formatting

**Visibility:**
- **Private**: Only team members can access
- **Team**: All team members can access
- **Public**: Anyone with link can access (if enabled)

**Status:**
- **Active**: Available for use
- **Inactive**: Temporarily disabled
- **Archived**: Read-only, no new documents

## Embedding Settings

### Embedding Model

Choose the model for generating document embeddings:

**Available Models:**
- `text-embedding-3-large` (Recommended)
  - Dimensions: 3072
  - Best accuracy
  - Higher cost

- `text-embedding-3-small`
  - Dimensions: 1536
  - Good balance
  - Lower cost

- `text-embedding-ada-002`
  - Dimensions: 1536
  - Legacy model
  - Lowest cost

**Considerations:**
- Cannot change after documents are indexed
- Higher dimensions = better accuracy but more storage
- Choose based on accuracy needs and budget

### Embedding Dimensions

**Custom Dimensions:**
- Reduce dimensions to save storage
- Trade-off: Lower accuracy
- Range: 256-3072 (for text-embedding-3-large)

**Example:**
```
Model: text-embedding-3-large
Dimensions: 1536 (reduced from 3072)
Storage savings: ~50%
Accuracy impact: Minimal for most use cases
```

## Chunking Settings

### Chunking Strategy

**Fixed Size:**
- Split by character count
- Simple and predictable
- Good for uniform content

**Semantic:**
- Split by meaning/context
- Better for varied content
- Preserves context

**Sentence:**
- Split by sentences
- Natural boundaries
- Good for Q&A

**Page:**
- Split by pages (PDF only)
- Preserves page structure
- Good for references

### Chunk Size

**Recommended Sizes:**
- **Small (500-800)**: Short, focused chunks
  - Best for: Q&A, specific facts
  - Pros: Precise retrieval
  - Cons: May lose context

- **Medium (1000-1500)**: Balanced chunks (Recommended)
  - Best for: General use
  - Pros: Good balance
  - Cons: None

- **Large (2000-3000)**: Long, contextual chunks
  - Best for: Complex topics
  - Pros: More context
  - Cons: Less precise

**Configuration:**
```yaml
Chunk Size: 1000
Chunk Overlap: 200
Strategy: Semantic
```

### Chunk Overlap

**Purpose:**
- Prevents information loss at boundaries
- Ensures context continuity

**Recommended Values:**
- 10-20% of chunk size
- Example: 200 for chunk size 1000

**Trade-offs:**
- Higher overlap = More context, more storage
- Lower overlap = Less storage, potential gaps

## Search Settings

### Search Algorithm

**Vector Search:**
- Semantic similarity
- Best for meaning-based queries
- Default and recommended

**Hybrid Search:**
- Vector + keyword search
- Best for specific terms
- Higher accuracy, slower

**Keyword Search:**
- Traditional text search
- Best for exact matches
- Fastest, less accurate

### Similarity Threshold

**Score Range:** 0.0 - 1.0

**Recommended Thresholds:**
- **Strict (0.8-1.0)**: Only very similar results
  - Use for: Critical information
  - Trade-off: May miss relevant results

- **Balanced (0.7-0.8)**: Good similarity (Recommended)
  - Use for: General use
  - Trade-off: Good balance

- **Relaxed (0.5-0.7)**: Broader results
  - Use for: Exploratory search
  - Trade-off: May include less relevant results

**Configuration:**
```yaml
Similarity Threshold: 0.7
Top K Results: 5
Rerank: Enabled
```

### Top K Results

**Number of results to retrieve:**
- Range: 1-20
- Default: 5
- Recommended: 3-5 for RAG

**Considerations:**
- More results = More context for LLM
- Too many = Noise and higher cost
- Balance based on use case

### Reranking

**Purpose:**
- Improve result relevance
- Reorder results by relevance

**Options:**
- **Disabled**: Use vector scores only
- **LLM-based**: Use LLM to rerank (Recommended)
- **Cross-encoder**: Use specialized model

**Configuration:**
```yaml
Reranking: LLM-based
Rerank Model: gpt-4-turbo
Rerank Top K: 10 (retrieve 10, return top 5)
```

## Document Processing

### Supported Formats

**Documents:**
- PDF, DOCX, DOC, TXT, MD
- XLSX, XLS, CSV
- PPTX, PPT
- HTML, HTM

**Images:**
- JPG, PNG, GIF (with OCR)
- SVG (text extraction)

**Archives:**
- ZIP, TAR, GZ (auto-extract)

### OCR Settings

**Enable OCR:**
- Extract text from images
- Process scanned PDFs
- Higher processing time

**OCR Language:**
- English (default)
- Chinese
- Multi-language

**Configuration:**
```yaml
OCR Enabled: true
OCR Language: English
OCR Quality: High
```

### Metadata Extraction

**Auto-extract metadata:**
- Title, author, date
- File properties
- Custom fields

**Metadata Fields:**
- `title`: Document title
- `author`: Document author
- `created_at`: Creation date
- `category`: Document category
- `tags`: Document tags
- Custom fields

**Configuration:**
```yaml
Extract Metadata: true
Custom Fields:
  - department
  - version
  - status
```

## RAG Settings

### RAG Mode

**Disabled:**
- No knowledge base retrieval
- Agent uses only training data

**Citation (before_llm):**
- Retrieve before LLM call
- Include sources in context
- LLM can cite sources

**Rewrite (after_llm):**
- LLM generates response first
- Verify with knowledge base
- Rewrite if needed

**Configuration:**
```yaml
RAG Mode: Citation
Include Sources: true
Max Sources: 3
```

### Context Window

**Max Context Length:**
- Maximum tokens for retrieved content
- Range: 500-8000
- Default: 2000

**Considerations:**
- Larger = More context, higher cost
- Smaller = Less context, lower cost
- Balance based on model limits

### Source Attribution

**Include Sources:**
- Show source documents
- Enable citations
- Improve transparency

**Source Format:**
```json
{
  "content": "Retrieved content",
  "source": "document.pdf",
  "page": 5,
  "score": 0.85,
  "metadata": {
    "title": "Product Manual",
    "version": "2.0"
  }
}
```

## Access Control

### Permissions

**Team Roles:**
- **Owner**: Full access
- **Admin**: Manage settings, documents
- **Member**: View, search
- **Viewer**: View only

**Document-Level:**
- Restrict by metadata
- Filter by user role
- Custom access rules

**Configuration:**
```yaml
Access Control: Enabled
Default Role: Member
Restrict By:
  - department
  - security_level
```

### API Access

**API Keys:**
- Generate API keys for programmatic access
- Set scopes (read, write, delete)
- Monitor usage

**Rate Limits:**
- Per API key
- Per team
- Custom limits

## Performance Settings

### Indexing

**Batch Size:**
- Documents per batch
- Range: 10-100
- Default: 50

**Parallel Processing:**
- Number of parallel workers
- Range: 1-10
- Default: 4

**Configuration:**
```yaml
Batch Size: 50
Parallel Workers: 4
Auto Index: true
```

### Caching

**Enable Caching:**
- Cache search results
- Reduce latency
- Lower costs

**Cache TTL:**
- Time to live (seconds)
- Range: 60-3600
- Default: 300 (5 minutes)

**Configuration:**
```yaml
Cache Enabled: true
Cache TTL: 300
Cache Size: 1000 entries
```

## Monitoring

### Usage Statistics

**Track:**
- Total documents
- Total chunks
- Storage used
- Search queries
- API calls

**View Statistics:**
1. Go to **Settings** → **Statistics**
2. View usage charts
3. Export reports

### Alerts

**Configure Alerts:**
- Storage limit reached
- Processing errors
- High latency
- API rate limits

**Notification Channels:**
- Email
- Webhook
- Slack integration

## Best Practices

### Chunking

**✅ Do:**
- Use semantic chunking for varied content
- Set appropriate chunk size (1000-1500)
- Use 10-20% overlap
- Test different strategies
- Monitor chunk quality

**❌ Don't:**
- Use very small chunks (< 500)
- Use very large chunks (> 3000)
- Skip overlap
- Use same settings for all content
- Ignore chunk boundaries

### Search

**✅ Do:**
- Use balanced similarity threshold (0.7-0.8)
- Enable reranking
- Retrieve 3-5 results for RAG
- Monitor search quality
- Adjust based on feedback

**❌ Don't:**
- Set threshold too high (> 0.9)
- Retrieve too many results (> 10)
- Skip reranking
- Ignore search metrics
- Use same settings for all queries

### Performance

**✅ Do:**
- Enable caching
- Use appropriate batch sizes
- Monitor processing time
- Optimize chunk size
- Use parallel processing

**❌ Don't:**
- Disable caching
- Use very small batches
- Ignore performance metrics
- Use oversized chunks
- Process sequentially

## Configuration Examples

### High Accuracy Configuration

```yaml
# Best for critical information
Embedding Model: text-embedding-3-large
Dimensions: 3072
Chunk Size: 1000
Chunk Overlap: 200
Strategy: Semantic
Similarity Threshold: 0.8
Top K: 5
Reranking: LLM-based
RAG Mode: Citation
```

### Balanced Configuration (Recommended)

```yaml
# Good balance of accuracy and cost
Embedding Model: text-embedding-3-large
Dimensions: 1536
Chunk Size: 1200
Chunk Overlap: 200
Strategy: Semantic
Similarity Threshold: 0.7
Top K: 5
Reranking: LLM-based
RAG Mode: Citation
```

### Cost-Optimized Configuration

```yaml
# Lower cost, acceptable accuracy
Embedding Model: text-embedding-3-small
Dimensions: 1536
Chunk Size: 1500
Chunk Overlap: 150
Strategy: Fixed
Similarity Threshold: 0.65
Top K: 3
Reranking: Disabled
RAG Mode: Citation
```

### Large Document Configuration

```yaml
# For long, complex documents
Embedding Model: text-embedding-3-large
Dimensions: 1536
Chunk Size: 2000
Chunk Overlap: 400
Strategy: Semantic
Similarity Threshold: 0.7
Top K: 5
Reranking: LLM-based
RAG Mode: Citation
```

## Troubleshooting

### Poor Search Results

**Problem:** Search returns irrelevant results

**Solutions:**
1. Increase similarity threshold
2. Enable reranking
3. Reduce top K
4. Check chunk quality
5. Review document content

### Slow Processing

**Problem:** Document processing is slow

**Solutions:**
1. Reduce batch size
2. Increase parallel workers
3. Optimize chunk size
4. Check document size
5. Review OCR settings

### High Costs

**Problem:** Embedding costs are high

**Solutions:**
1. Use smaller embedding model
2. Reduce dimensions
3. Increase chunk size
4. Enable caching
5. Optimize document count

### Missing Context

**Problem:** Retrieved chunks lack context

**Solutions:**
1. Increase chunk size
2. Increase overlap
3. Use semantic chunking
4. Review chunk boundaries
5. Adjust top K

## Related Documentation

- [Knowledge Base Management](../../admin-guide/knowledge-base/kb-management.md) - Admin guide
- [Document Upload](./document-upload.md) - Upload documents
- [Document Metadata](./document-metadata.md) - Metadata configuration
- [RAG Configuration](../agents/rag-configuration.md) - RAG setup

---

**Last Updated**: 2026-02-11
