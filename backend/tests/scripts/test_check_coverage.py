import json

import pytest

from scripts.check_coverage import check_coverage, coverage_percent


def write_report(tmp_path, *, covered_lines=95, covered_branches=95):
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "covered_lines": covered_lines,
                    "num_statements": 100,
                    "covered_branches": covered_branches,
                    "num_branches": 100,
                }
            }
        )
    )
    return report


def test_check_coverage_accepts_independent_metrics_at_threshold(tmp_path):
    check_coverage(write_report(tmp_path))


@pytest.mark.parametrize(("covered_lines", "covered_branches"), [(94, 95), (95, 94)])
def test_check_coverage_rejects_either_metric_below_threshold(
    tmp_path, covered_lines, covered_branches
):
    with pytest.raises(SystemExit):
        check_coverage(
            write_report(
                tmp_path,
                covered_lines=covered_lines,
                covered_branches=covered_branches,
            )
        )


def test_coverage_percent_handles_empty_denominator():
    assert coverage_percent(0, 0) == 100
