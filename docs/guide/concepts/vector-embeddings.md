# Vector Embeddings

Understanding vector embeddings and similarity search.

## What are Embeddings?

Embeddings are numerical representations of text that capture semantic meaning.

## How Similarity Search Works

1. Convert query to vector
2. Search for similar vectors in database
3. Return most similar documents

## Embedding Models

- OpenAI `text-embedding-ada-002` (configurable model ID)
- Custom OpenAI-compatible embedding endpoints
- Other providers registered in the model registry (e.g. Azure OpenAI, Google, DeepSeek, Ollama) that expose embedding models

## Chunking

Clouisle splits documents with LangChain's character-based `RecursiveCharacterTextSplitter`:

- `chunk_size` defaults to **1000 characters** (configurable per knowledge base)
- `chunk_overlap` defaults to **100 characters**
- Recursive separators in priority order: paragraphs, newlines, Chinese/English sentence punctuation, words, then individual characters
- Custom separators can be configured per knowledge base

There is no semantic/ML-based chunking; splitting is deterministic and character-level.

---

**Status**: This is a framework document. Content will be expanded based on the comprehensive research completed by the documentation agents.

For immediate needs, refer to:
- [Deployment Guide](../deployment/DEPLOYMENT.md)
- [SSO Configuration](../admin-guide/settings/SSO.md)
- [Tools Guide](../admin-guide/tools/TOOLS.md)
- [Permissions System](../admin-guide/permissions/PERMISSIONS.md)
