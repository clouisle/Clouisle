"""Response-only run comparison service for retrieval evaluation."""

from typing import Literal
from uuid import UUID


class ComparisonResult:
    """Result of comparing two evaluation runs."""

    def __init__(
        self,
        baseline_id: UUID,
        candidate_id: UUID,
        comparable: bool,
        incompatibility_reason: str | None,
        metric_deltas: dict[str, float],
        improved_cases: int,
        unchanged_cases: int,
        regressed_cases: int,
        unpaired_cases: int,
        case_deltas: list[dict],
        config_diff: dict,
    ):
        self.baseline_id = baseline_id
        self.candidate_id = candidate_id
        self.comparable = comparable
        self.incompatibility_reason = incompatibility_reason
        self.metric_deltas = metric_deltas
        self.improved_cases = improved_cases
        self.unchanged_cases = unchanged_cases
        self.regressed_cases = regressed_cases
        self.unpaired_cases = unpaired_cases
        self.case_deltas = case_deltas
        self.config_diff = config_diff


def compare_runs(baseline_run: dict, candidate_run: dict) -> ComparisonResult:
    """
    Compare two evaluation runs and return structured comparison result.

    Args:
        baseline_run: Baseline run with case_results
        candidate_run: Candidate run with case_results

    Returns:
        ComparisonResult with comparison details
    """
    baseline_id = baseline_run["id"]
    candidate_id = candidate_run["id"]

    # Check comparability
    comparable, reason = _check_comparability(baseline_run, candidate_run)

    # Extract config diff
    config_diff = _compute_config_diff(
        baseline_run.get("config_snapshot", {}),
        candidate_run.get("config_snapshot", {}),
    )

    # Compute metric deltas
    baseline_metrics = baseline_run.get("summary_metrics") or {}
    candidate_metrics = candidate_run.get("summary_metrics") or {}
    metric_deltas = _compute_metric_deltas(baseline_metrics, candidate_metrics)

    # Compute case-level deltas
    case_deltas, improved, unchanged, regressed, unpaired = _compute_case_deltas(
        baseline_run.get("case_results", []),
        candidate_run.get("case_results", []),
    )

    return ComparisonResult(
        baseline_id=baseline_id,
        candidate_id=candidate_id,
        comparable=comparable,
        incompatibility_reason=reason,
        metric_deltas=metric_deltas,
        improved_cases=improved,
        unchanged_cases=unchanged,
        regressed_cases=regressed,
        unpaired_cases=unpaired,
        case_deltas=case_deltas,
        config_diff=config_diff,
    )


def _check_comparability(baseline: dict, candidate: dict) -> tuple[bool, str | None]:
    """
    Check if two runs are comparable.

    Returns:
        (comparable, reason) tuple
    """
    # Must be from same dataset
    if baseline.get("dataset_id") != candidate.get("dataset_id"):
        return False, "Runs are from different datasets"

    # Check if dataset revision/hash match
    baseline_version = baseline.get("version_snapshot", {})
    candidate_version = candidate.get("version_snapshot", {})

    baseline_revision = baseline_version.get("dataset_revision")
    candidate_revision = candidate_version.get("dataset_revision")

    if baseline_revision is not None and candidate_revision is not None:
        if baseline_revision != candidate_revision:
            return (
                False,
                f"Dataset revision mismatch: baseline={baseline_revision}, candidate={candidate_revision}",
            )

    baseline_hash = baseline_version.get("dataset_snapshot_hash")
    candidate_hash = candidate_version.get("dataset_snapshot_hash")

    if baseline_hash and candidate_hash:
        if baseline_hash != candidate_hash:
            return False, "Dataset snapshot hash mismatch"

    # Check metric_k consistency if present
    baseline_metric_k = baseline.get("metric_k")
    candidate_metric_k = candidate.get("metric_k")

    if baseline_metric_k is not None and candidate_metric_k is not None:
        if baseline_metric_k != candidate_metric_k:
            return (
                False,
                f"Metric K mismatch: baseline={baseline_metric_k}, candidate={candidate_metric_k}",
            )

    return True, None


def _compute_config_diff(baseline_config: dict, candidate_config: dict) -> dict:
    """Compute config differences between baseline and candidate."""
    diff = {}

    all_keys = set(baseline_config.keys()) | set(candidate_config.keys())
    for key in all_keys:
        baseline_value = baseline_config.get(key)
        candidate_value = candidate_config.get(key)

        if baseline_value != candidate_value:
            diff[key] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
            }

    return diff


def _compute_metric_deltas(
    baseline_metrics: dict, candidate_metrics: dict
) -> dict[str, float]:
    """Compute delta for each metric."""
    deltas = {}

    # Metrics to compare
    metric_keys = [
        "chunk_recall_mean",
        "chunk_mrr_mean",
        "chunk_ndcg_mean",
        "document_recall_mean",
        "document_mrr_mean",
        "document_ndcg_mean",
        "expected_empty_accuracy",
        "latency_p50_ms",
        "latency_p95_ms",
        "error_count",
    ]

    for key in metric_keys:
        baseline_value = baseline_metrics.get(key)
        candidate_value = candidate_metrics.get(key)

        if baseline_value is not None and candidate_value is not None:
            deltas[key] = candidate_value - baseline_value

    return deltas


def _compute_case_deltas(
    baseline_results: list[dict],
    candidate_results: list[dict],
) -> tuple[list[dict], int, int, int, int]:
    """
    Compute per-case deltas and categorize outcomes.

    Returns:
        (case_deltas, improved_count, unchanged_count, regressed_count, unpaired_count)
    """
    # Index by case_snapshot.id (immutable) or case_id (fallback for old data)
    baseline_map = {}
    for result in baseline_results:
        snapshot = result.get("case_snapshot", {})
        case_key = snapshot.get("id") or result.get("case_id")
        if case_key:
            baseline_map[str(case_key)] = result

    candidate_map = {}
    for result in candidate_results:
        snapshot = result.get("case_snapshot", {})
        case_key = snapshot.get("id") or result.get("case_id")
        if case_key:
            candidate_map[str(case_key)] = result

    case_deltas = []
    improved = 0
    unchanged = 0
    regressed = 0
    unpaired = 0

    # Compare paired cases
    all_case_keys = set(baseline_map.keys()) | set(candidate_map.keys())

    for case_key in all_case_keys:
        baseline_result = baseline_map.get(case_key)
        candidate_result = candidate_map.get(case_key)

        if not baseline_result or not candidate_result:
            unpaired += 1
            continue

        # Extract primary metric (chunk_ndcg by default)
        baseline_metrics = baseline_result.get("metrics", {})
        candidate_metrics = candidate_result.get("metrics", {})

        baseline_score = baseline_metrics.get("chunk_ndcg")
        candidate_score = candidate_metrics.get("chunk_ndcg")

        if baseline_score is None or candidate_score is None:
            unpaired += 1
            continue

        delta = candidate_score - baseline_score
        outcome: Literal["improved", "unchanged", "regressed"]

        if delta > 0.01:  # Improvement threshold
            outcome = "improved"
            improved += 1
        elif delta < -0.01:  # Regression threshold
            outcome = "regressed"
            regressed += 1
        else:
            outcome = "unchanged"
            unchanged += 1

        case_deltas.append(
            {
                "case_id": case_key,
                "query": baseline_result.get("case_snapshot", {}).get("query", ""),
                "baseline_score": baseline_score,
                "candidate_score": candidate_score,
                "delta": delta,
                "outcome": outcome,
            }
        )

    return case_deltas, improved, unchanged, regressed, unpaired
