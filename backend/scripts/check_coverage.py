"""Enforce independent backend line and branch coverage thresholds."""

import json
from pathlib import Path

MINIMUM_PERCENT = 95.0


def coverage_percent(covered: int, total: int) -> float:
    return 100.0 if total == 0 else 100 * covered / total


def check_coverage(report_path: Path, minimum: float = MINIMUM_PERCENT) -> None:
    totals = json.loads(report_path.read_text())["totals"]
    metrics = {
        "line": coverage_percent(totals["covered_lines"], totals["num_statements"]),
        "branch": coverage_percent(totals["covered_branches"], totals["num_branches"]),
    }
    failed = False
    for name, percent in metrics.items():
        print(f"Backend {name} coverage: {percent:.2f}% (required: {minimum:.2f}%)")
        failed |= percent < minimum
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    check_coverage(Path("coverage.json"))
