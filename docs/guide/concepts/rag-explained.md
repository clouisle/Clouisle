# RAG (Retrieval-Augmented Generation) Explained

Understanding how RAG works in Clouisle.

## What is RAG?

RAG combines retrieval with language-model generation. Clouisle retrieves completed knowledge-base chunks, adds them to the model context, and generates an answer grounded in those chunks.

## Deep-Dive Retrieval & Ingestion Pipeline

```
┌───────────────────────────┐     ┌────────────────────────────────────────────────────────┐
│ Uploaded Documents        │ ──► │ MarkItDown Multi-Format Parser                         │
│ (PDF, DOCX, XLSX, HTML...)│     │ • Base64 Embedded Media Extraction -> Asset Storage    │
└───────────────────────────┘     │ • Structure Flattening & XSS Sanitization (Bleach)     │
                                  └────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │ Two-Stage CJK-Aware Chunking Engine                    │
                                  │ • Hard Boundary Split on Decoded Escapes (\n\n, \n)    │
                                  │ • Zero-Overlap Recursive Splitting + Trailing Overlap  │
                                  └────────────────────────────────────────────────────────┘
                                                              │
                                     ┌────────────────────────┴────────────────────────┐
                                     ▼                                                 ▼
                      ┌──────────────────────────────┐                 ┌──────────────────────────────┐
                      │ PostgreSQL 17 + pg_search    │                 │ Qdrant Vector Engine         │
                      │ • BM25 Tantivy Lexical Index │                 │ • Dense Embeddings (kb_dim_N)│
                      └──────────────────────────────┘                 └──────────────────────────────┘
                                     │                                                 │
                                     └────────────────────────┬────────────────────────┘
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │ Weighted Reciprocal Rank Fusion (RRF, k=60)            │
                                  │ • Channel Fault-Tolerance & Shared Vector Cache        │
                                  └────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │ Optional Neural Reranker (Cross-Encoder Scoring)       │
                                  └────────────────────────────────────────────────────────┘
                                                              │
                                                              ▼
                                  ┌────────────────────────────────────────────────────────┐
                                  │ Context Assembly & Token Budget Guard                  │
                                  │ • Adjacent Chunk Window Expansion (opt-in, default off) │
                                  │ • Per-Document Chunk Throttling & Token Truncation     │
                                  └────────────────────────────────────────────────────────┘
```

### 1. Document Ingestion & Sanitization
- **Universal Format Parsing**: Uses `MarkItDown` to parse PDF, DOCX, PPTX, XLSX, HTML, CSV, TXT, MD, and JSON.
- **Embedded Media Deconstruction (`replace_embedded_media_data_uris`)**: Automatically scans for base64 inline image data URIs in documents, extracts the binary payloads to dedicated storage (`/knowledge-bases/{kb_id}/documents/{doc_id}/media/{filename}`), and replaces them with clean URLs. This prevents massive token bloat and vector distortion.
- **Tabular & JSON Normalization**: CSV tables are converted into formatted Markdown pipes; JSON trees are recursively flattened using dot-notation keys.
- **XSS & Prompt Injection Sanitization**: All extracted text is sanitized through `bleach.clean(text, tags=[], attributes={}, strip=True)` to strip dangerous markup before vectorization.

### 2. CJK-Aware Chunking Implementation
- **Hard Split Boundary Pre-splitting**: User-defined separators (e.g. `\n\n`, `\n`) are decoded from escape strings into real control bytes via `_decode_separator_escapes` and applied as primary hard boundaries before recursive splitting.
- **Zero-Overlap Recursive Splitting + Exact Prepend**: Standard LangChain overlap can inflate text volume unpredictably with CJK characters. Clouisle splits chunks with zero internal overlap using a punctuation hierarchy (`\n\n`, `\n`, `。`, `！`, `？`, `. `, `! `, `? `, `；`, `，`, ` `), then prepends exact character-level trailing slices from preceding chunks (`_split_on_custom_separator`), guaranteeing deterministic token boundaries.

### 3. Dual-Engine Hybrid Retrieval & Weighted RRF

Clouisle executes parallel retrieval across two independent search engines:
1. **Lexical Retrieval**: Powered by PostgreSQL `pg_search` (BM25 Tantivy full-text index).
2. **Dense Vector Retrieval**: Powered by Qdrant (cosine/dot-product similarity over vector collections partitioned as `kb_dim_{dimension}`).

**Weighted Reciprocal Rank Fusion (RRF) Formula:**

$$\text{Score}(d) = \sum_{c \in \{\text{dense}, \text{lexical}\}} \frac{w_c}{k_{\text{RRF}} + \text{rank}_c(d)}$$

- **Parameters**: Default `rrf_k = 60`, `dense_weight = 1.0`, `lexical_weight = 1.0`.
- **Channel Fault Tolerance**: If one engine suffers a temporary network or indexing glitch, Clouisle seamlessly falls back to single-channel recall without throwing user-facing 500 errors.
- **Shared Vector Embeddings**: In multi-KB search contexts, `_RetrievalContext` deduplicates query embedding calls across knowledge bases sharing the same embedding model.

### 4. Optional Cross-Encoder Reranking

When `rerank_enabled = true`:
- The top `rerank_candidate_k` chunks from RRF (default 10; configurable per knowledge base and overridable per search) are fed into a neural Cross-Encoder reranker.
- Chunks are rescored based on deep semantic query-document alignment and filtered by `rerank_score_threshold`.

### 5. Context Assembly & Window Expansion

- **Adjacent Chunk Window Expansion (`expand_adjacent`, opt-in, default off)**: When the retrieval request sets `expand_adjacent = true`, the engine fetches adjacent sibling chunks (`chunk_index - 1`, `chunk_index + 1`) to reconstruct coherent paragraphs and restore fragmented context. The flag is not part of the public search request schema and no built-in caller enables it today.
- **Token Budget & Per-Document Throttling**: Context assembly adheres strictly to `context_token_budget`, capping the total token count and applying `max_chunks_per_document` to prevent single long files from starving other search results.
## Embedding compatibility

A knowledge base records its embedding dimension when the first document is processed. All later documents and queries must use a compatible dimension; Qdrant collection names are partitioned by configured prefix and dimension. Changing the embedding model is rejected after KB creation, so use an explicit reprocess/rechunk flow or create a replacement KB rather than assuming automatic re-indexing.

## When to use RAG

- Questions about specific documents
- Answers that should be grounded in team knowledge
- Retrieval experiments comparing vector, lexical, and hybrid modes

Related tuning guidance is in [Knowledge Base Optimization](../best-practices/kb-optimization.md).

## Related documentation

- [Multi-tenancy model](./multi-tenancy.md) - Team-scoped authorization
- [Vector embeddings](./vector-embeddings.md) - Embedding and collection compatibility
- [Agent vs Workflow](./agent-vs-workflow.md) - Choosing the interaction model
