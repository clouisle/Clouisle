"""Unified retrieval orchestration for already-authorized knowledge bases."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any, Literal, cast
from uuid import UUID

from app.llm.token_counter import count_tokens
from app.core.config import settings
from app.models.knowledge_base import DocumentChunk, DocumentStatus, KnowledgeBaseStatus
from app.services.lexical_store import INDEX_VERSION, LexicalStore, SearchHit
from app.services.retrieval_rollout import hybrid_enabled, record_metrics, record_shadow
from app.services.vector_store import VectorSearchUnavailableError, VectorStore

SearchMode = Literal["vector", "fulltext", "hybrid"]
_VALID_MODES = {"vector", "fulltext", "hybrid"}
_MAX_CONCURRENCY = 8
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _start_background(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def cleanup_background_tasks() -> None:
    tasks = tuple(_BACKGROUND_TASKS)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def validated_search_mode(value: str) -> SearchMode:
    """Validate and narrow a persisted or API-provided search mode."""
    if value not in _VALID_MODES:
        raise ValueError(f"unsupported search mode: {value}")
    return cast(SearchMode, value)


_DEFAULT_SEARCH_MODE: SearchMode = "hybrid"
_DEFAULT_TOP_K = 5
_DEFAULT_SCORE_THRESHOLD = 0.0
_DEFAULT_DENSE_WEIGHT = 1.0
_DEFAULT_LEXICAL_WEIGHT = 1.0
_DEFAULT_RRF_K = 60


def _target_setting(target: "RetrievalTarget", name: str) -> Any:
    return (target.settings or {}).get(name)


def _setting_or_default(settings: dict[str, Any], name: str, default: Any) -> Any:
    value = settings.get(name)
    return default if value is None else value


class RetrievalError(RuntimeError):
    """Raised when a retrieval request cannot produce results."""

    def __init__(
        self, message: str, diagnostics: tuple[RetrievalDiagnostic, ...]
    ) -> None:
        self.diagnostics = diagnostics
        super().__init__(message)


class _HybridChannelsFailed(RuntimeError):
    """Carry sanitized failure classifications for both hybrid channels."""

    def __init__(self, reasons: tuple[tuple[str, str], ...]) -> None:
        self.reasons = reasons
        super().__init__("both retrieval channels failed")


@dataclass
class _RetrievalContext:
    """Share in-flight query embeddings within one logical invocation."""

    embedding_tasks: dict[tuple[str, UUID, UUID], asyncio.Task[list[float]]] = field(
        default_factory=dict
    )

    async def embedding(
        self, query: str, target: "RetrievalTarget", store: VectorStore
    ) -> list[float]:
        assert target.embedding_model_id is not None
        key = (query, target.team_id, target.embedding_model_id)
        task = self.embedding_tasks.get(key)
        if task is None:
            task = asyncio.create_task(store.embed_query(query))
            self.embedding_tasks[key] = task
        try:
            return await asyncio.shield(task)
        except Exception as exc:
            raise VectorSearchUnavailableError("query_embedding_failed") from exc

    async def close(self) -> None:
        pending = [task for task in self.embedding_tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


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
    settings: dict[str, Any] | None = None
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
        if self.search_mode is not None:
            validated_search_mode(self.search_mode)
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be positive")


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    targets: tuple[RetrievalTarget, ...]
    search_mode: SearchMode | None = None
    top_k: int | None = None
    score_threshold: float | None = None
    timeout_seconds: float = 30.0
    rerank_overrides: dict[str, Any] | None = None
    dense_weight: float | None = None
    lexical_weight: float | None = None
    rrf_k: int | None = None
    expand_adjacent: bool = False
    max_documents: int | None = None
    max_chunks_per_document: int | None = None
    context_token_budget: int | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.search_mode is not None:
            validated_search_mode(self.search_mode)
        if self.top_k is not None and self.top_k < 1:
            raise ValueError("top_k must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if any(
            value is not None and value < 0
            for value in (self.dense_weight, self.lexical_weight)
        ):
            raise ValueError("retrieval weights must be nonnegative")
        if self.rrf_k is not None and self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if (
            self.dense_weight == 0
            and self.lexical_weight == 0
            and any(
                (
                    target.search_mode
                    or _target_setting(target, "search_mode")
                    or self.search_mode
                    or _DEFAULT_SEARCH_MODE
                )
                == "hybrid"
                for target in self.targets
            )
        ):
            raise ValueError(
                "at least one retrieval weight must be positive in hybrid mode"
            )
        if self.max_documents is not None and self.max_documents < 1:
            raise ValueError("max_documents must be positive")
        if (
            self.max_chunks_per_document is not None
            and self.max_chunks_per_document < 1
        ):
            raise ValueError("max_chunks_per_document must be positive")
        if self.context_token_budget is not None and self.context_token_budget < 1:
            raise ValueError("context_token_budget must be positive")


def _effective_request(request: RetrievalRequest) -> RetrievalRequest:
    """Resolve optional request values and safe single-KB defaults once."""
    settings = request.targets[0].settings or {} if len(request.targets) == 1 else {}
    dense_weight = (
        request.dense_weight
        if request.dense_weight is not None
        else _setting_or_default(settings, "dense_weight", _DEFAULT_DENSE_WEIGHT)
    )
    lexical_weight = (
        request.lexical_weight
        if request.lexical_weight is not None
        else _setting_or_default(settings, "lexical_weight", _DEFAULT_LEXICAL_WEIGHT)
    )
    effective = replace(
        request,
        search_mode=request.search_mode or _DEFAULT_SEARCH_MODE,
        top_k=request.top_k or _DEFAULT_TOP_K,
        score_threshold=(
            request.score_threshold
            if request.score_threshold is not None
            else _DEFAULT_SCORE_THRESHOLD
        ),
        dense_weight=dense_weight,
        lexical_weight=lexical_weight,
        rrf_k=(
            request.rrf_k
            if request.rrf_k is not None
            else _setting_or_default(settings, "rrf_k", _DEFAULT_RRF_K)
        ),
    )
    if (
        dense_weight == 0
        and lexical_weight == 0
        and any(
            (
                target.search_mode
                or _target_setting(target, "search_mode")
                or effective.search_mode
            )
            == "hybrid"
            for target in effective.targets
        )
    ):
        raise ValueError(
            "at least one retrieval weight must be positive in hybrid mode"
        )
    return effective


@dataclass(frozen=True)
class RetrievalDiagnostic:
    kb_id: UUID
    code: Literal["inactive", "missing_embedding_model", "timeout", "failed"]
    detail: str | None = None
    stage: str | None = None


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
        str(result.get("kb_id") or ""),
        str(result.get("document_id") or ""),
        str(result.get("chunk_id") or ""),
    )


def _lexical_results(hits: list[SearchHit]) -> list[dict[str, Any]]:
    results = [
        {
            **hit.source,
            "chunk_id": hit.chunk_id,
            "document_name": hit.source.get("name"),
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
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for channel, weight, rank_field in (
        (dense, dense_weight, "dense_rank"),
        (lexical, lexical_weight, "lexical_rank"),
    ):
        if weight == 0:
            continue
        for result in channel:
            identity = (
                str(result.get("kb_id") or ""),
                str(result.get("chunk_id") or ""),
            )
            current = merged.setdefault(identity, {})
            current.update(result)
            result_weight = float(result.get(f"_{rank_field}_weight", weight))
            result_k = int(result.get("_rrf_k", k))
            current["fusion_score"] = current.get(
                "fusion_score", 0.0
            ) + result_weight / (result_k + int(result[rank_field]))

    results = list(merged.values())
    results.sort(key=lambda result: _result_order(result, "fusion_score"))
    for rank, result in enumerate(results, 1):
        result["score"] = result["fusion_score"]
        result["fusion_rank"] = rank
        result["search_type"] = "hybrid"
        result["final_score_stage"] = "fusion"
    return results


def _global_fusion(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    channels: dict[str, list[dict[str, Any]]] = {"dense": [], "lexical": []}
    for result in results:
        channel = result.get("_fusion_channel")
        if channel in channels:
            channels[channel].append(result)
    for channel, score_field, rank_field in (
        ("dense", "dense_score", "dense_rank"),
        ("lexical", "lexical_score", "lexical_rank"),
    ):
        channels[channel].sort(
            key=lambda result: _result_order(result, score_field)
        )
        for rank, result in enumerate(channels[channel], 1):
            result[rank_field] = rank
    return _weighted_rrf(
        channels["dense"],
        channels["lexical"],
        dense_weight=_DEFAULT_DENSE_WEIGHT,
        lexical_weight=_DEFAULT_LEXICAL_WEIGHT,
        k=_DEFAULT_RRF_K,
    )


async def _resolve_global_rerank(
    request: RetrievalRequest,
) -> tuple[RetrievalTarget | None, VectorStore | None, dict[str, Any] | None]:
    for target in sorted(request.targets, key=lambda item: str(item.kb_id)):
        if (
            target.status != KnowledgeBaseStatus.ACTIVE.value
            or target.rerank_model_id is None
        ):
            continue
        store = VectorStore(
            rerank_model_id=str(target.rerank_model_id),
            team_id=str(target.team_id),
        )
        config = await store._resolve_rerank_config(  # noqa: SLF001
            target.kb_id, request.rerank_overrides
        )
        if config["enabled"] and config["model_id"]:
            return target, store, config
    return None, None, None


async def _assemble_context(
    results: list[dict[str, Any]], request: RetrievalRequest
) -> list[dict[str, Any]]:
    top_k = request.top_k or _DEFAULT_TOP_K
    if not results or not any(
        (
            request.expand_adjacent,
            request.max_documents,
            request.max_chunks_per_document,
            request.context_token_budget,
        )
    ):
        return results[:top_k]

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
            len(document_results) >= top_k
            or (
                request.max_documents is not None
                and len(document_results) >= request.max_documents
            )
        ):
            continue

        candidates: list[DocumentChunk | None] = [seed]
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

    for item in assembled:
        item["context_chunks"].sort(
            key=lambda chunk: (chunk["chunk_index"], chunk["chunk_id"])
        )
        item["citation_chunk_ids"] = [
            chunk["chunk_id"] for chunk in item["context_chunks"]
        ]
        item["content"] = "\n\n".join(
            chunk["content"] for chunk in item["context_chunks"]
        )
    return assembled


async def _retrieve_once(
    request: RetrievalRequest, context: _RetrievalContext
) -> RetrievalResponse:
    """Search targets concurrently, then rank and truncate results globally."""
    assert request.search_mode is not None
    assert request.top_k is not None
    assert request.score_threshold is not None
    assert request.dense_weight is not None
    assert request.lexical_weight is not None
    assert request.rrf_k is not None
    request_top_k = request.top_k
    request_score_threshold = request.score_threshold
    dense_weight = request.dense_weight
    lexical_weight = request.lexical_weight
    rrf_k = request.rrf_k
    started_at = perf_counter()
    rerank_target, rerank_store, rerank_config = await _resolve_global_rerank(request)
    candidate_k = max(
        request_top_k,
        int(rerank_config["candidate_k"]) if rerank_config is not None else 0,
    )
    semaphore = asyncio.Semaphore(min(_MAX_CONCURRENCY, max(1, len(request.targets))))

    async def search_target(
        target: RetrievalTarget,
    ) -> tuple[list[dict[str, Any]], RetrievalDiagnostic | None]:
        search_mode_value = (
            target.search_mode
            or _target_setting(target, "search_mode")
            or request.search_mode
        )
        search_mode = validated_search_mode(str(search_mode_value))
        target_dense_weight = _target_setting(target, "dense_weight")
        if target_dense_weight is None:
            target_dense_weight = dense_weight
        target_lexical_weight = _target_setting(target, "lexical_weight")
        if target_lexical_weight is None:
            target_lexical_weight = lexical_weight
        target_rrf_k = _target_setting(target, "rrf_k")
        if target_rrf_k is None:
            target_rrf_k = rrf_k
        if target_dense_weight < 0 or target_lexical_weight < 0:
            raise ValueError("retrieval weights must be nonnegative")
        if target_rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if (
            search_mode == "hybrid"
            and target_dense_weight == 0
            and target_lexical_weight == 0
        ):
            raise ValueError(
                "at least one retrieval weight must be positive in hybrid mode"
            )
        top_k = target.top_k
        if top_k is None:
            top_k = _target_setting(target, "top_k")
        if top_k is None:
            top_k = request_top_k
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be positive")
        if rerank_config is not None:
            top_k = max(top_k, candidate_k)
        score_threshold = (
            target.score_threshold
            if target.score_threshold is not None
            else _target_setting(target, "score_threshold")
        )
        if score_threshold is None:
            score_threshold = request_score_threshold
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
            store = VectorStore(
                embedding_model_id=(
                    str(target.embedding_model_id)
                    if target.embedding_model_id
                    else None
                ),
                rerank_model_id=(
                    str(target.rerank_model_id) if target.rerank_model_id else None
                ),
                team_id=str(target.team_id),
            )
            query_embedding = await context.embedding(request.query, target, store)
            return _dense_results(
                await store.search(
                    kb_id=target.kb_id,
                    query=request.query,
                    search_mode="vector",
                    top_k=top_k,
                    score_threshold=score_threshold,
                    filter_doc_ids=document_ids,
                    embedding_dimension=target.embedding_dimension,
                    rerank_overrides={"rerank_enabled": False},
                    query_embedding=query_embedding,
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
                results = await dense_search()
                for result in results:
                    result["_fusion_channel"] = "dense"
                    result["_dense_rank_weight"] = dense_weight
                    result["_rrf_k"] = rrf_k
                return results
            if search_mode == "fulltext":
                results = await lexical_search()
                for result in results:
                    result["_fusion_channel"] = "lexical"
                    result["_lexical_rank_weight"] = lexical_weight
                    result["_rrf_k"] = rrf_k
                return results
            channels: list[tuple[str, Any]] = []
            if target_dense_weight > 0:
                dense_call = (
                    dense_search()
                    if target.embedding_model_id
                    else asyncio.sleep(
                        0, result=RuntimeError("missing_embedding_model")
                    )
                )
                channels.append(("dense", dense_call))
            if target_lexical_weight > 0:
                channels.append(("lexical", lexical_search()))
            values = await asyncio.gather(
                *(call for _, call in channels), return_exceptions=True
            )
            channel_values: dict[str, Any] = dict(
                zip((name for name, _ in channels), values, strict=True)
            )
            dense = cast(
                list[dict[str, Any]] | BaseException, channel_values.get("dense", [])
            )
            lexical = cast(
                list[dict[str, Any]] | BaseException, channel_values.get("lexical", [])
            )
            reasons = [
                (channel, type(value).__name__)
                for channel, value in channel_values.items()
                if isinstance(value, BaseException)
            ]
            if reasons and len(reasons) == len(channels):
                raise _HybridChannelsFailed(tuple(reasons))
            dense_results = [] if isinstance(dense, BaseException) else dense
            lexical_results = [] if isinstance(lexical, BaseException) else lexical
            for result in dense_results:
                result["_fusion_channel"] = "dense"
                result["_dense_rank_weight"] = target_dense_weight
                result["_rrf_k"] = target_rrf_k
            for result in lexical_results:
                result["_fusion_channel"] = "lexical"
                result["_lexical_rank_weight"] = target_lexical_weight
                result["_rrf_k"] = target_rrf_k
            results = dense_results + lexical_results
            if reasons:
                degradation_reasons = [
                    {"channel": channel, "error": error} for channel, error in reasons
                ]
                for result in results:
                    result["degradation_reasons"] = degradation_reasons
            return results

        try:
            async with semaphore:
                results = await asyncio.wait_for(
                    search(), timeout=request.timeout_seconds
                )
        except TimeoutError:
            return [], RetrievalDiagnostic(target.kb_id, "timeout", stage="recall")
        except _HybridChannelsFailed as exc:
            detail = "; ".join(f"{channel}={error}" for channel, error in exc.reasons)
            return [], RetrievalDiagnostic(
                target.kb_id, "failed", detail, stage="fusion"
            )
        except Exception as exc:
            stage = "lexical_recall" if search_mode == "fulltext" else "dense_recall"
            return [], RetrievalDiagnostic(
                target.kb_id,
                "failed",
                type(exc).__name__,
                stage=stage,
            )

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

    uses_fusion = any(
        (
            target.search_mode
            or _target_setting(target, "search_mode")
            or request.search_mode
        )
        == "hybrid"
        for target in request.targets
    )
    if uses_fusion:
        results = _global_fusion(results)
    else:
        results.sort(key=lambda result: _result_order(result, "score"))
    for result in results:
        for field_name in tuple(result):
            if field_name.startswith("_"):
                result.pop(field_name)
    results = results[:candidate_k]
    rerank_ms = 0.0
    if rerank_store is not None and rerank_config is not None and results:
        rerank_started_at = perf_counter()
        try:
            results = await rerank_store._rerank_results(  # noqa: SLF001
                query=request.query,
                results=results,
                model_id=rerank_config["model_id"],
                rerank_score_threshold=rerank_config["score_threshold"],
            )
        except Exception as exc:
            rerank_diagnostic = RetrievalDiagnostic(
                rerank_target.kb_id if rerank_target else UUID(int=0),
                "failed",
                type(exc).__name__,
                stage="rerank",
            )
            raise RetrievalError("rerank failed", (rerank_diagnostic,)) from exc
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
            if (target.search_mode or _target_setting(target, "search_mode"))
            == "hybrid"
            else target
            for target in request.targets
        ),
    )


async def retrieve_many(
    requests: tuple[RetrievalRequest, ...],
) -> tuple[RetrievalResponse | BaseException, ...]:
    """Retrieve independent variants while sharing invocation-local embeddings."""
    context = _RetrievalContext()
    try:
        return tuple(
            await asyncio.gather(
                *(retrieve(request, context=context) for request in requests),
                return_exceptions=True,
            )
        )
    finally:
        await context.close()


async def _run_shadow(request: RetrievalRequest) -> None:
    context = _RetrievalContext()
    started_at = perf_counter()
    try:
        shadow = await _retrieve_once(request, context)
        await record_shadow(
            shadow.results,
            latency_ms=(perf_counter() - started_at) * 1000,
            index_version=INDEX_VERSION,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    finally:
        await context.close()


async def retrieve(
    request: RetrievalRequest, *, context: _RetrievalContext | None = None
) -> RetrievalResponse:
    """Apply hybrid rollout policy without allowing telemetry to affect answers."""
    owns_context = context is None
    context = context or _RetrievalContext()
    request = _effective_request(request)
    team_ids = tuple(str(target.team_id) for target in request.targets)
    uses_hybrid = any(
        (
            target.search_mode
            or _target_setting(target, "search_mode")
            or request.search_mode
        )
        == "hybrid"
        for target in request.targets
    )
    enabled = not uses_hybrid or await hybrid_enabled(team_ids)
    primary_request = request if enabled else _vector_fallback(request)

    try:
        response = await _retrieve_once(primary_request, context)
    except RetrievalError as exc:
        await record_metrics(
            candidate_count=0,
            timings=(),
            fallback_count=int(uses_hybrid and not enabled),
            error_count=len(exc.diagnostics),
            index_version=INDEX_VERSION,
        )
        if owns_context:
            await context.close()
        raise
    except BaseException:
        if owns_context:
            await context.close()
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
        _start_background(_run_shadow(request))
    if owns_context:
        await context.close()
    return response
