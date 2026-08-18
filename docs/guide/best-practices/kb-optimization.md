# Knowledge Base Optimization

Optimizing knowledge base performance.

## Chunking Strategies

Clouisle uses character-based chunking. The defaults are `chunk_size = 1000` characters and `chunk_overlap = 100` characters; the UI accepts chunk sizes from 100 to 2000 characters. These are starting points, not per-document-type presets.

| Starting point | Chunk size | Overlap |
|----------------|------------|---------|
| General prose | 1000 characters | 100 characters |
| Short Q&A | 400-800 characters | 50-100 characters |
| Code or structured text | 800-1500 characters | 100-200 characters |

Tune against representative documents and retrieval quality; these values are recommendations rather than hard defaults.

## Search Parameters

The retrieval API uses `top_k`, `score_threshold`, and (for hybrid search) dense/lexical weights and `rrf_k`. Defaults are `top_k = 5` and `score_threshold = 0.0`; there is no KB search `max_tokens` parameter. Context length is governed by the chat model's available token budget.

- **top_k**: Start with 3-5 and increase only when recall is insufficient
- **score_threshold**: Start at 0.0, then raise it using a representative evaluation set
- **search_mode**: Compare `vector`, `fulltext`, and `hybrid` for the corpus
- **reranking**: Enable only with an authorized rerank model; tune candidate count and threshold using measured quality/latency

## When to Reprocess

- Document content changed
- Chunking settings or separators changed
- A document needs explicit reprocessing/rechunking

Changing the embedding model on an existing KB is rejected because its dimension must remain compatible. Create a replacement KB or use an explicit migration/reprocessing process; the application does not silently auto-reindex the KB.

## Evaluation

Keep a small set of representative queries and record recall, answer quality, latency, and cost before changing settings. Compare retrieval modes and reranking with the same queries rather than relying on a single example.
