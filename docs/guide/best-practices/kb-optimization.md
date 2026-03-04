# Knowledge Base Optimization

Optimizing knowledge base performance.

## Chunking Strategies

| Document Type | Chunk Size | Overlap |
|---------------|------------|---------|
| General docs | 500-1000 tokens | 10-20% |
| Q&A | 200-400 tokens | 5-10% |
| Code | 300-600 tokens | 15-25% |

## Search Parameters

- **top_k**: 3-5 for most cases
- **score_threshold**: 0.7-0.8 for quality
- **max_tokens**: 2000-4000 for context

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
