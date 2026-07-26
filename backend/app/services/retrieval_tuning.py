"""Pure functions for retrieval parameter tuning.

All functions here are IO-free and deterministic for easy testing.
Actual execution orchestration lives in tasks/retrieval_tuning.py.
"""

import hashlib
import json
from typing import Any, Literal


ObjectiveMetric = Literal[
    "chunk_recall",
    "chunk_mrr",
    "chunk_ndcg",
    "document_recall",
    "document_mrr",
    "document_ndcg",
]


def normalize_space(
    space: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, list[Any]]:
    """Normalize parameter space to explicit axis → candidates mapping."""
    default_space = {
        "channel_weights": [
            (1.0, 0.3),
            (1.0, 0.6),
            (1.0, 1.0),
            (0.6, 1.0),
            (0.3, 1.0),
        ],
        "rrf_k": [20, 60, 120],
        "rerank_config": [
            {"enabled": False},
            {"enabled": True, "candidate_k": 20},
            {"enabled": True, "candidate_k": 50},
        ],
        "rerank_score_threshold": [None, 0.1, 0.3],
        "score_threshold": [0, 0.2, 0.35],
    }

    normalized = {}
    for axis, default_candidates in default_space.items():
        user_candidates = space.get(axis, default_candidates)
        if not isinstance(user_candidates, list):
            user_candidates = [user_candidates]
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for candidate in user_candidates:
            key = (
                json.dumps(candidate, sort_keys=True)
                if isinstance(candidate, dict)
                else candidate
            )
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
        normalized[axis] = unique if unique else [baseline.get(axis)]

    return normalized


def candidate_key(stage: str, axis: str, value: Any) -> str:
    """Generate deterministic candidate key for idempotent child run creation."""
    value_str = (
        json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value)
    )
    return f"{stage}:{axis}={value_str}"


def expand_stage(
    stage: str,
    axis: str,
    candidates: list[Any],
    parent_config: dict[str, Any],
    metric_k: int,
    serving_top_k: int,
) -> list[tuple[str, str, dict[str, Any]]]:
    """Expand one stage's candidates into (key, label, config) tuples.

    Returns:
        List of (candidate_key, label, config) tuples
    """
    results = []
    for value in candidates:
        config = parent_config.copy()
        key = candidate_key(stage, axis, value)

        if axis == "channel_weights":
            dense_weight, lexical_weight = value
            config["dense_weight"] = dense_weight
            config["lexical_weight"] = lexical_weight
            label = f"D{dense_weight}×L{lexical_weight}"
        elif axis == "rrf_k":
            config["rrf_k"] = value
            label = f"rrf_k={value}"
        elif axis == "rerank_config":
            config["rerank_enabled"] = value["enabled"]
            if value["enabled"]:
                config["rerank_candidate_k"] = value["candidate_k"]
                label = f"rerank@{value['candidate_k']}"
            else:
                label = "rerank=off"
        elif axis == "rerank_score_threshold":
            if config.get("rerank_enabled"):
                config["rerank_score_threshold"] = value
                label = (
                    f"rerank_thresh={value}"
                    if value is not None
                    else "rerank_thresh=none"
                )
            else:
                continue  # Skip threshold candidates when rerank is off
        elif axis == "score_threshold":
            config["score_threshold"] = value
            label = f"score_thresh={value}"
        else:
            continue

        # Clamp top_k to metric_k minimum
        if config.get("top_k", serving_top_k) < metric_k:
            config["top_k"] = metric_k

        results.append((key, label, config))

    return results


