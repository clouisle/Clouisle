import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.workflow.benchmark import (
    BenchmarkConfig,
    LatencyHistogram,
    WorkflowBenchmark,
    compare_benchmarks,
    get_benchmark,
)


@pytest.mark.asyncio
async def test_run_concurrent_pre_cancelled_rate_limited_workers_skip_executor(
    monkeypatch,
):
    benchmark = WorkflowBenchmark()
    benchmark_id = "pre_cancelled"
    cancel_event = asyncio.Event()
    cancel_event.set()
    benchmark._cancel_events[benchmark_id] = cancel_event
    executor = AsyncMock(return_value="unused")
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)

    results = await benchmark._run_concurrent(
        benchmark_id=benchmark_id,
        executor=executor,
        inputs_generator=lambda: {"value": 1},
        config=BenchmarkConfig(
            concurrent_users=2,
            requests_per_user=3,
            ramp_up_seconds=4,
            requests_per_second=1,
            warmup_requests=0,
        ),
    )

    assert results == []
    executor.assert_not_awaited()
    assert sleep.await_count == 1


@pytest.mark.asyncio
async def test_compare_benchmarks_reuses_config_and_get_benchmark_singleton(capsys):
    config = BenchmarkConfig(
        concurrent_users=1,
        requests_per_user=1,
        ramp_up_seconds=0,
        warmup_requests=0,
    )

    async def fast(inputs):
        return inputs

    results = await compare_benchmarks(
        {"fast": fast},
        inputs_generator=lambda: {"ok": True},
        config=config,
    )

    assert list(results) == ["fast"]
    assert results["fast"].config is config
    assert results["fast"].total_requests == 1
    assert "Benchmark Comparison" in capsys.readouterr().out
    assert get_benchmark() is get_benchmark()


def test_latency_histogram_empty_bucket_and_overflow_paths():
    histogram = LatencyHistogram(buckets=[10, 20])

    assert histogram.get_percentile(0.95) == 0

    histogram.observe(5)
    histogram.observe(25)

    assert histogram.get_distribution() == {
        "<=10ms": 1,
        "<=20ms": -1,
        ">20ms": 1,
    }
    assert histogram.get_percentile(0.5) == 10
    assert histogram.get_percentile(1.0) == 20
