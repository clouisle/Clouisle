"""Unified retrieval orchestration for already-authorized knowledge bases."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any, Literal
from uuid import UUID

from app.llm.token_counter import count_tokens
from app.core.config import settings
from app.models.knowledge_base import DocumentChunk, DocumentStatus, KnowledgeBaseStatus
from app.services.lexical_store import INDEX_VERSION, LexicalStore, SearchHit
from app.services.retrieval_rollout import hybrid_enabled, record_metrics, record_shadow
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
    expand_adjacent: bool = False
    max_documents: int | None = None
    max_chunks_per_document: int | None = None
    context_token_budget: int | None = None

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
        if self.max_documents is not None and self.max_documents < 1:
            raise ValueError("max_documents must be positive")
        if (
            self.max_chunks_per_document is not None
            and self.max_chunks_per_document < 1
        ):
            raise ValueError("max_chunks_per_document must be positive")
        if self.context_token_budget is not None and self.context_token_budget < 1:
            raise ValueError("context_token_budget must be positive")


@dataclass(frozen=True)
class RetrievalDiagnostic:
    kb_id: UUID
    code: Literal["inactive", "missing_embedding_model", "timeout", "failed"]
    detail: str | None = None


@dataclass(frozen=True)
class RetrievalTiming:
    stage: Literal["recall", "rerank", "context", "total"]
    latency_ms: float


@dataclass(frozen=True)
class RetrievalResponse:
    results: tuple[dict[str, Any], ...]
    diagnostics: tuple[RetrievalDiagnostic, ...]
    timings: tuple[RetrievalTiming, ...] = ()


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


async def _resolve_global_rerank(
    request: RetrievalRequest,
) -> tuple[VectorStore | None, dict[str, Any] | None]:
    target = next(
        (target for target in request.targets if target.rerank_model_id is not None),
        None,
    )
    if target is None:
        return None, None

    store = VectorStore(
        rerank_model_id=str(target.rerank_model_id),
        team_id=str(target.team_id),
    )
    config = await store._resolve_rerank_config(  # noqa: SLF001
        target.kb_id, request.rerank_overrides
    )
    if not config["enabled"] or not config["model_id"]:
        return None, None
    return store, config


async def _assemble_context(
    results: list[dict[str, Any]], request: RetrievalRequest
) -> list[dict[str, Any]]:
    if not results or not any(
        (
            request.expand_adjacent,
            request.max_documents,
            request.max_chunks_per_document,
            request.context_token_budget,
        )
    ):
        return results[: request.top_k]

    target_map = {str(target.kb_id): target for target in request.targets}
    chunk_ids = [result.get("chunk_id") for result in results if result.get("chunk_id")]
    chunks = await DocumentChunk.filter(
        id__in=chunk_ids,
        document__status=DocumentStatus.COMPLETED.value,
        document__knowledge_base__status=KnowledgeBaseStatus.ACTIVE.value,
    ).prefetch_related("document")
    seeds = {str(chunk.id): chunk for chunk in chunks}

    adjacent: dict[tuple[str, int], DocumentChunk] = {}
    if request.expand_adjacent and seeds:
        filters = [
            DocumentChunk.filter(
                document_id=chunk.document_id,
                chunk_index__in=[chunk.chunk_index - 1, chunk.chunk_index + 1],
                document__status=DocumentStatus.COMPLETED.value,
                document__knowledge_base__status=KnowledgeBaseStatus.ACTIVE.value,
            )
            for chunk in seeds.values()
        ]
        neighbor_batches = await asyncio.gather(*filters)
        adjacent = {
            (str(chunk.document_id), chunk.chunk_index): chunk
            for batch in neighbor_batches
            for chunk in batch
        }

    assembled: list[dict[str, Any]] = []
    document_results: dict[str, dict[str, Any]] = {}
    chunks_per_document: dict[str, int] = {}
    used_chunks: set[str] = set()
    used_tokens = 0

    for result in results:
        seed = seeds.get(str(result.get("chunk_id")))
        if seed is None:
            continue
        target = target_map.get(str(result.get("kb_id")))
        if target is None or seed.document.knowledge_base_id != target.kb_id:
            continue
        if (
            target.document_ids is not None
            and seed.document_id not in target.document_ids
        ):
            continue
        if (
            target.allowed_document_ids is not None
            and seed.document_id not in target.allowed_document_ids
        ):
            continue

        document_id = str(seed.document_id)
        if document_id not in document_results and (
            len(document_results) >= request.top_k
            or (
                request.max_documents is not None
                and len(document_results) >= request.max_documents
            )
        ):
            continue

        candidates = [seed]
        if request.expand_adjacent:
            candidates.extend(
                [
                    adjacent.get((document_id, seed.chunk_index - 1)),
                    adjacent.get((document_id, seed.chunk_index + 1)),
                ]
            )

        context_chunks: list[dict[str, Any]] = []
        for chunk in candidates:
            if chunk is None or str(chunk.id) in used_chunks:
                continue
            if (
                request.max_chunks_per_document is not None
                and chunks_per_document.get(document_id, 0)
                >= request.max_chunks_per_document
            ):
                break
            token_count = chunk.token_count or count_tokens(chunk.content)
            if (
                request.context_token_budget is not None
                and used_tokens + token_count > request.context_token_budget
            ):
                if chunk is seed:
                    context_chunks = []
                    break
                continue
            context_chunks.append(
                {
                    "chunk_id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": token_count,
                }
            )
            used_chunks.add(str(chunk.id))
            used_tokens += token_count
            chunks_per_document[document_id] = (
                chunks_per_document.get(document_id, 0) + 1
            )

        if not context_chunks:
            continue
        existing = document_results.get(document_id)
        if existing is not None:
            existing["context_chunks"].extend(context_chunks)
            existing["citation_chunk_ids"].extend(
                chunk["chunk_id"] for chunk in context_chunks
            )
            existing["content"] = "\n\n".join(
                chunk["content"] for chunk in existing["context_chunks"]
            )
            continue

        item = {
            **result,
            "content": "\n\n".join(chunk["content"] for chunk in context_chunks),
            "context_chunks": context_chunks,
            "citation_chunk_ids": [chunk["chunk_id"] for chunk in context_chunks],
        }
        document_results[document_id] = item
        assembled.append(item)

    return assembled


async def _retrieve_once(request: RetrievalRequest) -> RetrievalResponse:
    """Search targets concurrently, then rank and truncate results globally."""
    started_at = perf_counter()
    rerank_store, rerank_config = await _resolve_global_rerank(request)
    candidate_k = max(
        request.top_k,
        int(rerank_config["candidate_k"]) if rerank_config is not None else 0,
    )
    semaphore = asyncio.Semaphore(min(_MAX_CONCURRENCY, max(1, len(request.targets))))

    async def search_target(
        target: RetrievalTarget,
    ) -> tuple[list[dict[str, Any]], RetrievalDiagnostic | None]:
        search_mode = target.search_mode or request.search_mode
        top_k = target.top_k or request.top_k
        if rerank_config is not None:
            top_k = max(top_k, candidate_k)
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

    recall_started_at = perf_counter()
    batches = await asyncio.gather(
        *(search_target(target) for target in request.targets)
    )
    recall_ms = (perf_counter() - recall_started_at) * 1000
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
    results = results[:candidate_k]
    rerank_ms = 0.0
    if rerank_store is not None and rerank_config is not None and results:
        rerank_started_at = perf_counter()
        results = await rerank_store._rerank_results(  # noqa: SLF001
            query=request.query,
            results=results,
            model_id=rerank_config["model_id"],
            fail_open=bool(rerank_config["fail_open"]),
            rerank_score_threshold=rerank_config["score_threshold"],
        )
        rerank_ms = (perf_counter() - rerank_started_at) * 1000
    context_started_at = perf_counter()
    results = await _assemble_context(results, request)
    context_ms = (perf_counter() - context_started_at) * 1000
    timings = (
        RetrievalTiming("recall", recall_ms),
        RetrievalTiming("rerank", rerank_ms),
        RetrievalTiming("context", context_ms),
        RetrievalTiming("total", (perf_counter() - started_at) * 1000),
    )
    return RetrievalResponse(tuple(results), diagnostics, timings)


def _vector_fallback(request: RetrievalRequest) -> RetrievalRequest:
    return replace(
        request,
        search_mode="vector",
        targets=tuple(
            replace(target, search_mode="vector")
            if target.search_mode == "hybrid"
            else target
            for target in request.targets
        ),
    )


async def retrieve(request: RetrievalRequest) -> RetrievalResponse:
    """Apply hybrid rollout policy without allowing telemetry to affect answers."""
    team_ids = tuple(str(target.team_id) for target in request.targets)
    uses_hybrid = request.search_mode == "hybrid" or any(
        target.search_mode == "hybrid" for target in request.targets
    )
    enabled = not uses_hybrid or await hybrid_enabled(team_ids)
    primary_request = request if enabled else _vector_fallback(request)

    try:
        response = await _retrieve_once(primary_request)
    except RetrievalError as exc:
        await record_metrics(
            candidate_count=0,
            timings=(),
            fallback_count=int(uses_hybrid and not enabled),
            error_count=len(exc.diagnostics),
            index_version=INDEX_VERSION,
        )
        raise
    fallback_count = sum(
        bool(result.get("degradation_reasons")) for result in response.results
    ) + int(uses_hybrid and not enabled)
    await record_metrics(
        candidate_count=len(response.results),
        timings=tuple((timing.stage, timing.latency_ms) for timing in response.timings),
        fallback_count=fallback_count,
        error_count=len(response.diagnostics),
        index_version=INDEX_VERSION,
    )

    if uses_hybrid and not enabled and settings.RETRIEVAL_SHADOW_ENABLED:
        shadow_started_at = perf_counter()
        try:
            shadow = await _retrieve_once(request)
            await record_shadow(
                shadow.results,
                latency_ms=(perf_counter() - shadow_started_at) * 1000,
                index_version=INDEX_VERSION,
            )
        except Exception:
            pass
    return response
