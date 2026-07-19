"""Behavioral tests for workflow execution profiling."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.workflow.profiler import (
    ExecutionProfiler,
    WorkflowProfile,
    compare_profiles,
)


def test_public_lifecycle_measures_nodes_stages_and_summary():
    profiler = ExecutionProfiler("run-1", "workflow-1", "Example")

    with patch(
        "app.services.workflow.profiler.time.time",
        side_effect=[10, 11, 12, 14, 15, 20],
    ):
        profiler.start()
        profiler.start_stage(["node-1"])
        with profiler.node("node-1", "code", "Transform") as node:
            node.retries = 3
            node.tokens_used = 120
            node.cache_hit = True
            node.output_size = 42
        profiler.end_stage()
        profile = profiler.finish()

    assert profile.run_id == "run-1"
    assert profile.workflow_id == "workflow-1"
    assert profile.workflow_name == "Example"
    assert profile.start_time is not None
    assert profile.end_time is not None
    assert profile.total_duration_ms == 10_000

    measured_node = profile.node_profiles["node-1"]
    assert measured_node.duration_ms == 2_000
    assert measured_node.output_size_bytes == 42
    assert profile.stage_profiles[0].duration_ms == 4_000
    assert profile.stage_profiles[0].parallel_nodes == 1

    assert profile.total_nodes == 1
    assert profile.successful_nodes == 1
    assert profile.failed_nodes == 0
    assert profile.cached_nodes == 1
    assert profile.total_tokens == 120
    assert profile.total_retries == 3
    assert profile.cache_hit_rate == 1
    assert profile.slowest_node_id == "node-1"
    assert profile.slowest_node_ms == 2_000
    assert profile.parallel_efficiency == pytest.approx(0.2)
    assert {item["type"] for item in profile.bottlenecks} == {
        "slow_node",
        "high_retries",
        "sequential_bottleneck",
    }
    assert any("optimizing the code" in item for item in profile.suggestions)
    assert any("high retry count" in item for item in profile.suggestions)


def test_recorded_failure_skip_and_serialized_summary():
    profiler = ExecutionProfiler("run-2", "workflow-2")

    with patch(
        "app.services.workflow.profiler.time.time",
        side_effect=[1, 2, 2.25, 3],
    ):
        profiler.start()
        profiler.record_node_start("failed", "http_request")
        profiler.record_node_end("failed", success=False, error="timeout")
        profiler.record_skip("skipped", "condition was false")
        profile = profiler.finish()

    assert profile.failed_nodes == 1
    assert profile.successful_nodes == 0
    assert profile.skipped_nodes == 1
    assert profile.node_profiles["failed"].error == "timeout"

    result = profiler.to_dict()
    assert result["summary"]["failed_nodes"] == 1
    assert result["summary"]["skipped_nodes"] == 1
    assert result["nodes"]["failed"] == {
        "node_type": "http_request",
        "node_label": "",
        "duration_ms": 250,
        "success": False,
        "retries": 0,
        "cache_hit": False,
        "tokens_used": 0,
    }
    assert result["start_time"] is not None
    assert result["end_time"] is not None


@pytest.mark.asyncio
async def test_async_node_context_records_and_propagates_exception():
    profiler = ExecutionProfiler("run", "workflow")

    with (
        patch(
            "app.services.workflow.profiler.time.time",
            side_effect=[4, 5],
        ),
        pytest.raises(ValueError, match="invalid output"),
    ):
        async with profiler.node("node", "code"):
            raise ValueError("invalid output")

    node = profiler._profile.node_profiles["node"]
    assert node.success is False
    assert node.error == "invalid output"
    assert node.duration_ms == 1_000


def test_boundary_calls_are_safe_and_finish_requires_start():
    profiler = ExecutionProfiler("run", "workflow")

    profiler.end_stage()
    profiler.record_node_end("unknown")
    assert profiler.to_dict()["nodes"] == {}
    assert profiler.to_dict()["slowest_node"] is None

    with pytest.raises(AttributeError, match="_start_time"):
        profiler.finish()


def test_empty_run_summary_avoids_division_by_zero():
    profiler = ExecutionProfiler("run", "workflow")

    with patch(
        "app.services.workflow.profiler.time.time",
        side_effect=[10, 10],
    ):
        profiler.start()
        profile = profiler.finish()

    assert profile.total_nodes == 0
    assert profile.cache_hit_rate == 0
    assert profile.parallel_efficiency == 0
    assert profile.slowest_node_id is None
    assert profile.bottlenecks == []


def test_compare_profiles_reports_deltas_and_zero_baseline():
    baseline = WorkflowProfile(
        run_id="before",
        workflow_id="workflow",
        total_duration_ms=0,
        total_tokens=100,
        total_retries=2,
        cache_hit_rate=0.25,
        parallel_efficiency=0.4,
    )
    candidate = WorkflowProfile(
        run_id="after",
        workflow_id="workflow",
        total_duration_ms=750,
        total_tokens=80,
        total_retries=1,
        cache_hit_rate=0.75,
        parallel_efficiency=0.6,
    )

    comparison = compare_profiles(baseline, candidate)

    assert comparison["duration_change_ms"] == 750
    assert comparison["duration_change_pct"] == 0
    assert comparison["token_change"] == -20
    assert comparison["retry_change"] == -1
    assert comparison["cache_hit_rate_change"] == 0.5
    assert comparison["efficiency_change"] == pytest.approx(0.2)
    assert comparison["profile1"]["run_id"] == "before"
    assert comparison["profile2"]["run_id"] == "after"
