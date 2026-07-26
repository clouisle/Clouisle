"""Deterministic metrics and snapshots for retrieval evaluation."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from math import log2
from statistics import mean
from time import perf_counter
from typing import Any
from uuid import UUID

from app.services.admin_observability import continuous_percentile


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query: str
    chunk_relevance: dict[str, int]
    document_relevance: dict[str, int]
    expected_empty: bool = False


@dataclass(frozen=True)
class SearchConfiguration:
    search_mode: str
    top_k: int
    score_threshold: float = 0.0
    rerank_overrides: dict[str, Any] | None = None


@dataclass(frozen=True)
class RankingMetrics:
    recall: float
    mrr: float
    ndcg: float


@dataclass(frozen=True)
class CaseEvaluation:
    chunk: RankingMetrics
    document: RankingMetrics
    expected_empty_correct: bool | None
    chunk_graded: bool
    document_graded: bool


@dataclass(frozen=True)
class BaselineSnapshot:
    case_id: str
    configuration: SearchConfiguration
    chunk_ids: list[str]
    document_ids: list[str]
    latency_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _graded(relevance: dict[str, int]) -> bool:
    """A case only carries ranking signal when it has at least one positive grade."""
    return any(grade > 0 for grade in relevance.values())


def ranking_metrics(
    relevance: dict[str, int], retrieved_ids: Sequence[str], k: int
) -> RankingMetrics:
    if k < 1:
        raise ValueError("k must be at least 1")
    ranked = _unique(retrieved_ids)[:k]
    relevant_ids = {item_id for item_id, grade in relevance.items() if grade > 0}
    recall = (
        len(relevant_ids.intersection(ranked)) / len(relevant_ids)
        if relevant_ids
        else 0.0
    )
    first_relevant_rank = next(
        (rank for rank, item_id in enumerate(ranked, 1) if item_id in relevant_ids),
        None,
    )
    mrr = 1 / first_relevant_rank if first_relevant_rank else 0.0

    dcg = sum(
        (2 ** max(0, relevance.get(item_id, 0)) - 1) / log2(rank + 1)
        for rank, item_id in enumerate(ranked, 1)
    )
    ideal_grades = sorted(
        (grade for grade in relevance.values() if grade > 0), reverse=True
    )[:k]
    ideal_dcg = sum(
        (2**grade - 1) / log2(rank + 1) for rank, grade in enumerate(ideal_grades, 1)
    )
    return RankingMetrics(
        recall=recall, mrr=mrr, ndcg=dcg / ideal_dcg if ideal_dcg else 0.0
    )


def evaluate_case(
    case: EvaluationCase,
    chunk_ids: Sequence[str],
    document_ids: Sequence[str],
    k: int,
) -> CaseEvaluation:
    unique_chunks = _unique(chunk_ids)
    unique_documents = _unique(document_ids)
    return CaseEvaluation(
        chunk=ranking_metrics(case.chunk_relevance, unique_chunks, k),
        document=ranking_metrics(case.document_relevance, unique_documents, k),
        expected_empty_correct=(not unique_chunks if case.expected_empty else None),
        chunk_graded=_graded(case.chunk_relevance),
        document_graded=_graded(case.document_relevance),
    )


def ranking_means(metrics: Sequence[RankingMetrics]) -> dict[str, float | None]:
    """Average one metric family, reporting None when no case is gradeable."""
    if not metrics:
        return {"recall": None, "mrr": None, "ndcg": None}
    return {
        "recall": mean(item.recall for item in metrics),
        "mrr": mean(item.mrr for item in metrics),
        "ndcg": mean(item.ndcg for item in metrics),
    }


def expected_empty_accuracy(evaluations: Sequence[CaseEvaluation]) -> float | None:
    outcomes = [
        evaluation.expected_empty_correct
        for evaluation in evaluations
        if evaluation.expected_empty_correct is not None
    ]
    return (
        sum(outcome is True for outcome in outcomes) / len(outcomes)
        if outcomes
        else None
    )


def latency_percentiles(latencies_ms: Sequence[float]) -> dict[str, float | None]:
    return {
        "p50_ms": continuous_percentile(latencies_ms, 0.50),
        "p95_ms": continuous_percentile(latencies_ms, 0.95),
        "p99_ms": continuous_percentile(latencies_ms, 0.99),
    }


async def snapshot_baseline(
    cases: Sequence[EvaluationCase],
    configurations: Sequence[SearchConfiguration],
    search: Callable[
        [EvaluationCase, SearchConfiguration],
        Awaitable[list[dict[str, Any]]],
    ],
) -> list[BaselineSnapshot]:
    snapshots: list[BaselineSnapshot] = []
    for case in cases:
        for configuration in configurations:
            started = perf_counter()
            try:
                results = await search(case, configuration)
                chunk_ids = _unique([str(result["chunk_id"]) for result in results])
                document_ids = _unique(
                    [str(result["document_id"]) for result in results]
                )
                error = None
            except Exception as exc:
                chunk_ids = []
                document_ids = []
                error = f"{type(exc).__name__}: {exc}"
            snapshots.append(
                BaselineSnapshot(
                    case_id=case.case_id,
                    configuration=configuration,
                    chunk_ids=chunk_ids,
                    document_ids=document_ids,
                    latency_ms=(perf_counter() - started) * 1000,
                    error=error,
                )
            )
    return snapshots


async def snapshot_vector_store_baseline(
    vector_store: Any,
    kb_id: UUID,
    cases: Sequence[EvaluationCase],
    configurations: Sequence[SearchConfiguration],
) -> list[BaselineSnapshot]:
    async def search(
        case: EvaluationCase, configuration: SearchConfiguration
    ) -> list[dict[str, Any]]:
        return await vector_store.search(
            kb_id=kb_id,
            query=case.query,
            search_mode=configuration.search_mode,
            top_k=configuration.top_k,
            score_threshold=configuration.score_threshold,
            rerank_overrides=configuration.rerank_overrides,
        )

    return await snapshot_baseline(cases, configurations, search)
