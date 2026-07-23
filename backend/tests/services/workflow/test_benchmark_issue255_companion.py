import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

import app.services.workflow.benchmark as benchmark_module
from app.services.workflow.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkStatus,
    LatencyHistogram,
    RequestResult,
    WorkflowBenchmark,
    compare_benchmarks,
    get_benchmark,
    run_quick_benchmark,
)


def request_result(
    request_id: str,
    *,
    success: bool = True,
    duration_ms: float = 10,
    error: str | None = None,
    response_size: int = 0,
) -> RequestResult:
    start = datetime(2026, 1, 1)
    return RequestResult(
        request_id=request_id,
        success=success,
        duration_ms=duration_ms,
        start_time=start,
        end_time=start + timedelta(milliseconds=duration_ms),
        error=error,
        response_size=response_size,
    )


@pytest.mark.asyncio
async def test_run_performs_warmup_collects_requests_and_cleans_up():
    calls = 0

    async def executor(inputs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("ignored warmup failure")
        return inputs

    benchmark = WorkflowBenchmark()
    result = await benchmark.run(
        "smoke",
        executor,
        lambda: {"value": calls},
        BenchmarkConfig(
            concurrent_users=2,
            requests_per_user=2,
            ramp_up_seconds=0,
            warmup_requests=2,
        ),
    )

    assert result.status is BenchmarkStatus.COMPLETED
    assert result.total_requests == 4
    assert result.successful_requests == 4
    assert calls == 6
    assert result.end_time is not None
    assert benchmark.get_running() == []
    assert await benchmark.cancel(result.benchmark_id) is False


@pytest.mark.asyncio
async def test_run_honors_max_requests():
    executor = AsyncMock(return_value="ok")

    result = await WorkflowBenchmark().run(
        "limited",
        executor,
        dict,
        BenchmarkConfig(
            concurrent_users=3,
            requests_per_user=4,
            ramp_up_seconds=0,
            max_requests=5,
            warmup_requests=0,
        ),
    )

    assert result.total_requests == 5
    assert executor.await_count == 5
    assert {item.request_id.split("_u", 1)[0] for item in result.results} == {
        result.benchmark_id
    }


@pytest.mark.asyncio
async def test_run_records_setup_failure_and_cleans_up(monkeypatch):
    benchmark = WorkflowBenchmark()
    monkeypatch.setattr(
        benchmark,
        "_run_concurrent",
        AsyncMock(side_effect=ValueError("bad inputs")),
    )

    result = await benchmark.run(
        "broken",
        AsyncMock(),
        dict,
        BenchmarkConfig(warmup_requests=0, ramp_up_seconds=0),
    )

    assert result.status is BenchmarkStatus.FAILED
    assert result.errors == {"benchmark_error": "bad inputs"}
    assert result.end_time is not None
    assert benchmark.get_status(result.benchmark_id) is None


@pytest.mark.asyncio
async def test_run_converts_task_cancellation_to_cancelled_result(monkeypatch):
    benchmark = WorkflowBenchmark()
    monkeypatch.setattr(
        benchmark,
        "_run_concurrent",
        AsyncMock(side_effect=asyncio.CancelledError),
    )

    result = await benchmark.run(
        "cancelled",
        AsyncMock(),
        dict,
        BenchmarkConfig(warmup_requests=0),
    )

    assert result.status is BenchmarkStatus.CANCELLED
    assert result.end_time is not None
    assert benchmark.get_running() == []


@pytest.mark.asyncio
async def test_cancel_and_status_report_in_progress_results():
    benchmark = WorkflowBenchmark()
    result = BenchmarkResult(
        benchmark_id="active",
        status=BenchmarkStatus.RUNNING,
        config=BenchmarkConfig(),
        start_time=datetime.utcnow(),
        results=[request_result("ok"), request_result("bad", success=False)],
    )
    benchmark._running_benchmarks["active"] = result
    benchmark._cancel_events["active"] = asyncio.Event()

    status = benchmark.get_status("active")

    assert status is not None
    assert status["requests_completed"] == 2
    assert status["successful"] == 1
    assert status["failed"] == 1
    assert status["elapsed_seconds"] >= 0
    assert await benchmark.cancel("active") is True
    assert benchmark._cancel_events["active"].is_set()
    assert benchmark.get_status("missing") is None


@pytest.mark.asyncio
async def test_execute_request_handles_sizes_failures_and_timeout():
    benchmark = WorkflowBenchmark()

    text = await benchmark._execute_request(
        "text", AsyncMock(return_value="abc"), {}, 1
    )
    mapping = await benchmark._execute_request(
        "mapping", AsyncMock(return_value={"a": 1}), {}, 1
    )
    failed = await benchmark._execute_request(
        "failed", AsyncMock(side_effect=RuntimeError("boom")), {}, 1
    )

    async def blocked(_inputs):
        await asyncio.sleep(1)

    timed_out = await benchmark._execute_request("timeout", blocked, {}, 0.001)

    assert text.success is True and text.response_size == 3
    assert mapping.success is True and mapping.response_size == len('{"a": 1}')
    assert failed.success is False and failed.error == "boom"
    assert timed_out.success is False and timed_out.error == "timeout"


def test_calculate_stats_uses_successful_latencies_and_groups_errors():
    benchmark = WorkflowBenchmark()
    result = BenchmarkResult(
        benchmark_id="stats",
        status=BenchmarkStatus.RUNNING,
        config=BenchmarkConfig(),
        start_time=datetime(2026, 1, 1),
        total_duration_seconds=2,
        results=[
            request_result("one", duration_ms=10, response_size=20),
            request_result("two", duration_ms=30, response_size=40),
            request_result("three", success=False, duration_ms=100, error="x" * 60),
            request_result("four", success=False, error="x" * 60),
        ],
    )

    benchmark._calculate_stats(result)

    assert (
        result.total_requests,
        result.successful_requests,
        result.failed_requests,
    ) == (
        4,
        2,
        2,
    )
    assert (result.min_latency, result.max_latency) == (10, 30)
    assert result.mean_latency == result.median_latency == 20
    assert result.stddev_latency == pytest.approx(14.1421356)
    assert (result.p90_latency, result.p95_latency, result.p99_latency) == (30, 30, 30)
    assert result.requests_per_second == 1
    assert result.bytes_per_second == 30
    assert result.errors == {"x" * 50: 2}


def test_result_serialization_summary_and_empty_stats():
    result = BenchmarkResult(
        benchmark_id="serial",
        status=BenchmarkStatus.COMPLETED,
        config=BenchmarkConfig(concurrent_users=1),
        start_time=datetime(2026, 1, 1),
        successful_requests=1,
        total_requests=2,
        failed_requests=1,
        errors={"boom": 1},
        results=[request_result("one")],
    )

    compact = result.to_dict()
    detailed = result.to_dict(include_raw=True)
    summary = result.to_summary()

    assert compact["requests"]["success_rate"] == 0.5
    assert "raw_results" not in compact
    assert detailed["raw_results"][0]["request_id"] == "one"
    assert "Successful: 1 (50.0%)" in summary
    assert "boom: 1" in summary

    empty = BenchmarkResult(
        benchmark_id="empty",
        status=BenchmarkStatus.RUNNING,
        config=BenchmarkConfig(),
        start_time=datetime.utcnow(),
    )
    WorkflowBenchmark()._calculate_stats(empty)
    assert empty.total_requests == 0


@pytest.mark.asyncio
async def test_quick_benchmark_returns_basic_statistics(monkeypatch):
    run = AsyncMock(
        return_value=BenchmarkResult(
            benchmark_id="quick",
            status=BenchmarkStatus.COMPLETED,
            config=BenchmarkConfig(),
            start_time=datetime.utcnow(),
            total_requests=4,
            successful_requests=3,
            mean_latency=12,
            p95_latency=20,
            requests_per_second=8,
        )
    )
    monkeypatch.setattr(WorkflowBenchmark, "run", run)
    inputs = {"query": "hello"}

    stats = await run_quick_benchmark(AsyncMock(), inputs, iterations=4)

    assert stats == {
        "iterations": 4,
        "success_rate": 0.75,
        "mean_latency_ms": 12,
        "p95_latency_ms": 20,
        "requests_per_second": 8,
    }
    config = run.await_args.kwargs["config"]
    assert config.concurrent_users == 1
    assert config.requests_per_user == 4
    assert run.await_args.kwargs["inputs_generator"]() is inputs


@pytest.mark.asyncio
async def test_compare_benchmarks_runs_each_executor(monkeypatch, capsys):
    first = BenchmarkResult(
        benchmark_id="first",
        status=BenchmarkStatus.COMPLETED,
        config=BenchmarkConfig(),
        start_time=datetime.utcnow(),
        total_requests=2,
        successful_requests=2,
        requests_per_second=4,
    )
    second = BenchmarkResult(
        benchmark_id="second",
        status=BenchmarkStatus.COMPLETED,
        config=BenchmarkConfig(),
        start_time=datetime.utcnow(),
    )
    run = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(WorkflowBenchmark, "run", run)

    results = await compare_benchmarks(
        {"first": AsyncMock(), "second": AsyncMock()}, dict
    )

    assert results == {"first": first, "second": second}
    assert [call.kwargs["name"] for call in run.await_args_list] == ["first", "second"]
    assert "Benchmark Comparison" in capsys.readouterr().out


def test_histogram_and_global_accessor(monkeypatch):
    histogram = LatencyHistogram([10, 20])
    for latency in (5, 15, 15, 30):
        histogram.observe(latency)

    assert histogram.get_distribution() == {"<=10ms": 1, "<=20ms": 1, ">20ms": 1}
    assert histogram.get_percentile(0.5) == 20
    assert histogram.get_percentile(1) == 20
    assert LatencyHistogram([10]).get_percentile(0.5) == 0

    monkeypatch.setattr(benchmark_module, "_benchmark", None)
    assert get_benchmark() is get_benchmark()
