"""Offline-only learned sparse retrieval evaluation gate."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from statistics import mean
from typing import Literal, TypedDict

from app.services.retrieval_evaluation import latency_percentiles, ranking_metrics

Strategy = Literal["dense_bm25", "dense_learned_sparse", "three_way"]
Cohort = Literal["chinese", "english", "mixed_language", "identifiers"]

STRATEGIES: tuple[Strategy, ...] = (
    "dense_bm25",
    "dense_learned_sparse",
    "three_way",
)
COHORTS: tuple[Cohort, ...] = (
    "chinese",
    "english",
    "mixed_language",
    "identifiers",
)


@dataclass(frozen=True)
class SparseEvaluationCase:
    case_id: str
    cohort: Cohort
    relevance: Mapping[str, int]


@dataclass(frozen=True)
class RetrievalObservation:
    ranked_ids: Sequence[str]
    latency_ms: float
    inference_cost: float


@dataclass(frozen=True)
class IndexMeasurement:
    index_size_bytes: int
    rebuild_time_ms: float


class StrategyMetrics(TypedDict):
    recall: float
    ndcg: float
    cohorts: dict[Cohort, dict[str, float]]
    p95_ms: float | None
    mean_inference_cost: float
    index_size_bytes: int
    rebuild_time_ms: float


class DeterministicSparseAdapter:
    """Returns precomputed ID-only observations for reproducible evaluation."""

    measured = False

    def __init__(
        self, observations: Mapping[tuple[str, Strategy], RetrievalObservation]
    ) -> None:
        self._observations = observations

    def retrieve(self, case_id: str, strategy: Strategy) -> RetrievalObservation:
        try:
            return self._observations[(case_id, strategy)]
        except KeyError:
            raise ValueError("missing benchmark observation") from None


def _validate_measurement(observation: RetrievalObservation) -> None:
    if observation.latency_ms < 0 or observation.inference_cost < 0:
        raise ValueError("operational measurements must be non-negative")


def _improvement(candidate: float, baseline: float) -> float:
    return candidate - baseline if baseline == 0 else (candidate - baseline) / baseline


def _operational_regressions(
    candidate: StrategyMetrics, baseline: StrategyMetrics
) -> list[str]:
    regressions = []
    if candidate["mean_inference_cost"] > baseline["mean_inference_cost"]:
        regressions.append("mean_inference_cost")
    if candidate["index_size_bytes"] > baseline["index_size_bytes"]:
        regressions.append("index_size_bytes")
    if candidate["rebuild_time_ms"] > baseline["rebuild_time_ms"]:
        regressions.append("rebuild_time_ms")
    if (
        candidate["p95_ms"] is not None
        and baseline["p95_ms"] is not None
        and candidate["p95_ms"] > baseline["p95_ms"]
    ):
        regressions.insert(0, "p95_ms")
    return regressions


def run_learned_sparse_gate(
    cases: Sequence[SparseEvaluationCase],
    adapter: DeterministicSparseAdapter,
    indexes: Mapping[Strategy, IndexMeasurement],
    *,
    k: int = 10,
    minimum_quality_improvement: float = 0.05,
) -> dict[str, object]:
    """Compare three retrieval strategies and return a persistence-safe gate report."""
    if k < 1:
        raise ValueError("k must be at least 1")
    if minimum_quality_improvement < 0:
        raise ValueError("minimum quality improvement must be non-negative")
    if not cases or {case.cohort for case in cases} != set(COHORTS):
        raise ValueError("benchmark must include every required cohort")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("benchmark case IDs must be unique")
    if set(indexes) != set(STRATEGIES):
        raise ValueError("index measurements must cover every strategy")

    metrics: dict[Strategy, StrategyMetrics] = {}
    fingerprint_rows: list[object] = []
    for strategy in STRATEGIES:
        recalls: list[float] = []
        ndcgs: list[float] = []
        latencies: list[float] = []
        costs: list[float] = []
        cohort_values: dict[Cohort, dict[str, list[float]]] = {
            cohort: {"recall": [], "ndcg": []} for cohort in COHORTS
        }
        for case in cases:
            observation = adapter.retrieve(case.case_id, strategy)
            _validate_measurement(observation)
            ranking = ranking_metrics(dict(case.relevance), observation.ranked_ids, k)
            recalls.append(ranking.recall)
            ndcgs.append(ranking.ndcg)
            latencies.append(observation.latency_ms)
            costs.append(observation.inference_cost)
            cohort_values[case.cohort]["recall"].append(ranking.recall)
            cohort_values[case.cohort]["ndcg"].append(ranking.ndcg)
            fingerprint_rows.append(
                [
                    case.case_id,
                    case.cohort,
                    sorted(case.relevance.items()),
                    strategy,
                    list(observation.ranked_ids),
                    observation.latency_ms,
                    observation.inference_cost,
                ]
            )
        index = indexes[strategy]
        if index.index_size_bytes < 0 or index.rebuild_time_ms < 0:
            raise ValueError("index measurements must be non-negative")
        metrics[strategy] = {
            "recall": mean(recalls),
            "ndcg": mean(ndcgs),
            "cohorts": {
                cohort: {
                    name: mean(values) for name, values in cohort_values[cohort].items()
                }
                for cohort in COHORTS
            },
            "p95_ms": latency_percentiles(latencies)["p95_ms"],
            "mean_inference_cost": mean(costs),
            "index_size_bytes": index.index_size_bytes,
            "rebuild_time_ms": index.rebuild_time_ms,
        }
        fingerprint_rows.append(
            [strategy, index.index_size_bytes, index.rebuild_time_ms]
        )

    baseline = metrics["dense_bm25"]
    gates: dict[Strategy, dict[str, object]] = {}
    passing: list[Strategy] = []
    for strategy in STRATEGIES[1:]:
        candidate = metrics[strategy]
        recall_improvement = _improvement(candidate["recall"], baseline["recall"])
        ndcg_improvement = _improvement(candidate["ndcg"], baseline["ndcg"])
        cohort_regressions = [
            cohort
            for cohort in COHORTS
            if any(
                candidate["cohorts"][cohort][name] < baseline["cohorts"][cohort][name]
                for name in ("recall", "ndcg")
            )
        ]
        operational_regressions = _operational_regressions(candidate, baseline)
        quality_passed = (
            recall_improvement >= minimum_quality_improvement
            and ndcg_improvement >= minimum_quality_improvement
        )
        passed = (
            quality_passed and not cohort_regressions and not operational_regressions
        )
        gates[strategy] = {
            "passed": passed,
            "recall_improvement": recall_improvement,
            "ndcg_improvement": ndcg_improvement,
            "cohort_regressions": cohort_regressions,
            "operational_regressions": operational_regressions,
        }
        if passed:
            passing.append(strategy)

    selected = max(
        passing,
        key=lambda strategy: (
            metrics[strategy]["recall"] + metrics[strategy]["ndcg"],
            strategy,
        ),
        default=None,
    )
    fingerprint = sha256(
        json.dumps(fingerprint_rows, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "benchmark_fingerprint": fingerprint,
        "case_count": len(cases),
        "k": k,
        "minimum_quality_improvement": minimum_quality_improvement,
        "metrics": metrics,
        "gates": gates,
        "measured": adapter.measured,
        "decision": "no_go",
        "decision_reason": "no_measured_learned_sparse_provider",
        "eligible_strategy": selected,
        "selected_strategy": None,
        "production_sparse_indexing_enabled": False,
    }
