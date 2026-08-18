# Searching Documents

This guide explains how to search for documents and information in knowledge bases.

## Overview

Clouisle provides search capabilities:

- **Vector Search**: Semantic similarity search using embeddings
- **Fulltext Search**: Keyword / lexical search
- **Hybrid Search**: Combines vector and fulltext search
- **Document filter**: Narrow results to specific documents

> **Note:** Boolean operators (AND/OR/NOT), wildcards, field search (`title:`), proximity, and fuzzy queries are **not supported** — the query string is used as-is. Search history, saved searches, and result export are **not implemented**.

## Accessing Search

### From a knowledge-base detail page

1. In the platform header, select **Knowledge Base** (`/app/kb`).
2. Open a knowledge base at `/app/kb/{id}`.
3. Select **Search Test**.
4. Enter a query, choose a search mode, and view the results.

## Search Modes

### Vector Search (Semantic)

**What it does:**
- Finds chunks by meaning, not just keywords
- Understands context and intent
- Returns semantically similar content

**Best for:**
- Natural language queries
- Conceptual searches
- Finding related content

**Example queries:**
```
"How do I reset my password?"
→ Finds password reset documentation

"troubleshooting login issues"
→ Finds login help, authentication errors, etc.
```

### Fulltext Search

**What it does:**
- Finds exact keyword matches using the lexical index
- Fast and precise

**Best for:**
- Exact term matching
- Technical terms, product names, IDs

**Example queries:**
```
"API key"
→ Finds documents containing "API key"

"error code 404"
→ Finds documents with "error code 404"
```

> **Note:** The query is matched as a plain text string — boolean operators such as `AND`/`OR`/`NOT` and wildcards are treated as literal characters, not syntax.

### Hybrid Search

**What it does:**
- Combines vector and fulltext search (RRF fusion)
- Best of both worlds
- Default mode

**Example:**
```
Query: "API authentication errors"

Hybrid search finds:
• Documents about API authentication (semantic)
• Documents with the phrase "authentication errors" (fulltext)
```

## Search Interface

### Search Results

**Results view:**
```
┌─────────────────────────────────────────────────────┐
│ 🔍 "password reset"              [Hybrid ▼] [⚙️]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Found 15 results in 0.23s                          │
│                                                     │
│ 📄 Password Management Guide                        │
│    ...instructions for resetting your password...  │
│    Score: 0.95 • Updated: 2026-02-10               │
│    [View]                                          │
│                                                     │
│ 📄 User Authentication                              │
│    ...password reset process and security...       │
│    Score: 0.89 • Updated: 2026-02-08               │
│    [View]                                          │
│                                                     │
│ [Load More Results]                                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Result Information

Each result shows:

| Field | Description |
|-------|-------------|
| **Chunk text** | Relevant excerpt |
| **Score** | Relevance score (0.0-1.0) |
| **Source** | Document name and chunk location |
| **Metadata** | Chunk metadata (page, section, etc.) |

### Relevance Score

**Score interpretation:**
- **0.9-1.0**: Highly relevant
- **0.7-0.9**: Very relevant
- **0.5-0.7**: Moderately relevant
- **<0.5**: Lower relevance

**Note**: The default score threshold is **0.0** — all results are shown unless a threshold is configured. Lower scores mean less relevant results.

## Filters

### Available Filters

| Filter | Description |
|--------|-------------|
| **Document IDs** (`filter_doc_ids`) | Restrict search to specific documents |

> **Note:** Filtering by file type, date, category, language, tags, or author is **not supported**. Document lists are filterable by type and status separately (see [Browsing Knowledge Bases](./browsing-kb.md)).

## Search Configuration

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **search_mode** | `hybrid` | `vector`, `fulltext`, or `hybrid` |
| **top_k** | 5 | Number of results (1-20) |
| **score_threshold** | 0.0 | Minimum dense similarity score |
| **dense_weight** | 1.0 | RRF weight for vector scores (hybrid) |
| **lexical_weight** | 1.0 | RRF weight for fulltext scores (hybrid) |
| **rrf_k** | 60 | RRF rank constant |
| **rerank_enabled** | (KB setting) | Override rerank on/off |
| **rerank_candidate_k** | (KB setting) | Candidate pool size before reranking |
| **rerank_score_threshold** | null | Minimum rerank score (null disables threshold) |
| **filter_doc_ids** | null | Restrict to specific document IDs |

## Batch Search

The batch search endpoint (`POST /api/v1/knowledge-bases/{kb_id}/search/batch`) evaluates **one query against up to 10 independent configurations** at once — useful for comparing retrieval settings side by side.

## Search Tips

### Writing Effective Queries

**✅ Do:**
- Use natural language for semantic search
- Be specific but not too narrow
- Use multiple keywords
- Try different phrasings

**❌ Don't:**
- Use single generic words
- Expect boolean operators or wildcards to work
- Give up after the first try

**Examples:**

**Good queries:**
```
"How to configure SSO authentication"
"Q3 2026 sales performance analysis"
"Troubleshooting API connection errors"
```

**Poor queries:**
```
"help" (too generic)
"api" (too broad)
```

### Refining Results

**If too many results:**
1. Add more specific keywords
2. Raise the score threshold
3. Restrict with `filter_doc_ids`

**If too few results:**
1. Use fewer keywords
2. Lower the score threshold
3. Try synonyms
4. Try hybrid or vector mode

**If no results:**
1. Check spelling
2. Try different keywords
3. Use broader terms
4. Verify documents are processed (status: completed)

## Best Practices

### Search Strategy

**✅ Do:**
- Start with a broad search, then narrow
- Use semantic/hybrid search for concepts
- Use fulltext search for exact terms
- Apply document filters when appropriate

**❌ Don't:**
- Use too many keywords at once
- Ignore search mode
- Forget to check spelling

## Troubleshooting

### No Results Found

**Problem**: Search returns no results

**Solutions:**
1. Check spelling
2. Try different keywords
3. Use broader terms
4. Try hybrid or vector mode
5. Check if documents exist in the KB (status: completed)

### Irrelevant Results

**Problem**: Results don't match the query

**Solutions:**
1. Use more specific keywords
2. Raise the score threshold
3. Try fulltext mode for exact terms

### Slow Search

**Problem**: Search takes too long

**Solutions:**
1. Try fulltext search (faster)
2. Check your internet connection
3. Contact the administrator

### Results Not Updated

**Problem**: New documents don't appear in search

**Solutions:**
1. Wait for processing/indexing to complete
2. Refresh the page
3. Check document status (must be completed)
4. Verify the document is in the selected KB

## Related Documentation

- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Uploading Documents](./uploading-documents.md) - Adding documents
- [Document Management](./document-management.md) - Managing documents

## Getting Help

If you need assistance with searching:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
