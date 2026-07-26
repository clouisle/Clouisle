"""Tests for retrieval parameter tuning pure functions."""

from app.services.retrieval_tuning import (
    candidate_key,
    compare_runs,
    config_fingerprint,
    expand_space,
    expand_stage,
    normalize_space,
    score_run,
    select_recommendation,
)


class TestNormalizeSpace:
    """Tests for normalize_space function."""

    def test_empty_space_uses_defaults(self):
        """Empty space should return all default axes."""
        baseline = {"top_k": 10}
        result = normalize_space({}, baseline)

        assert "channel_weights" in result
        assert "rrf_k" in result
        assert "rerank_config" in result
        assert "rerank_score_threshold" in result
        assert "score_threshold" in result

        assert len(result["channel_weights"]) == 5
        assert result["rrf_k"] == [20, 60, 120]

    def test_partial_space_merges_with_defaults(self):
        """User-provided axes should override defaults."""
        baseline = {"top_k": 10}
        space = {"rrf_k": [30, 90], "score_threshold": [0.1]}

        result = normalize_space(space, baseline)

        assert result["rrf_k"] == [30, 90]
        assert result["score_threshold"] == [0.1]
        assert len(result["channel_weights"]) == 5  # default

    def test_scalar_values_wrapped_in_list(self):
        """Scalar values should be wrapped in list."""
        baseline = {"top_k": 10}
        space = {"rrf_k": 40}

        result = normalize_space(space, baseline)

        assert result["rrf_k"] == [40]

    def test_deduplicates_candidates(self):
        """Duplicate candidates should be removed while preserving order."""
        baseline = {"top_k": 10}
        space = {"rrf_k": [20, 60, 20, 60, 120]}

        result = normalize_space(space, baseline)

        assert result["rrf_k"] == [20, 60, 120]

    def test_deduplicates_dict_candidates(self):
        """Duplicate dict candidates should be removed by canonical JSON."""
        baseline = {"top_k": 10}
        space = {
            "rerank_config": [
                {"enabled": True, "candidate_k": 20},
                {"candidate_k": 20, "enabled": True},  # same content, different order
                {"enabled": False},
            ]
        }

        result = normalize_space(space, baseline)

        assert len(result["rerank_config"]) == 2

    def test_empty_candidate_list_uses_baseline_value(self):
        """Empty candidate list should fall back to baseline value."""
        baseline = {"rrf_k": 50}
        space = {"rrf_k": []}

        result = normalize_space(space, baseline)

        assert result["rrf_k"] == [50]


class TestCandidateKey:
    """Tests for candidate_key function."""

    def test_scalar_values(self):
        """Scalar values should produce readable keys."""
        assert candidate_key("s1", "rrf_k", 60) == "s1:rrf_k=60"
        assert candidate_key("s2", "score_threshold", 0.2) == "s2:score_threshold=0.2"

    def test_dict_values(self):
        """Dict values should be JSON-serialized with sorted keys."""
        key1 = candidate_key(
            "s3", "rerank_config", {"enabled": True, "candidate_k": 20}
        )
        key2 = candidate_key(
            "s3", "rerank_config", {"candidate_k": 20, "enabled": True}
        )

        assert key1 == key2  # order-independent
        assert "rerank_config=" in key1
        assert "candidate_k" in key1

    def test_tuple_values(self):
        """Tuple values should be converted to string."""
        key = candidate_key("s1", "channel_weights", (1.0, 0.6))
        assert key == "s1:channel_weights=(1.0, 0.6)"


