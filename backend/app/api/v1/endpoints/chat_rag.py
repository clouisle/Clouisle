"""RAG (Retrieval-Augmented Generation) functions for chat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import Agent

logger = logging.getLogger(__name__)


async def perform_rag_retrieval(agent: "Agent", query: str) -> list[dict[str, Any]]:
    """Perform RAG retrieval from knowledge bases.

    Args:
        agent: The agent with knowledge base associations
        query: Search query string

    Returns:
        List of retrieval results with kb_id, kb_name, document_id, document_name, content, score
    """
    from app.models.agent import AgentKnowledgeBase
    from app.services.vector_store import VectorStore

    rag_contexts: list[dict[str, Any]] = []

    # Get knowledge base associations
    kb_associations = await AgentKnowledgeBase.filter(
        agent_id=agent.id
    ).prefetch_related("knowledge_base")

    for akb in kb_associations:
        kb = akb.knowledge_base

        # Skip if KB has no embedding model
        if not kb.embedding_model_id:
            continue

        try:
            vector_store = VectorStore(
                embedding_model_id=str(kb.embedding_model_id),
                rerank_model_id=str(kb.rerank_model_id) if kb.rerank_model_id else None,
                team_id=str(kb.team_id),
            )

            results = await vector_store.search(
                kb_id=kb.id,
                query=query,
                search_mode=akb.search_mode,
                top_k=akb.retrieval_top_k,
                score_threshold=akb.score_threshold,
            )

            for result in results:
                rag_contexts.append(
                    {
                        "kb_id": str(kb.id),
                        "kb_name": kb.name,
                        "document_id": str(result.get("document_id")),
                        "document_name": result.get("document_name"),
                        "content": result.get("content"),
                        "score": result.get("score"),
                    }
                )
        except Exception as e:
            logger.warning(f"RAG retrieval failed for KB {kb.id}: {e}")

    return rag_contexts


def aggregate_rag_contexts(rag_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate RAG contexts by document to align citations with document-level sources.

    Args:
        rag_contexts: List of retrieval results

    Returns:
        Aggregated list where each entry represents a unique document
    """
    if not rag_contexts:
        return []

    aggregated: list[dict[str, Any]] = []
    index_map: dict[tuple[str | None, str | None], int] = {}

    for ctx in rag_contexts:
        kb_id = ctx.get("kb_id")
        doc_id = ctx.get("document_id") or ctx.get("document_name")
        key = (kb_id, doc_id)

        if key in index_map:
            idx = index_map[key]
            if ctx.get("content"):
                aggregated[idx]["content_parts"].append(ctx.get("content"))
            score = ctx.get("score")
            if isinstance(score, (int, float)):
                existing_score = aggregated[idx].get("score")
                current_score = (
                    float(existing_score)
                    if isinstance(existing_score, (int, float))
                    else 0.0
                )
                aggregated[idx]["score"] = max(current_score, float(score))
            continue

        index_map[key] = len(aggregated)
        aggregated.append(
            {
                "kb_id": kb_id,
                "kb_name": ctx.get("kb_name"),
                "document_id": ctx.get("document_id"),
                "document_name": ctx.get("document_name"),
                "score": ctx.get("score"),
                "content_parts": [ctx.get("content")] if ctx.get("content") else [],
            }
        )

    for item in aggregated:
        item["content"] = "\n\n".join([p for p in item.get("content_parts", []) if p])
        item.pop("content_parts", None)

    return aggregated


def build_rag_prompt(rag_contexts: list[dict[str, Any]], user_message: str) -> str:
    """Build user message with RAG context and citation instructions.

    Args:
        rag_contexts: List of aggregated retrieval results
        user_message: Original user message

    Returns:
        Enhanced prompt with RAG context and citation format instructions
    """
    if not rag_contexts:
        return user_message

    rag_contexts = aggregate_rag_contexts(rag_contexts)

    # Build numbered references
    references = []
    for i, ctx in enumerate(rag_contexts, 1):
        references.append(
            f"[[ref:{i}]] {ctx['kb_name']} - {ctx['document_name']}:\n{ctx['content']}"
        )

    context_text = "\n\n---\n\n".join(references)

    return f"""The following reference materials may help you answer the user's question.
Use them ONLY if they are relevant to the question.

Citation format requirement:
- Use ONLY [[cite:N]] where N is the reference number.
- Do NOT use (ref:N), [ref:N], "ref:N", or any other citation format.
Only cite sources you actually use. Do not cite if the information comes from your general knowledge.

Reference Materials:

{context_text}

---

User question: {user_message}

Remember: Only use [[cite:N]] citations when you actually use information from the references above."""
