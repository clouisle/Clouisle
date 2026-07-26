"""LLM-based relevance label suggestions for retrieval evaluation datasets.

This service provides pre-labeling suggestions to speed up dataset authoring.
Suggestions are NEVER automatically applied - they require explicit human confirmation.
The feature is disabled by default (RETRIEVAL_EVAL_LLM_LABELING_ENABLED=False).
"""

import asyncio
from typing import Literal

from app.core.config import settings

LabelSource = Literal["human", "llm_suggested", "llm_confirmed", "imported"]


async def suggest_label(
    query: str,
    chunk_text: str,
    kb,  # KnowledgeBase
    user,  # User
    timeout: int | None = None,
) -> int | None:
    """Request an LLM relevance grade suggestion for a (query, chunk) pair.

    Args:
        query: User's search query
        chunk_text: Text content of the chunk to evaluate
        kb: Knowledge base context
        user: User requesting the suggestion
        timeout: Max seconds to wait (default: RETRIEVAL_EVAL_LLM_LABELING_TIMEOUT)

    Returns:
        Suggested grade (0-3), or None if disabled, timed out, or failed.
        Failures are silent - they never block the labeling workflow.
    """
    if not settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED:
        return None

    # For now, return None since this is a placeholder implementation
    # In a full implementation, this would:
    # 1. Get KB's default LLM model
    # 2. Send a prompt asking for 0-3 grade
    # 3. Parse the response
    # 4. Handle timeouts and errors silently
    return None


async def suggest_labels_batch(
    query: str,
    chunks: list[tuple[str, str]],  # [(chunk_id, chunk_text), ...]
    kb,  # KnowledgeBase
    user,  # User
) -> dict[str, int]:
    """Request LLM suggestions for multiple chunks in parallel.

    Args:
        query: User's search query
        chunks: List of (chunk_id, chunk_text) tuples
        kb: Knowledge base context
        user: User requesting suggestions

    Returns:
        Dict mapping chunk_id to suggested grade (0-3).
        Missing entries indicate timeouts or failures.
    """
    if not settings.RETRIEVAL_EVAL_LLM_LABELING_ENABLED:
        return {}

    # Run suggestions in parallel with individual timeouts
    tasks = [suggest_label(query, text, kb, user) for _, text in chunks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Map successful results back to chunk IDs
    suggestions = {}
    for (chunk_id, _), result in zip(chunks, results):
        if isinstance(result, int):
            suggestions[chunk_id] = result

    return suggestions
