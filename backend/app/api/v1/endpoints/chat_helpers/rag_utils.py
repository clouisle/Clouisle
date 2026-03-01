"""
RAG (Retrieval-Augmented Generation) utilities for chat.
"""

from app.models.agent import Agent, KnowledgeBase
from app.services.vector_store import vector_store_service


async def perform_rag_retrieval(agent: Agent, query: str) -> list[dict]:
    """Perform RAG retrieval for the given query."""
    if not agent.knowledge_base_ids:
        return []

    all_contexts = []

    for kb_id in agent.knowledge_base_ids:
        kb = await KnowledgeBase.get_or_none(id=kb_id)
        if not kb or not kb.is_active:
            continue

        # Retrieve relevant documents from vector store
        results = await vector_store_service.search(
            collection_name=kb.collection_name,
            query=query,
            top_k=kb.top_k or 5,
            score_threshold=kb.score_threshold or 0.7,
        )

        for result in results:
            all_contexts.append(
                {
                    "knowledge_base_id": kb_id,
                    "knowledge_base_name": kb.name,
                    "content": result["content"],
                    "metadata": result.get("metadata", {}),
                    "score": result["score"],
                }
            )

    return all_contexts


def aggregate_rag_contexts(rag_contexts: list[dict]) -> list[dict]:
    """Aggregate and deduplicate RAG contexts."""
    # Sort by score (descending)
    sorted_contexts = sorted(rag_contexts, key=lambda x: x["score"], reverse=True)

    # Deduplicate by content
    seen_contents = set()
    unique_contexts = []

    for context in sorted_contexts:
        content = context["content"]
        if content not in seen_contents:
            seen_contents.add(content)
            unique_contexts.append(context)

    return unique_contexts


def build_rag_prompt(rag_contexts: list[dict], user_message: str) -> str:
    """Build prompt with RAG contexts."""
    if not rag_contexts:
        return user_message

    context_text = "\n\n".join(
        [
            f"[Knowledge Base: {ctx['knowledge_base_name']}]\n{ctx['content']}"
            for ctx in rag_contexts
        ]
    )

    return f"""Based on the following knowledge base contexts, please answer the user's question:

{context_text}

User Question: {user_message}"""