class TestExpandStage:
    """Tests for expand_stage function."""

    def test_channel_weights_expansion(self):
        """Channel weights should expand to dense_weight and lexical_weight."""
        parent = {"top_k": 10}
        candidates = [(1.0, 0.6), (0.6, 1.0)]

        result = expand_stage(
            "s1_weights", "channel_weights", candidates, parent, 10, 10
        )

        assert len(result) == 2
        key1, label1, config1 = result[0]
        assert "D1.0×L0.6" in label1
        assert config1["dense_weight"] == 1.0
        assert config1["lexical_weight"] == 0.6

    def test_rrf_k_expansion(self):
        """RRF k should be mapped directly."""
        parent = {"top_k": 10}
        candidates = [20, 60]

        result = expand_stage("s2_rrf", "rrf_k", candidates, parent, 10, 10)

        assert len(result) == 2
        _, label1, config1 = result[0]
        assert label1 == "rrf_k=20"
        assert config1["rrf_k"] == 20

    def test_rerank_config_expansion(self):
        """Rerank config should set enabled and candidate_k."""
        parent = {"top_k": 10}
        candidates = [
            {"enabled": False},
            {"enabled": True, "candidate_k": 20},
            {"enabled": True, "candidate_k": 50},
        ]

        result = expand_stage("s3_rerank", "rerank_config", candidates, parent, 10, 10)

        assert len(result) == 3
        _, label1, config1 = result[0]
        assert label1 == "rerank=off"
        assert config1["rerank_enabled"] is False

        _, label2, config2 = result[1]
        assert label2 == "rerank@20"
        assert config2["rerank_enabled"] is True
        assert config2["rerank_candidate_k"] == 20

    def test_rerank_score_threshold_skipped_when_rerank_off(self):
        """Rerank score threshold should be skipped when rerank is disabled."""
        parent = {"top_k": 10, "rerank_enabled": False}
        candidates = [None, 0.1, 0.3]

        result = expand_stage(
            "s4_rerank_thresh", "rerank_score_threshold", candidates, parent, 10, 10
        )

        assert len(result) == 0  # all skipped

    def test_rerank_score_threshold_used_when_rerank_on(self):
        """Rerank score threshold should be used when rerank is enabled."""
        parent = {"top_k": 10, "rerank_enabled": True}
        candidates = [None, 0.1, 0.3]

        result = expand_stage(
            "s4_rerank_thresh", "rerank_score_threshold", candidates, parent, 10, 10
        )

        assert len(result) == 3
        _, label1, config1 = result[0]
        assert label1 == "rerank_thresh=none"
        assert config1["rerank_score_threshold"] is None

    def test_score_threshold_expansion(self):
        """Score threshold should be mapped directly."""
        parent = {"top_k": 10}
        candidates = [0, 0.2, 0.35]

        result = expand_stage(
            "s5_score_thresh", "score_threshold", candidates, parent, 10, 10
        )

        assert len(result) == 3
        _, label1, config1 = result[0]
        assert label1 == "score_thresh=0"
        assert config1["score_threshold"] == 0

    def test_top_k_clamped_to_metric_k(self):
        """Config top_k should be clamped to metric_k minimum."""
        parent = {"top_k": 5}
        candidates = [20]
        metric_k = 10

        result = expand_stage("s2_rrf", "rrf_k", candidates, parent, metric_k, 10)

        _, _, config = result[0]
        assert config["top_k"] == 10  # clamped from 5 to 10

    def test_unknown_axis_returns_empty(self):
        """Unknown axis should return empty list."""
        parent = {"top_k": 10}
        candidates = [1, 2, 3]

        result = expand_stage("s99", "unknown_axis", candidates, parent, 10, 10)

        assert len(result) == 0


class TestExpandSpace:
    """Tests for expand_space function."""

    def test_baseline_always_first(self):
        """First tuple should always be baseline."""
        baseline = {"top_k": 10, "rrf_k": 60}
        space = normalize_space({}, baseline)

        result = expand_space(space, baseline, 10, 10)

        assert len(result) > 0
        stage, key, label, config = result[0]
        assert stage == "baseline"
        assert key == "baseline"
        assert label == "baseline"
        assert config["top_k"] == 10

    def test_staged_order(self):
        """Candidates should be grouped by stage in defined order."""
        baseline = {"top_k": 10}
        space = {
            "channel_weights": [(1.0, 1.0)],
            "rrf_k": [60],
            "rerank_config": [{"enabled": False}],
            "score_threshold": [0],
        }

        result = expand_space(space, baseline, 10, 10)

        stages = [stage for stage, _, _, _ in result[1:]]  # skip baseline
        assert stages == ["s1_weights", "s2_rrf", "s3_rerank", "s5_score_thresh"]

    def test_empty_axis_skipped(self):
        """Axes with no candidates should be skipped."""
        baseline = {"top_k": 10}
        space = {"rrf_k": [60], "rerank_config": []}  # rerank_config empty

        result = expand_space(space, baseline, 10, 10)

        stages = [stage for stage, _, _, _ in result[1:]]
        assert "s2_rrf" in stages
        assert "s3_rerank" not in stages  # skipped

    def test_baseline_top_k_clamped_to_metric_k(self):
        """Baseline top_k should be clamped to metric_k minimum."""
        baseline = {"top_k": 5}
        space = {}
        metric_k = 10

        result = expand_space(space, baseline, metric_k, 10)

        _, _, _, config = result[0]
        assert config["top_k"] == 10  # clamped from 5

    def test_candidate_keys_deterministic(self):
        """Candidate keys should be deterministic and unique."""
        baseline = {"top_k": 10}
        space = {"rrf_k": [20, 60, 120]}

        result1 = expand_space(space, baseline, 10, 10)
        result2 = expand_space(space, baseline, 10, 10)

        keys1 = [key for _, key, _, _ in result1]
        keys2 = [key for _, key, _, _ in result2]

        assert keys1 == keys2
        assert len(keys1) == len(set(keys1))  # all unique


