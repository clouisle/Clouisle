import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.workflow import benchmark as benchmark_module
from app.services.workflow.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkStatus,
    RequestResult,
    WorkflowBenchmark,
)


@pytest.mark.asyncio
async def test_execute_request_sizes_timeout_and_exception_branches(monkeypatch):
    bench = WorkflowBenchmark()
    ticks = iter([0, 2_000_000, 5_000_000, 9_000_000, 10_000_000, 16_000_000])
    monkeypatch.setattr(benchmark_module.time, "perf_counter_ns", lambda: next(ticks))

    async def returns_bytes(_inputs):
        return b"abc"

    bytes_result = await bench._execute_request("bytes", returns_bytes, {}, 1)
    assert bytes_result.success is True
    assert bytes_result.response_size == 3
    assert bytes_result.duration_ms == 2

    async def times_out(_inputs):
        raise asyncio.TimeoutError

    timeout_result = await bench._execute_request("timeout", times_out, {}, 1)
    assert timeout_result.success is False
    assert timeout_result.error == "timeout"

    async def fails(_inputs):
        raise ValueError("bad input")

    failed_result = await bench._execute_request("failed", fails, {}, 1)
    assert failed_result.success is False
    assert failed_result.error == "bad input"


def test_status_cancel_and_stats_empty_failed_only_and_single_latency():
    bench = WorkflowBenchmark()
    assert bench.get_running() == []
    assert bench.get_status("missing") is None
    assert asyncio.run(bench.cancel("missing")) is False

    benchmark_id = "running"
    bench._cancel_events[benchmark_id] = asyncio.Event()
    bench._running_benchmarks[benchmark_id] = BenchmarkResult(
        benchmark_id=benchmark_id,
        status=BenchmarkStatus.RUNNING,
        config=BenchmarkConfig(),
        start_time=datetime.utcnow() - timedelta(seconds=1),
        results=[
            RequestResult("ok", True, 7, datetime.utcnow(), datetime.utcnow()),
            RequestResult("bad", False, 3, datetime.utcnow(), datetime.utcnow()),
        ],
    )

    status = bench.get_status(benchmark_id)
    assert status is not None
    assert status["successful"] == 1
    assert status["failed"] == 1
    assert bench.get_running() == [benchmark_id]
    assert asyncio.run(bench.cancel(benchmark_id)) is True
    assert bench._cancel_events[benchmark_id].is_set()

    empty = BenchmarkResult(
        "empty", BenchmarkStatus.RUNNING, BenchmarkConfig(), datetime.utcnow()
    )
    bench._calculate_stats(empty)
    assert empty.total_requests == 0

    failed_only = BenchmarkResult(
        "failed-only",
        BenchmarkStatus.RUNNING,
        BenchmarkConfig(),
        datetime.utcnow(),
        total_duration_seconds=2,
        results=[
            RequestResult(
                "f1", False, 4, datetime.utcnow(), datetime.utcnow(), error="x" * 80
            ),
            RequestResult(
                "f2", False, 5, datetime.utcnow(), datetime.utcnow(), error="x" * 80
            ),
        ],
    )
    bench._calculate_stats(failed_only)
    assert failed_only.total_requests == 2
    assert failed_only.requests_per_second == 0
    assert failed_only.errors == {"x" * 50: 2}

    one_success = BenchmarkResult(
        "one-success",
        BenchmarkStatus.RUNNING,
        BenchmarkConfig(),
        datetime.utcnow(),
        total_duration_seconds=4,
        results=[
            RequestResult(
                "s", True, 11, datetime.utcnow(), datetime.utcnow(), response_size=8
            )
        ],
    )
    bench._calculate_stats(one_success)
    assert one_success.stddev_latency == 0
    assert one_success.requests_per_second == 0.25
    assert one_success.bytes_per_second == 2