def expand_space(
    space: dict[str, list[Any]],
    baseline: dict[str, Any],
    metric_k: int,
    serving_top_k: int,
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Expand parameter space into staged coordinate search candidates.

    Returns:
        List of (stage, candidate_key, label, config) tuples in execution order.
        First tuple is always ("baseline", "baseline", "baseline", baseline_config).
    """
    stages = [
        ("s1_weights", "channel_weights"),
        ("s2_rrf", "rrf_k"),
        ("s3_rerank", "rerank_config"),
        ("s4_rerank_thresh", "rerank_score_threshold"),
        ("s5_score_thresh", "score_threshold"),
    ]

    baseline_with_top_k = baseline.copy()
    baseline_with_top_k["top_k"] = max(baseline.get("top_k", serving_top_k), metric_k)

    all_candidates = [("baseline", "baseline", "baseline", baseline_with_top_k)]
    current_best = baseline_with_top_k

    for stage_name, axis in stages:
        candidates = space.get(axis, [])
        if not candidates:
            continue

        stage_candidates = expand_stage(
            stage_name, axis, candidates, current_best, metric_k, serving_top_k
        )

        if stage_candidates:
            all_candidates.extend(
                (stage_name, key, label, config)
                for key, label, config in stage_candidates
            )
            # For staged search, current_best would be updated after each stage completes
            # But for estimation/expansion, we just use the baseline for all stages
            # The actual "pick best and continue" logic lives in the orchestrator

    return all_candidates


def config_fingerprint(config: dict[str, Any]) -> str:
    """Generate stable fingerprint for config comparison."""
    canonical = json.dumps(config, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def score_run(
    summary: dict[str, Any],
    objective: ObjectiveMetric,
    metric_k: int,
) -> float:
    """Extract objective metric score from run summary.

    Returns:
        Objective metric value, or -1.0 if not available (e.g., no graded cases).
    """
    metric_key = f"{objective}@{metric_k}"
    return summary.get(metric_key, -1.0)


def compare_runs(
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    objective: ObjectiveMetric,
    metric_k: int,
) -> tuple[int, int, float]:
    """Compare two run summaries at case level.

    Returns:
        (improved_count, regressed_count, mean_delta)
    """
    baseline_score = score_run(baseline_summary, objective, metric_k)
    candidate_score = score_run(candidate_summary, objective, metric_k)

    # For now, use summary-level comparison
    # TODO: Implement per-case comparison when case_results are available
    delta = candidate_score - baseline_score

    if delta > 0.01:
        return (1, 0, delta)
    elif delta < -0.01:
        return (0, 1, delta)
    else:
        return (0, 0, delta)


def select_recommendation(
    candidates: list[tuple[str, dict[str, Any], dict[str, Any]]],
    baseline_key: str,
    objective: ObjectiveMetric,
    metric_k: int,
    guards: dict[str, Any],
) -> dict[str, Any] | None:
    """Select best candidate that passes all guards.

    Args:
        candidates: List of (candidate_key, config, summary) tuples
        baseline_key: Key of the baseline run
        objective: Target metric
        metric_k: Metric computation depth
        guards: Guard thresholds (min_improvement, max_error_count, max_p95_latency_ms, etc.)

    Returns:
        Recommendation dict with config, evidence, and reasoning, or None if no improvement.
    """
    min_improvement = guards.get("min_improvement", 0.01)
    max_error_count = guards.get("max_error_count", 0)
    max_p95_latency_ms = guards.get("max_p95_latency_ms", 5000)

    baseline = next((s for k, c, s in candidates if k == baseline_key), None)
    if not baseline:
        return None

    baseline_score = score_run(baseline, objective, metric_k)
    if baseline_score < 0:
        return None  # No valid baseline score

    # Filter and score candidates
    viable = []
    for key, config, summary in candidates:
        if key == baseline_key:
            continue

        score = score_run(summary, objective, metric_k)
        if score < 0:
            continue  # Skip runs without valid scores

        delta = score - baseline_score
        if delta < min_improvement:
            continue  # Insufficient improvement

        error_count = summary.get("error_count", 0)
        if error_count > max_error_count:
            continue  # Too many errors

        p95_latency = summary.get("latency_p95_ms", 0)
        if p95_latency > max_p95_latency_ms:
            continue  # Latency too high

        # TODO: Add improved_cases > regressed_cases check when per-case data available

        viable.append((key, config, summary, score, delta))

    if not viable:
        return None  # No candidate passes guards

    # Sort by: delta desc, error_count asc, p95 asc, config fingerprint (for determinism)
    viable.sort(
        key=lambda x: (
            -x[4],  # delta descending
            x[2].get("error_count", 0),  # error count ascending
            x[2].get("latency_p95_ms", 0),  # p95 ascending
            config_fingerprint(x[1]),  # config fingerprint for tie-break
        )
    )

    best_key, best_config, best_summary, best_score, best_delta = viable[0]

    return {
        "config": best_config,
        "candidate_key": best_key,
        "objective_value": best_score,
        "delta": best_delta,
        "baseline_value": baseline_score,
        "guards_passed": True,
    }
