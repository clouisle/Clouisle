# RAG (Retrieval-Augmented Generation) Explained

Understanding how RAG works in Clouisle.

## What is RAG?

RAG combines information retrieval with language model generation to provide accurate, context-aware responses.

## How RAG Works

1. **Retrieve**: Search knowledge base for relevant documents
2. **Augment**: Add retrieved context to the prompt
3. **Generate**: LLM generates response using the context

## RAG Modes in Clouisle

Agents expose three RAG modes (`RAGMode`):

- **Off**: No knowledge base retrieval, even if knowledge bases are configured
- **Auto**: Traditional RAG — relevant chunks are retrieved automatically on every message
- **Agentic**: Agentic RAG — the agent decides when to search based on the conversation

## When to Use RAG

- Answering questions about specific documents
- Providing accurate, sourced information
- Reducing hallucinations
- Grounding responses in facts

---

**Note**: This is a placeholder document. Please update with detailed content.

For more information, see the [main documentation](../README.md).