@pytest.mark.asyncio
async def test_run_concurrent_max_requests_ramp_progress_and_duration(monkeypatch):
    bench = WorkflowBenchmark()
    benchmark_id = "matrix"
    bench._cancel_events[benchmark_id] = asyncio.Event()
    sleep_calls = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)
        if delay == 0.01:
            bench._cancel_events[benchmark_id].set()

    monkeypatch.setattr(benchmark_module.asyncio, "sleep", fake_sleep)

    async def executor(inputs):
        return inputs

    results = await bench._run_concurrent(
        benchmark_id,
        executor,
        lambda: {"payload": "x"},
        BenchmarkConfig(
            concurrent_users=2,
            requests_per_user=3,
            ramp_up_seconds=0.2,
            duration_seconds=0.01,
            max_requests=3,
            warmup_requests=0,
        ),
    )

    assert len(results) <= 3
    assert any(delay > 0 for delay in sleep_calls)
    assert bench._cancel_events[benchmark_id].is_set()


@pytest.mark.asyncio
async def test_run_records_default_config_warmup_failure_and_run_failure(monkeypatch):
    bench = WorkflowBenchmark()
    monkeypatch.setattr(
        bench,
        "_run_concurrent",
        AsyncMock(side_effect=RuntimeError("runner exploded")),
    )

    async def warmup_fails(_inputs):
        raise RuntimeError("ignored warmup")

    result = await bench.run("default", warmup_fails, lambda: {"x": 1})

    assert result.status is BenchmarkStatus.FAILED
    assert result.errors == {"benchmark_error": "runner exploded"}
    assert result.end_time is not None
    assert bench.get_running() == []


@pytest.mark.asyncio
async def test_run_quick_and_compare_reuse_benchmark_paths(monkeypatch, capsys):
    async def fake_run(self, name, executor, inputs_generator, config=None):
        await executor(inputs_generator())
        result = BenchmarkResult(
            benchmark_id=name,
            status=BenchmarkStatus.COMPLETED,
            config=config or BenchmarkConfig(),
            start_time=datetime.utcnow(),
            total_duration_seconds=1,
            total_requests=2,
            successful_requests=1,
            mean_latency=12,
            p95_latency=15,
            requests_per_second=1,
        )
        return result

    monkeypatch.setattr(WorkflowBenchmark, "run", fake_run)

    async def executor(inputs):
        return {"seen": inputs}

    quick = await benchmark_module.run_quick_benchmark(executor, {"q": 1}, iterations=2)
    assert quick == {
        "iterations": 2,
        "success_rate": 0.5,
        "mean_latency_ms": 12,
        "p95_latency_ms": 15,
        "requests_per_second": 1,
    }

    compared = await benchmark_module.compare_benchmarks(
        {"a": executor, "b": executor}, lambda: {"q": 2}
    )
    assert list(compared) == ["a", "b"]
    assert "Benchmark Comparison" in capsys.readouterr().out


def test_endpoint_benchmark_wrappers_return_running_cancelled_and_missing(monkeypatch):
    from app.api.v1.endpoints import workflows

    if not all(
        hasattr(workflows, name)
        for name in (
            "start_benchmark",
            "list_benchmarks",
            "get_benchmark_status",
            "cancel_benchmark",
        )
    ):
        pytest.skip("benchmark endpoints are not present in this branch")

    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    added = []
    runner = AsyncMock()
    fake_benchmark = SimpleNamespace(
        get_running=lambda: ["bench-1", "bench-2"],
        get_status=lambda benchmark_id: (
            {"benchmark_id": benchmark_id, "status": "running"}
            if benchmark_id == "bench-1"
            else None
        ),
        cancel=AsyncMock(return_value=False),
    )
    monkeypatch.setattr(workflows, "get_benchmark", lambda: fake_benchmark)
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(id=workflow_id)),
    )

    class BackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            added.append((func, args, kwargs))

    response = asyncio.run(
        workflows.start_benchmark(
            workflow_id, BackgroundTasks(), user, runner, iterations=4
        )
    )
    assert response["message"]
    assert added

    assert asyncio.run(workflows.list_benchmarks(user)) == {
        "running_benchmarks": ["bench-1", "bench-2"]
    }
    assert (
        asyncio.run(workflows.get_benchmark_status("bench-1", user))["status"]
        == "running"
    )

    with pytest.raises(Exception):
        asyncio.run(workflows.get_benchmark_status("missing", user))

    with pytest.raises(Exception):
        asyncio.run(workflows.cancel_benchmark("missing", user))
