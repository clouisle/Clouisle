"""Unified retrieval orchestration for already-authorized knowledge bases."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.models.knowledge_base import KnowledgeBaseStatus
from app.services.lexical_store import LexicalStore, SearchHit
from app.services.vector_store import VectorStore

SearchMode = Literal["vector", "fulltext", "hybrid"]
_VALID_MODES = {"vector", "fulltext", "hybrid"}
_MAX_CONCURRENCY = 8


class RetrievalError(RuntimeError):
    """Raised when a retrieval request cannot produce results."""

    def __init__(
        self, message: str, diagnostics: tuple[RetrievalDiagnostic, ...]
    ) -> None:
        self.diagnostics = diagnostics
        super().__init__(message)


@dataclass(frozen=True)
class RetrievalTarget:
    """An already-authorized knowledge base and its allowed document scope."""

    kb_id: UUID
    kb_name: str
    team_id: UUID
    status: str
    embedding_model_id: UUID | None = None
    rerank_model_id: UUID | None = None
    embedding_dimension: int | None = None
    search_mode: SearchMode | None = None
    top_k: int | None = None
    score_threshold: float | None = None
    allowed_document_ids: frozenset[UUID] | None = None
    document_ids: frozenset[UUID] | None = None

    def __post_init__(self) -> None:
        if (
            self.document_ids is not None
            and self.allowed_document_ids is not None
            and not self.document_ids <= self.allowed_document_ids
        ):
            raise ValueError("document_ids must be within allowed_document_ids")
        if self.search_mode is not None and self.search_mode not in _VALID_MODES:
            raise ValueError(f"unsupported search mode: {self.search_mode}")
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be positive")


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    targets: tuple[RetrievalTarget, ...]
    search_mode: SearchMode = "hybrid"
    top_k: int = 5
    score_threshold: float = 0.0
    timeout_seconds: float = 30.0
    rerank_overrides: dict[str, Any] | None = None
    dense_weight: float = 1.0
    lexical_weight: float = 1.0
    rrf_k: int = 60

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.search_mode not in _VALID_MODES:
            raise ValueError(f"unsupported search mode: {self.search_mode}")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.dense_weight < 0 or self.lexical_weight < 0:
            raise ValueError("retrieval weights must be nonnegative")
        if (
            any(
                (target.search_mode or self.search_mode) == "hybrid"
                for target in self.targets
            )
            and self.dense_weight == 0
            and self.lexical_weight == 0
        ):
            raise ValueError(
                "at least one retrieval weight must be positive in hybrid mode"
            )
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")


@dataclass(frozen=True)
class RetrievalDiagnostic:
    kb_id: UUID
    code: Literal["inactive", "missing_embedding_model", "timeout", "failed"]
    detail: str | None = None


@dataclass(frozen=True)
class RetrievalResponse:
    results: tuple[dict[str, Any], ...]
    diagnostics: tuple[RetrievalDiagnostic, ...]


def _result_order(result: dict[str, Any], score_field: str) -> tuple[Any, ...]:
    return (
        -float(result.get(score_field) or 0),
        str(result.get("document_id") or ""),
        str(result.get("chunk_id") or ""),
    )


def _lexical_results(hits: list[SearchHit]) -> list[dict[str, Any]]:
    results = [
        {
            **hit.source,
            "chunk_id": hit.chunk_id,
            "score": hit.score,
            "lexical_score": hit.score,
            "search_type": "fulltext",
            "final_score_stage": "lexical",
        }
        for hit in hits
    ]
    results.sort(key=lambda result: _result_order(result, "lexical_score"))
    for rank, result in enumerate(results, 1):
        result["lexical_rank"] = rank
    return results


def _dense_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        {
            **result,
            "dense_score": result.get("dense_score", result.get("score", 0.0)),
            "search_type": "vector",
            "final_score_stage": "dense",
        }
        for result in results
    ]
    normalized.sort(key=lambda result: _result_order(result, "dense_score"))
    for rank, result in enumerate(normalized, 1):
        result["dense_rank"] = rank
    return normalized


def _weighted_rrf(
    dense: list[dict[str, Any]],
    lexical: list[dict[str, Any]],
    *,
    dense_weight: float,
    lexical_weight: float,
    k: int,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for channel, weight, rank_field in (
        (dense, dense_weight, "dense_rank"),
        (lexical, lexical_weight, "lexical_rank"),
    ):
        if weight == 0:
            continue
        for result in channel:
            chunk_id = str(result.get("chunk_id") or "")
            current = merged.setdefault(chunk_id, {})
            current.update(result)
            current["fusion_score"] = current.get("fusion_score", 0.0) + weight / (
                k + int(result[rank_field])
            )

    results = list(merged.values())
    results.sort(key=lambda result: _result_order(result, "fusion_score"))
    for rank, result in enumerate(results, 1):
        result["score"] = result["fusion_score"]
        result["fusion_rank"] = rank
        result["search_type"] = "hybrid"
        result["final_score_stage"] = "fusion"
    return results


async def retrieve(request: RetrievalRequest) -> RetrievalResponse:
    """Search targets concurrently, then rank and truncate results globally."""
    semaphore = asyncio.Semaphore(min(_MAX_CONCURRENCY, max(1, len(request.targets))))

    async def search_target(
        target: RetrievalTarget,
    ) -> tuple[list[dict[str, Any]], RetrievalDiagnostic | None]:
        search_mode = target.search_mode or request.search_mode
        top_k = target.top_k or request.top_k
        score_threshold = (
            target.score_threshold
            if target.score_threshold is not None
            else request.score_threshold
        )
        if target.status != KnowledgeBaseStatus.ACTIVE.value:
            return [], RetrievalDiagnostic(target.kb_id, "inactive")
        if search_mode == "vector" and not target.embedding_model_id:
            return [], RetrievalDiagnostic(target.kb_id, "missing_embedding_model")

        document_scope = (
            target.document_ids
            if target.document_ids is not None
            else target.allowed_document_ids
        )
        if document_scope is not None and not document_scope:
            return [], None
        document_ids = (
            sorted(document_scope, key=str) if document_scope is not None else None
        )

        async def dense_search() -> list[dict[str, Any]]:
            return _dense_results(
                await VectorStore(
                    embedding_model_id=(
                        str(target.embedding_model_id)
                        if target.embedding_model_id
                        else None
                    ),
                    rerank_model_id=(
                        str(target.rerank_model_id) if target.rerank_model_id else None
                    ),
                    team_id=str(target.team_id),
                ).search(
                    kb_id=target.kb_id,
                    query=request.query,
                    search_mode="vector",
                    top_k=top_k,
                    score_threshold=score_threshold,
                    filter_doc_ids=document_ids,
                    embedding_dimension=target.embedding_dimension,
                    rerank_overrides={"rerank_enabled": False},
                )
            )

        async def lexical_search() -> list[dict[str, Any]]:
            async with LexicalStore() as store:
                return _lexical_results(
                    await store.search(
                        request.query,
                        team_id=str(target.team_id),
                        kb_ids=[str(target.kb_id)],
                        document_ids=(
                            [str(document_id) for document_id in document_ids]
                            if document_ids is not None
                            else None
                        ),
                        limit=top_k,
                    )
                )

        async def search() -> list[dict[str, Any]]:
            if search_mode == "vector":
                return await dense_search()
            if search_mode == "fulltext":
                return await lexical_search()

            dense_call = (
                dense_search()
                if target.embedding_model_id
                else asyncio.sleep(0, result=RuntimeError("missing_embedding_model"))
            )
            dense, lexical = await asyncio.gather(
                dense_call, lexical_search(), return_exceptions=True
            )
            reasons = [
                {"channel": channel, "error": type(value).__name__}
                for channel, value in (("dense", dense), ("lexical", lexical))
                if isinstance(value, BaseException)
            ]
            if len(reasons) == 2:
                raise RuntimeError(f"both retrieval channels failed: {reasons}")
            results = _weighted_rrf(
                [] if isinstance(dense, BaseException) else dense,
                [] if isinstance(lexical, BaseException) else lexical,
                dense_weight=request.dense_weight,
                lexical_weight=request.lexical_weight,
                k=request.rrf_k,
            )
            if reasons:
                for result in results:
                    result["degradation_reasons"] = reasons
            return results

        try:
            async with semaphore:
                results = await asyncio.wait_for(
                    search(), timeout=request.timeout_seconds
                )
        except TimeoutError:
            return [], RetrievalDiagnostic(target.kb_id, "timeout")
        except Exception as exc:
            return [], RetrievalDiagnostic(target.kb_id, "failed", str(exc))

        return [
            {**result, "kb_id": str(target.kb_id), "kb_name": target.kb_name}
            for result in results
        ], None

    batches = await asyncio.gather(
        *(search_target(target) for target in request.targets)
    )
    results = [result for batch, _ in batches for result in batch]
    diagnostics = tuple(diagnostic for _, diagnostic in batches if diagnostic)
    if request.targets and len(diagnostics) == len(request.targets):
        raise RetrievalError("all retrieval targets failed", diagnostics)

    results.sort(
        key=lambda result: (
            -float(result.get("score") or 0),
            str(result.get("kb_id") or ""),
            str(result.get("document_id") or ""),
            str(result.get("chunk_id") or ""),
        )
    )
    return RetrievalResponse(tuple(results[: request.top_k]), diagnostics)
