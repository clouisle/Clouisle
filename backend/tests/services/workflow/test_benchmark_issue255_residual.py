"""Focused residual branch tests for workflow benchmarking (issue #255)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.services.workflow.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkStatus,
    RequestResult,
    WorkflowBenchmark,
)


def _benchmark_result(**overrides) -> BenchmarkResult:
    values = {
        "benchmark_id": "residual",
        "status": BenchmarkStatus.COMPLETED,
        "config": BenchmarkConfig(),
        "start_time": datetime(2026, 1, 1),
    }
    values.update(overrides)
    return BenchmarkResult(**values)


def _request(*, success: bool, error: str | None = None) -> RequestResult:
    now = datetime(2026, 1, 1)
    return RequestResult("request", success, 10, now, now, error=error)


def test_issue255_benchmark_summary_includes_each_recorded_error():
    summary = _benchmark_result(errors={"timeout": 2, "bad input": 1}).to_summary()

    assert "Errors:" in summary
    assert "  timeout: 2" in summary
    assert "  bad input: 1" in summary


@pytest.mark.asyncio
async def test_issue255_benchmark_object_response_keeps_zero_size():
    result = await WorkflowBenchmark()._execute_request(
        "object-response", AsyncMock(return_value=object()), {}, 1
    )

    assert result.success is True
    assert result.response_size == 0


def test_issue255_benchmark_zero_duration_still_counts_errors_without_throughput():
    result = _benchmark_result(
        total_duration_seconds=0,
        results=[_request(success=False, error="failure")],
    )

    WorkflowBenchmark()._calculate_stats(result)

    assert result.requests_per_second == 0
    assert result.bytes_per_second == 0
    assert result.errors == {"failure": 1}


@pytest.mark.asyncio
async def test_issue255_benchmark_scheduler_covers_ramp_rate_progress_and_duration(
    monkeypatch, caplog
):
    caplog.set_level("INFO")
    benchmark = WorkflowBenchmark()
    benchmark_id = "scheduled"
    benchmark._cancel_events[benchmark_id] = asyncio.Event()
    original_sleep = asyncio.sleep

    async def cooperative_sleep(_delay):
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", cooperative_sleep)
    monkeypatch.setattr(asyncio, "Semaphore", asyncio.BoundedSemaphore)
    monkeypatch.setattr(
        benchmark,
        "_execute_request",
        AsyncMock(return_value=_request(success=True)),
    )
    config = BenchmarkConfig(
        concurrent_users=1,
        requests_per_user=100,
        ramp_up_seconds=0.1,
        duration_seconds=0.1,
        requests_per_second=100,
        warmup_requests=0,
    )

    results = await benchmark._run_concurrent(
        benchmark_id, AsyncMock(), lambda: {}, config
    )

    assert results
    assert benchmark._cancel_events[benchmark_id].is_set()
    assert "Progress: 100/100 requests" in caplog.text
