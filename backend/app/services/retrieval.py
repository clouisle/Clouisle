"""Unified retrieval orchestration for already-authorized knowledge bases."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.models.knowledge_base import KnowledgeBaseStatus
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

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.search_mode not in _VALID_MODES:
            raise ValueError(f"unsupported search mode: {self.search_mode}")
        if self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True)
class RetrievalDiagnostic:
    kb_id: UUID
    code: Literal["inactive", "missing_embedding_model", "timeout", "failed"]
    detail: str | None = None


@dataclass(frozen=True)
class RetrievalResponse:
    results: tuple[dict[str, Any], ...]
    diagnostics: tuple[RetrievalDiagnostic, ...]


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

        try:
            async with semaphore:
                results = await asyncio.wait_for(
                    VectorStore(
                        embedding_model_id=(
                            str(target.embedding_model_id)
                            if target.embedding_model_id
                            else None
                        ),
                        rerank_model_id=(
                            str(target.rerank_model_id)
                            if target.rerank_model_id
                            else None
                        ),
                        team_id=str(target.team_id),
                    ).search(
                        kb_id=target.kb_id,
                        query=request.query,
                        search_mode=search_mode,
                        top_k=top_k,
                        score_threshold=score_threshold,
                        filter_doc_ids=(
                            list(target.document_ids or target.allowed_document_ids)
                            if target.document_ids is not None
                            or target.allowed_document_ids is not None
                            else None
                        ),
                        embedding_dimension=target.embedding_dimension,
                        rerank_overrides=request.rerank_overrides,
                    ),
                    timeout=request.timeout_seconds,
                )
        except TimeoutError:
            return [], RetrievalDiagnostic(target.kb_id, "timeout")
        except Exception as exc:
            return [], RetrievalDiagnostic(target.kb_id, "failed", type(exc).__name__)

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
