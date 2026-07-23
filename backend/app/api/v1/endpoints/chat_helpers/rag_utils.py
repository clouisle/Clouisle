"""Compatibility helpers for chat RAG retrieval and prompt formatting."""

from app.api.v1.endpoints.chat_rag import perform_rag_retrieval as _perform_retrieval
from app.models.agent import Agent


async def perform_rag_retrieval(agent: Agent, query: str) -> list[dict]:
    """Use the canonical AUTO retrieval path with the legacy result keys."""
    results = await _perform_retrieval(agent, query)
    return [
        {
            "knowledge_base_id": result["kb_id"],
            "knowledge_base_name": result["kb_name"],
            "content": result["content"],
            "metadata": result.get("metadata", {}),
            "score": result["score"],
        }
        for result in results
    ]


def aggregate_rag_contexts(rag_contexts: list[dict]) -> list[dict]:
    """Sort and deduplicate RAG contexts by content."""
    sorted_contexts = sorted(rag_contexts, key=lambda item: item["score"], reverse=True)
    unique: dict[str, dict] = {}
    for context in sorted_contexts:
        unique.setdefault(context["content"], context)
    return list(unique.values())


def build_rag_prompt(rag_contexts: list[dict], user_message: str) -> str:
    """Build prompt with RAG contexts."""
    if not rag_contexts:
        return user_message

    context_text = "\n\n".join(
        f"[Knowledge Base: {ctx['knowledge_base_name']}]\n{ctx['content']}"
        for ctx in rag_contexts
    )
    return f"""Based on the following knowledge base contexts, please answer the user's question:

{context_text}

User Question: {user_message}"""
