from math import log2
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.retrieval_evaluation import (
    EvaluationCase,
    SearchConfiguration,
    evaluate_case,
    expected_empty_accuracy,
    latency_percentiles,
    ranking_metrics,
    snapshot_baseline,
    snapshot_vector_store_baseline,
)


def case(*, expected_empty=False):
    return EvaluationCase(
        case_id="case-1",
        query="moon",
        chunk_relevance={"c1": 3, "c2": 1, "ignored": 0},
        document_relevance={"d1": 2, "d2": 1},
        expected_empty=expected_empty,
    )


def test_ranking_metrics_golden_graded_and_duplicate_results():
    metrics = ranking_metrics({"a": 3, "b": 2, "c": 1}, ["b", "b", "x", "a"], k=3)

    assert metrics.recall == pytest.approx(2 / 3)
    assert metrics.mrr == 1
    expected_dcg = 3 + 7 / log2(4)
    ideal_dcg = 7 + 3 / log2(3) + 1 / log2(4)
    assert metrics.ndcg == pytest.approx(expected_dcg / ideal_dcg)


def test_ranking_metrics_handles_fewer_hits_empty_labels_and_invalid_k():
    assert ranking_metrics({"a": 1, "b": 1}, ["a"], 10).recall == 0.5
    assert ranking_metrics({}, ["a"], 5).recall == 0
    assert ranking_metrics({}, ["a"], 5).mrr == 0
    assert ranking_metrics({}, ["a"], 5).ndcg == 0
    with pytest.raises(ValueError, match="k must be at least 1"):
        ranking_metrics({}, [], 0)


def test_case_metrics_cover_chunk_document_and_expected_empty_accuracy():
    normal = evaluate_case(case(), ["c2", "c1"], ["d2", "d1"], 2)
    empty_success = evaluate_case(case(expected_empty=True), [], [], 2)
    empty_failure = evaluate_case(case(expected_empty=True), ["c1"], ["d1"], 2)

    assert normal.chunk.recall == 1
    assert normal.document.recall == 1
    assert normal.expected_empty_correct is None
    assert empty_success.expected_empty_correct is True
    assert empty_failure.expected_empty_correct is False
    assert expected_empty_accuracy([normal]) is None
    assert expected_empty_accuracy([empty_success, empty_failure]) == 0.5


def test_latency_percentiles_reuse_continuous_interpolation():
    assert latency_percentiles([]) == {
        "p50_ms": None,
        "p95_ms": None,
        "p99_ms": None,
    }
    assert latency_percentiles([12]) == {
        "p50_ms": 12,
        "p95_ms": 12,
        "p99_ms": 12,
    }
    values = latency_percentiles([0, 100])
    assert values == {"p50_ms": 50, "p95_ms": 95, "p99_ms": 99}


@pytest.mark.anyio
async def test_snapshot_baseline_serializes_results_and_failures():
    search = AsyncMock(
        side_effect=[
            [
                {"chunk_id": "c1", "document_id": "d1"},
                {"chunk_id": "c1", "document_id": "d1"},
            ],
            RuntimeError("offline"),
        ]
    )
    configurations = [
        SearchConfiguration("vector", 5),
        SearchConfiguration("hybrid", 10, rerank_overrides={"rerank_enabled": True}),
    ]

    snapshots = await snapshot_baseline([case()], configurations, search)

    assert snapshots[0].chunk_ids == ["c1"]
    assert snapshots[0].document_ids == ["d1"]
    assert snapshots[0].error is None
    assert snapshots[0].latency_ms >= 0
    assert snapshots[0].to_dict()["configuration"]["search_mode"] == "vector"
    assert snapshots[1].chunk_ids == []
    assert snapshots[1].error == "RuntimeError: offline"


@pytest.mark.anyio
async def test_vector_store_snapshot_forwards_current_search_contract():
    store = type("Store", (), {"search": AsyncMock(return_value=[])})()
    kb_id = uuid4()
    configuration = SearchConfiguration(
        "fulltext",
        7,
        score_threshold=0.2,
        rerank_overrides={"rerank_enabled": False},
    )

    snapshots = await snapshot_vector_store_baseline(
        store, kb_id, [case()], [configuration]
    )

    assert len(snapshots) == 1
    store.search.assert_awaited_once_with(
        kb_id=kb_id,
        query="moon",
        search_mode="fulltext",
        top_k=7,
        score_threshold=0.2,
        rerank_overrides={"rerank_enabled": False},
    )
