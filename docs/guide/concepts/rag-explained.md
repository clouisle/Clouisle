# RAG (Retrieval-Augmented Generation) Explained

Understanding how RAG works in Clouisle.

## What is RAG?

RAG combines retrieval with language-model generation. Clouisle retrieves completed knowledge-base chunks, adds them to the model context, and generates an answer grounded in those chunks.

## Retrieval pipeline

1. **Prepare**: MarkItDown extracts text; the knowledge-base splitter creates deterministic character-based chunks.
2. **Index**: Each chunk is stored with metadata in PostgreSQL and its embedding is stored in a Qdrant collection. PostgreSQL `pg_search` provides the lexical index.
3. **Recall**: A query can use `vector`, `fulltext`, or `hybrid` search. Hybrid retrieval combines dense and lexical candidates; an optional authorized rerank model can reorder the candidate pool.
4. **Augment**: The selected chunks are formatted as knowledge-base context for the agent.
5. **Generate**: The configured LLM produces the response; retrieval and generation are separate stages.

The retrieval mode is independent from the agent's RAG mode. `off`, `auto`, and `agentic` control whether and when the agent invokes retrieval, while `vector`, `fulltext`, and `hybrid` control how a knowledge base searches.

## RAG Modes in Clouisle

Agents expose three RAG modes (`RAGMode`):

- **Off**: No knowledge-base retrieval, even if knowledge bases are configured.
- **Auto**: Retrieve relevant chunks automatically for each message.
- **Agentic**: Let the agent decide when to search based on the conversation.

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
