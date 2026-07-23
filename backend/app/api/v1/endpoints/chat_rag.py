"""RAG (Retrieval-Augmented Generation) functions for chat."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.core.config import settings
from app.services.retrieval import RetrievalRequest, RetrievalTarget, retrieve

if TYPE_CHECKING:
    from app.models.agent import Agent

logger = logging.getLogger(__name__)

_REWRITE_HISTORY_MESSAGES = 6
_REWRITE_PROMPT = """Rewrite the latest user question as a standalone knowledge-base search query using only the conversation context below.
Do not answer the question. Do not add facts, names, or constraints absent from the conversation.
Return exactly one JSON object with two string fields: {"query":"...","evidence":"..."}.
The evidence must be an exact non-empty substring copied from the conversation that supplies the missing entity or subject.
The query must be exactly the evidence, one space, then the latest user question unchanged."""
_REFERENTIAL_QUERY = re.compile(
    r"\b(it|its|they|them|their|this|that|these|those|he|she|there|former|latter)\b"
    r"|它|其|他们|她们|这个|那个|这些|那些|上述|前者|后者"
)


ContextualizationStatus = Literal["disabled", "not_needed", "rewritten", "fallback"]


@dataclass(frozen=True)
class ContextualizedQuery:
    query: str
    status: ContextualizationStatus


def should_contextualize_query(query: str) -> bool:
    """Conservatively detect referential follow-ups without a model call."""
    normalized = query.strip()
    return (
        bool(normalized)
        and len(normalized) <= 160
        and bool(_REFERENTIAL_QUERY.search(normalized.lower()))
    )


async def contextualize_retrieval_query(
    agent: "Agent", query: str, history: list[Any] | None
) -> ContextualizedQuery:
    """Best-effort standalone query rewrite for conversational AUTO retrieval."""
    if not settings.RAG_QUERY_CONTEXTUALIZATION_ENABLED:
        return ContextualizedQuery(query, "disabled")
    if not history or not should_contextualize_query(query):
        return ContextualizedQuery(query, "not_needed")
    if not agent.model_id or not agent.team_id:
        return ContextualizedQuery(query, "fallback")

    conversation = [
        {
            "role": str(getattr(message.role, "value", message.role)),
            "content": message.content,
        }
        for message in history
        if getattr(message.role, "value", message.role) in {"user", "assistant"}
        and isinstance(message.content, str)
        and message.content.strip()
    ][-_REWRITE_HISTORY_MESSAGES:]
    if not conversation:
        return ContextualizedQuery(query, "not_needed")

    from app.llm import model_manager
    from app.models.model import TeamModel

    try:
        team_model = (
            await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
        )
        if not team_model:
            return ContextualizedQuery(query, "fallback")
        response = await asyncio.wait_for(
            model_manager.team_chat(
                team_id=str(agent.team_id),
                model_id=str(team_model.model.id),
                messages=[
                    {"role": "system", "content": _REWRITE_PROMPT},
                    *conversation,
                    {"role": "user", "content": query},
                ],
            ),
            timeout=settings.RAG_QUERY_CONTEXTUALIZATION_TIMEOUT_SECONDS,
        )
        payload = json.loads(response.content or "")
        if set(payload) != {"query", "evidence"}:
            return ContextualizedQuery(query, "fallback")
        rewritten = payload["query"]
        evidence = payload["evidence"]
        history_text = "\n".join(message["content"] for message in conversation)
        if (
            not isinstance(rewritten, str)
            or not rewritten.strip()
            or not isinstance(evidence, str)
            or not evidence.strip()
            or evidence not in history_text
            or rewritten.strip() != f"{evidence} {query}"
        ):
            return ContextualizedQuery(query, "fallback")
        return ContextualizedQuery(rewritten.strip(), "rewritten")
    except Exception:
        logger.warning("RAG query contextualization failed")
        return ContextualizedQuery(query, "fallback")


async def perform_rag_retrieval(
    agent: "Agent", query: str, history: list[Any] | None = None
) -> list[dict[str, Any]]:
    """Perform RAG retrieval from knowledge bases.

    Args:
        agent: The agent with knowledge base associations
        query: Search query string

    Returns:
        List of retrieval results with kb_id, kb_name, document_id, document_name, content, score
    """
    from app.models.agent import AgentKnowledgeBase

    kb_associations = await AgentKnowledgeBase.filter(
        agent_id=agent.id
    ).prefetch_related("knowledge_base")
    targets = tuple(
        RetrievalTarget(
            kb_id=association.knowledge_base.id,
            kb_name=association.knowledge_base.name,
            team_id=association.knowledge_base.team_id,
            status=association.knowledge_base.status,
            embedding_model_id=association.knowledge_base.embedding_model_id,
            rerank_model_id=association.knowledge_base.rerank_model_id,
            search_mode=association.search_mode,
            top_k=association.retrieval_top_k,
            score_threshold=association.score_threshold,
        )
        for association in kb_associations
    )
    if not targets:
        return []

    contextualized = await contextualize_retrieval_query(agent, query, history)
    logger.info(
        "RAG query contextualization status=%s",
        contextualized.status,
    )
    try:
        response = await retrieve(
            RetrievalRequest(
                query=contextualized.query,
                targets=targets,
                top_k=max(target.top_k or 1 for target in targets),
            )
        )
    except Exception:
        logger.warning("RAG retrieval failed")
        return []

    return [
        {
            "kb_id": result["kb_id"],
            "kb_name": result["kb_name"],
            "document_id": str(result.get("document_id")),
            "document_name": result.get("document_name"),
            "content": result.get("content"),
            "score": result.get("score"),
        }
        for result in response.results
    ]


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
