"""Replay mode for fast parameter sweep evaluation.

Replay mode exploits the mathematical fact that fusion and truncation are pure functions
of channel recall results. Instead of running full retrieval for each config, we:
1. Deep probe each channel once at max depth
2. Cache rerank scores for the union of all candidates
3. Replay each config by: prefix truncate → apply thresholds → fuse → rerank from cache → truncate

This reduces 20 queries × 17 configs = 340 retrievals to 20 deep probes + 20 rerank batches.
"""

import copy
from typing import Any

from app.services.retrieval import _weighted_rrf


class ChannelCache:
    """Cached channel recall results for one query."""

    def __init__(
        self,
        dense_results: list[dict[str, Any]],
        lexical_results: list[dict[str, Any]],
    ):
        """Initialize channel cache.

        Args:
            dense_results: Dense recall results with chunk_id, score, rank
            lexical_results: Lexical recall results with chunk_id, score, rank
        """
        self.dense_results = dense_results
        self.lexical_results = lexical_results

    def deep_copy(self) -> "ChannelCache":
        """Return deep copy to prevent cache pollution."""
        return ChannelCache(
            copy.deepcopy(self.dense_results),
            copy.deepcopy(self.lexical_results),
        )


class RerankCache:
    """Cached rerank scores for (query, chunk_id) pairs."""

    def __init__(self):
        self._cache: dict[tuple[str, str], float] = {}

    def put(self, query: str, chunk_id: str, score: float) -> None:
        """Store rerank score."""
        self._cache[(query, chunk_id)] = score

    def get(self, query: str, chunk_id: str) -> float | None:
        """Retrieve rerank score."""
        return self._cache.get((query, chunk_id))

    def batch_put(self, query: str, scores: dict[str, float]) -> None:
        """Store multiple rerank scores for one query."""
        for chunk_id, score in scores.items():
            self.put(query, chunk_id, score)


async def probe_channels(
    query: str,
    kb_id: str,
    depth: int,
    retrieval_service: Any,
) -> ChannelCache:
    """Deep probe both channels at max depth with no thresholds.

    Args:
        query: Query text
        kb_id: Knowledge base ID
        depth: Max depth to probe (typically max of all candidate top_k/candidate_k)
        retrieval_service: KnowledgeRetrievalService instance

    Returns:
        ChannelCache with deep recall results
    """
    # Probe dense channel
    dense_results = await retrieval_service._dense_recall(
        query=query,
        kb_ids=[kb_id],
        k=depth,
        score_threshold=0.0,  # No threshold for deep probe
    )

    # Probe lexical channel
    lexical_results = await retrieval_service._lexical_recall(
        query=query,
        kb_ids=[kb_id],
        k=depth,
    )

    return ChannelCache(dense_results, lexical_results)


def replay_config(
    cache: ChannelCache,
    config: dict[str, Any],
    query: str,
    rerank_cache: RerankCache | None,
    metric_k: int,
) -> list[dict[str, Any]]:
    """Replay one config from cached channel results.

    Args:
        cache: ChannelCache from deep probe
        config: Config dict with search_mode, dense_weight, lexical_weight, rrf_k, etc.
        query: Query text (for rerank cache lookup)
        rerank_cache: Optional rerank score cache
        metric_k: Truncation depth for metrics

    Returns:
        Replayed results list (chunk_id, scores, ranks)
    """
    # Deep copy to prevent cache pollution
    cache_copy = cache.deep_copy()

    search_mode = config.get("search_mode", "hybrid")
    top_k = config.get("top_k", metric_k)
    score_threshold = config.get("score_threshold", 0.0)
    dense_weight = config.get("dense_weight", 1.0)
    lexical_weight = config.get("lexical_weight", 1.0)
    rrf_k = config.get("rrf_k", 60)
    rerank_enabled = config.get("rerank_enabled", False)
    rerank_candidate_k = config.get("rerank_candidate_k", 20)
    rerank_score_threshold = config.get("rerank_score_threshold")

    # Prefix truncate to effective depth
    effective_depth = max(top_k, rerank_candidate_k if rerank_enabled else 0)
    dense_truncated = cache_copy.dense_results[:effective_depth]
    lexical_truncated = cache_copy.lexical_results[:effective_depth]

    # Apply dense score threshold
    if score_threshold > 0:
        dense_truncated = [
            r for r in dense_truncated if r.get("dense_score", 0) >= score_threshold
        ]

    # Fusion based on search_mode
    if search_mode == "vector":
        fused = dense_truncated[:top_k]
    elif search_mode == "fulltext":
        fused = lexical_truncated[:top_k]
    else:  # hybrid
        fused = _weighted_rrf(
            dense_results=dense_truncated,
            lexical_results=lexical_truncated,
            dense_weight=dense_weight,
            lexical_weight=lexical_weight,
            k=rrf_k,
        )
        fused = fused[: rerank_candidate_k if rerank_enabled else top_k]

    # Rerank from cache
    if rerank_enabled and rerank_cache:
        for result in fused:
            chunk_id = result["chunk_id"]
            cached_score = rerank_cache.get(query, chunk_id)
            if cached_score is not None:
                result["rerank_score"] = cached_score
                result["rerank_rank"] = None  # Will be assigned after sort

        # Sort by rerank score
        fused_with_rerank = [r for r in fused if "rerank_score" in r]
        fused_with_rerank.sort(key=lambda x: x["rerank_score"], reverse=True)

        # Assign rerank ranks
        for idx, result in enumerate(fused_with_rerank, start=1):
            result["rerank_rank"] = idx
            result["final_score_stage"] = "rerank"

        # Apply rerank score threshold
        if rerank_score_threshold is not None:
            fused_with_rerank = [
                r
                for r in fused_with_rerank
                if r.get("rerank_score", 0) >= rerank_score_threshold
            ]

        fused = fused_with_rerank[:top_k]

    # Final truncation to metric_k for metrics calculation
    return fused[:metric_k]


async def build_rerank_cache(
    query: str,
    candidate_chunks: list[str],
    rerank_service: Any,
) -> RerankCache:
    """Build rerank cache for candidate union.

    Args:
        query: Query text
        candidate_chunks: List of chunk IDs to rerank
        rerank_service: Rerank service instance

    Returns:
        RerankCache with scores for all candidates
    """
    cache = RerankCache()

    if not candidate_chunks:
        return cache

    # Call rerank service once for all candidates
    rerank_results = await rerank_service.rerank(
        query=query,
        chunks=candidate_chunks,
    )

    # Populate cache
    for result in rerank_results:
        chunk_id = result["chunk_id"]
        score = result["rerank_score"]
        cache.put(query, chunk_id, score)

    return cache
