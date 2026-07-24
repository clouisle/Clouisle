import pytest

from app.services.learned_sparse_evaluation import (
    COHORTS,
    DeterministicSparseAdapter,
    IndexMeasurement,
    RetrievalObservation,
    SparseEvaluationCase,
    run_learned_sparse_gate,
)


def benchmark_cases():
    return [
        SparseEvaluationCase(
            f"case-{cohort}",
            cohort,
            {f"doc-{cohort}": 3, f"secondary-{cohort}": 3},
        )
        for cohort in COHORTS
    ]


def observations(*, learned_hits: bool = True):
    rows = {}
    for case in benchmark_cases():
        expected = next(iter(case.relevance))
        secondary = list(case.relevance)[1]
        rows[(case.case_id, "dense_bm25")] = RetrievalObservation([secondary], 10, 1)
        rows[(case.case_id, "dense_learned_sparse")] = RetrievalObservation(
            [expected, secondary] if learned_hits else [secondary], 9, 1
        )
        rows[(case.case_id, "three_way")] = RetrievalObservation(
            [expected, secondary], 8, 1
        )
    return rows


def indexes():
    return {
        "dense_bm25": IndexMeasurement(100, 20),
        "dense_learned_sparse": IndexMeasurement(90, 19),
        "three_way": IndexMeasurement(95, 18),
    }


def test_gate_selects_best_passing_strategy_without_sensitive_payloads():
    report = run_learned_sparse_gate(
        benchmark_cases(), DeterministicSparseAdapter(observations()), indexes()
    )

    assert report["decision"] == "no_go"
    assert report["decision_reason"] == "no_measured_learned_sparse_provider"
    assert report["measured"] is False
    assert report["eligible_strategy"] == "three_way"
    assert report["selected_strategy"] is None
    assert report["production_sparse_indexing_enabled"] is False
    assert report["gates"]["dense_learned_sparse"]["passed"] is True
    assert report["metrics"]["three_way"]["cohorts"] == {
        cohort: {"recall": 1, "ndcg": 1} for cohort in COHORTS
    }
    assert "query" not in str(report).lower()
    assert "case-chinese" not in str(report)
    assert "doc-chinese" not in str(report)


def test_gate_rejects_a_language_regression_despite_aggregate_gain():
    rows = observations()
    rows[("case-chinese", "dense_learned_sparse")] = RetrievalObservation(
        ["miss"], 9, 1
    )

    report = run_learned_sparse_gate(
        benchmark_cases(), DeterministicSparseAdapter(rows), indexes()
    )

    assert report["gates"]["dense_learned_sparse"]["passed"] is False
    assert report["gates"]["dense_learned_sparse"]["cohort_regressions"] == ["chinese"]


def test_gate_uses_absolute_improvement_for_zero_quality_baseline():
    rows = observations()
    for case in benchmark_cases():
        rows[(case.case_id, "dense_bm25")] = RetrievalObservation(["miss"], 10, 1)

    report = run_learned_sparse_gate(
        benchmark_cases(), DeterministicSparseAdapter(rows), indexes()
    )

    assert report["decision"] == "no_go"
    assert report["eligible_strategy"] == "three_way"
    assert report["gates"]["dense_learned_sparse"]["recall_improvement"] == 1
    assert report["gates"]["dense_learned_sparse"]["ndcg_improvement"] == 1


def test_gate_records_no_go_for_quality_and_operational_regression():
    rows = observations(learned_hits=False)
    for case in benchmark_cases():
        rows[(case.case_id, "three_way")] = RetrievalObservation(["miss"], 11, 2)

    report = run_learned_sparse_gate(
        benchmark_cases(), DeterministicSparseAdapter(rows), indexes()
    )

    assert report["decision"] == "no_go"
    assert report["selected_strategy"] is None
    assert report["gates"]["three_way"]["operational_regressions"] == [
        "p95_ms",
        "mean_inference_cost",
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"k": 0}, "k must be at least 1"),
        ({"minimum_quality_improvement": -0.1}, "must be non-negative"),
    ],
)
def test_gate_rejects_invalid_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        run_learned_sparse_gate(
            benchmark_cases(),
            DeterministicSparseAdapter(observations()),
            indexes(),
            **kwargs,
        )


def test_gate_rejects_invalid_measurements_and_duplicate_cases():
    cases = benchmark_cases()
    with pytest.raises(ValueError, match="case IDs must be unique"):
        run_learned_sparse_gate(
            [*cases, cases[0]], DeterministicSparseAdapter(observations()), indexes()
        )

    rows = observations()
    rows[("case-chinese", "dense_bm25")] = RetrievalObservation(["miss"], -1, 1)
    with pytest.raises(ValueError, match="operational measurements"):
        run_learned_sparse_gate(cases, DeterministicSparseAdapter(rows), indexes())

    invalid_indexes = indexes()
    invalid_indexes["dense_bm25"] = IndexMeasurement(-1, 20)
    with pytest.raises(ValueError, match="index measurements must be non-negative"):
        run_learned_sparse_gate(
            cases, DeterministicSparseAdapter(observations()), invalid_indexes
        )


def test_gate_rejects_incomplete_or_invalid_benchmarks():
    with pytest.raises(ValueError, match="every required cohort"):
        run_learned_sparse_gate(
            benchmark_cases()[:-1],
            DeterministicSparseAdapter(observations()),
            indexes(),
        )

    missing_indexes = indexes()
    del missing_indexes["three_way"]
    with pytest.raises(ValueError, match="cover every strategy"):
        run_learned_sparse_gate(
            benchmark_cases(),
            DeterministicSparseAdapter(observations()),
            missing_indexes,
        )

    rows = observations()
    del rows[("case-chinese", "dense_bm25")]
    with pytest.raises(ValueError, match="missing benchmark observation"):
        run_learned_sparse_gate(
            benchmark_cases(), DeterministicSparseAdapter(rows), indexes()
        )
