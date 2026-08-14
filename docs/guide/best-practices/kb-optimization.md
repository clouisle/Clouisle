# Knowledge Base Optimization

Optimizing knowledge base performance.

## Chunking Strategies

> **Note:** The presets below are recommendations, not hard defaults. Clouisle chunks by characters with a default `chunk_size` of 1000 and `chunk_overlap` of 100; there is no built-in per-document-type preset table.

| Document Type | Chunk Size | Overlap |
|---------------|------------|---------|
| General docs | 500-1000 tokens | 10-20% |
| Q&A | 200-400 tokens | 5-10% |
| Code | 300-600 tokens | 15-25% |

## Search Parameters

> **Note:** The values below are recommendations, not hard defaults. The implementation defaults to `top_k = 5` and `score_threshold = 0.0`; context length is governed by a token budget rather than a fixed `max_tokens`.

- **top_k**: 3-5 for most cases (recommended)
- **score_threshold**: 0.7-0.8 for quality (recommended)
- **max_tokens**: 2000-4000 for context (recommended; actual limits follow the configured token budget)

## When to Re-index

- Document content changed
- Chunking strategy updated
- Embedding model changed

---

**Status**: This is a framework document. Content will be expanded based on the comprehensive research completed by the documentation agents.

For immediate needs, refer to:
- [Deployment Guide](../deployment/DEPLOYMENT.md)
- [SSO Configuration](../admin-guide/settings/SSO.md)
- [Tools Guide](../admin-guide/tools/TOOLS.md)
- [Permissions System](../admin-guide/permissions/PERMISSIONS.md)
