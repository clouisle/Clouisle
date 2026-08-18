# Vector Embeddings

Understanding vector embeddings and similarity search.

## What are Embeddings?

Embeddings are numerical representations of text that capture semantic meaning. Clouisle uses the configured embedding model to encode both document chunks and search queries; similarity is meaningful only when both use the same model family and vector dimension.

## How Similarity Search Works

1. Extract and character-split a document.
2. Convert each chunk to a vector and persist it with chunk metadata.
3. Convert a query with the same embedding configuration.
4. Search the matching Qdrant collection and combine results with the optional `pg_search` lexical leg when using hybrid retrieval.

## Embedding Models

- The model registry supplies enabled embedding models, including OpenAI-compatible endpoints and configured providers.
- The model ID is configurable; `text-embedding-ada-002` is only an example, not a required default.
- A knowledge base records `embedding_dimension` on first processing. Qdrant collections use the configured prefix and dimension (for example, `<prefix>_1536`).
- A later document whose vector dimension differs from the KB dimension is rejected. Changing the embedding model after KB creation is rejected; explicitly reprocess/rechunk into a compatible KB or create a replacement KB.

## Chunking

Clouisle splits documents with LangChain's character-based `RecursiveCharacterTextSplitter`:

- `chunk_size` defaults to **1000 characters** (configurable per knowledge base)
- `chunk_overlap` defaults to **100 characters**
- The UI accepts chunk sizes from 100 to 2000 characters
- Recursive separators prioritize paragraphs, newlines, sentence punctuation, words, then individual characters
- Custom separators can be configured per knowledge base

There is no semantic/ML-based chunking; splitting is deterministic and character-level.

See [RAG Explained](./rag-explained.md) for the complete retrieval pipeline and [Knowledge Base Optimization](../best-practices/kb-optimization.md) for tuning guidance.