class TestConfigFingerprint:
    """Tests for config_fingerprint function."""

    def test_same_config_same_fingerprint(self):
        """Same config should produce same fingerprint."""
        config1 = {"top_k": 10, "rrf_k": 60}
        config2 = {"top_k": 10, "rrf_k": 60}

        fp1 = config_fingerprint(config1)
        fp2 = config_fingerprint(config2)

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_different_config_different_fingerprint(self):
        """Different configs should produce different fingerprints."""
        config1 = {"top_k": 10, "rrf_k": 60}
        config2 = {"top_k": 10, "rrf_k": 120}

        fp1 = config_fingerprint(config1)
        fp2 = config_fingerprint(config2)

        assert fp1 != fp2

    def test_key_order_independent(self):
        """Config fingerprint should be order-independent."""
        config1 = {"top_k": 10, "rrf_k": 60, "rerank_enabled": True}
        config2 = {"rerank_enabled": True, "rrf_k": 60, "top_k": 10}

        fp1 = config_fingerprint(config1)
        fp2 = config_fingerprint(config2)

        assert fp1 == fp2


class TestScoreRun:
    """Tests for score_run function."""

    def test_extracts_metric_from_summary(self):
        """Should extract objective metric from run summary."""
        summary = {"chunk_recall@10": 0.85, "chunk_mrr@10": 0.72}

        score = score_run(summary, "chunk_recall", 10)

        assert score == 0.85

    def test_missing_metric_returns_negative(self):
        """Missing metric should return -1.0."""
        summary = {"chunk_recall@10": 0.85}

        score = score_run(summary, "document_recall", 10)

        assert score == -1.0

    def test_different_metric_k(self):
        """Should use correct metric_k suffix."""
        summary = {"chunk_recall@5": 0.8, "chunk_recall@10": 0.85}

        score5 = score_run(summary, "chunk_recall", 5)
        score10 = score_run(summary, "chunk_recall", 10)

        assert score5 == 0.8
        assert score10 == 0.85


class TestCompareRuns:
    """Tests for compare_runs function."""

    def test_improvement(self):
        """Should detect improvement."""
        baseline = {"chunk_recall@10": 0.70}
        candidate = {"chunk_recall@10": 0.85}

        improved, regressed, delta = compare_runs(
            baseline, candidate, "chunk_recall", 10
        )

        assert improved == 1
        assert regressed == 0
        assert abs(delta - 0.15) < 1e-9

    def test_regression(self):
        """Should detect regression."""
        baseline = {"chunk_recall@10": 0.85}
        candidate = {"chunk_recall@10": 0.70}

        improved, regressed, delta = compare_runs(
            baseline, candidate, "chunk_recall", 10
        )

        assert improved == 0
        assert regressed == 1
        assert abs(delta - (-0.15)) < 1e-9

    def test_no_change_within_tolerance(self):
        """Small deltas within 0.01 should be counted as unchanged."""
        baseline = {"chunk_recall@10": 0.80}
        candidate = {"chunk_recall@10": 0.805}

        improved, regressed, delta = compare_runs(
            baseline, candidate, "chunk_recall", 10
        )

        assert improved == 0
        assert regressed == 0
        assert abs(delta) < 0.01

    def test_missing_baseline_metric(self):
        """Missing baseline metric should return no change with -1.0 delta."""
        baseline = {}
        candidate = {"chunk_recall@10": 0.85}

        improved, regressed, delta = compare_runs(
            baseline, candidate, "chunk_recall", 10
        )

        # When baseline score is -1.0, delta = 0.85 - (-1.0) = 1.85 > 0.01
        assert improved == 1
        assert regressed == 0


class TestSelectRecommendation:
    """Tests for select_recommendation function."""

    def test_no_improvement_returns_none(self):
        """No candidates passing guards should return None."""
        candidates = [
            ("baseline", {"top_k": 10}, {"chunk_recall@10": 0.80, "error_count": 0}),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.81, "error_count": 0},
            ),  # +0.01, below min
        ]
        guards = {"min_improvement": 0.05}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result is None

    def test_selects_best_candidate(self):
        """Should select candidate with highest objective delta."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.75, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c2",
                {"rrf_k": 120},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 100},
            ),
        ]
        guards = {"min_improvement": 0.02}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result is not None
        assert result["candidate_key"] == "c2"
        assert abs(result["delta"] - 0.15) < 1e-9
        assert result["baseline_value"] == 0.70
        assert result["objective_value"] == 0.85

    def test_filters_by_error_count(self):
        """Should filter candidates exceeding max_error_count."""
        candidates = [
            ("baseline", {"top_k": 10}, {"chunk_recall@10": 0.70, "error_count": 0}),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "error_count": 2},
            ),  # too many errors
        ]
        guards = {"min_improvement": 0.02, "max_error_count": 1}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result is None

    def test_filters_by_p95_latency(self):
        """Should filter candidates exceeding max_p95_latency_ms."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "latency_p95_ms": 6000},
            ),  # too slow
        ]
        guards = {"min_improvement": 0.02, "max_p95_latency_ms": 5000}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result is None

    def test_tie_break_by_error_count(self):
        """When delta is equal, should prefer lower error count."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "error_count": 2, "latency_p95_ms": 100},
            ),
            (
                "c2",
                {"rrf_k": 120},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 100},
            ),
        ]
        guards = {"min_improvement": 0.02, "max_error_count": 5}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result["candidate_key"] == "c2"  # lower error count

    def test_tie_break_by_latency(self):
        """When delta and error count are equal, should prefer lower latency."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 200},
            ),
            (
                "c2",
                {"rrf_k": 120},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 150},
            ),
        ]
        guards = {"min_improvement": 0.02}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result["candidate_key"] == "c2"  # lower latency

    def test_tie_break_by_config_fingerprint(self):
        """When all metrics are equal, should use config fingerprint for determinism."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c2",
                {"rrf_k": 120},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 100},
            ),
        ]
        guards = {"min_improvement": 0.02}

        result1 = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )
        result2 = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        # Should be deterministic
        assert result1["candidate_key"] == result2["candidate_key"]

    def test_missing_baseline_returns_none(self):
        """Missing baseline should return None."""
        candidates = [
            ("c1", {"rrf_k": 60}, {"chunk_recall@10": 0.85}),
        ]

        result = select_recommendation(candidates, "baseline", "chunk_recall", 10, {})

        assert result is None

    def test_invalid_baseline_score_returns_none(self):
        """Baseline with invalid score (-1.0) should return None."""
        candidates = [
            ("baseline", {"top_k": 10}, {}),  # no metric
            ("c1", {"rrf_k": 60}, {"chunk_recall@10": 0.85}),
        ]

        result = select_recommendation(candidates, "baseline", "chunk_recall", 10, {})

        assert result is None

    def test_skips_candidates_with_invalid_scores(self):
        """Candidates with invalid scores should be skipped."""
        candidates = [
            ("baseline", {"top_k": 10}, {"chunk_recall@10": 0.70, "error_count": 0}),
            ("c1", {"rrf_k": 60}, {}),  # no metric
            ("c2", {"rrf_k": 120}, {"chunk_recall@10": 0.85, "error_count": 0}),
        ]
        guards = {"min_improvement": 0.02}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result["candidate_key"] == "c2"

    def test_guards_passed_flag(self):
        """Recommendation should always have guards_passed=True."""
        candidates = [
            (
                "baseline",
                {"top_k": 10},
                {"chunk_recall@10": 0.70, "error_count": 0, "latency_p95_ms": 100},
            ),
            (
                "c1",
                {"rrf_k": 60},
                {"chunk_recall@10": 0.85, "error_count": 0, "latency_p95_ms": 100},
            ),
        ]
        guards = {"min_improvement": 0.02}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result["guards_passed"] is True

    def test_returns_config(self):
        """Recommendation should include the winning config."""
        candidates = [
            ("baseline", {"top_k": 10}, {"chunk_recall@10": 0.70, "error_count": 0}),
            (
                "c1",
                {"top_k": 10, "rrf_k": 120},
                {"chunk_recall@10": 0.85, "error_count": 0},
            ),
        ]
        guards = {"min_improvement": 0.02}

        result = select_recommendation(
            candidates, "baseline", "chunk_recall", 10, guards
        )

        assert result["config"]["rrf_k"] == 120
