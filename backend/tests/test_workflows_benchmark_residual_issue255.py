import asyncio
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus
from app.schemas.response import BusinessError
from app.services.workflow import benchmark as benchmark_module
from app.services.workflow.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkStatus,
    LatencyHistogram,
    RequestResult,
    WorkflowBenchmark,
    get_benchmark,
)


class QueryStub:
    def __init__(self, *, rows=None, first=None):
        self.rows = rows or []
        self.first_row = first
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def all(self):
        return self.rows

    async def first(self):
        return self.first_row

    async def count(self):
        return len(self.rows)

    def __await__(self):
        return self.all().__await__()


def make_request_result(
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


def test_public_error_sanitizers_cover_empty_known_and_unknown(monkeypatch):
    monkeypatch.setattr(
        workflows, "get_public_workflow_error_key", lambda value: value == "known"
    )
    monkeypatch.setattr(
        workflows, "translate_public_workflow_error", lambda _value: "translated"
    )
    monkeypatch.setattr(workflows, "t", lambda key: f"safe:{key}")

    assert workflows.sanitize_public_workflow_error(None) is None
    assert workflows.sanitize_public_workflow_error("known") == "translated"
    assert (
        workflows.sanitize_public_workflow_error("secret")
        == "safe:workflow_execution_error"
    )
    assert workflows.sanitize_workflow_run_payload(
        {"error_message": "secret", "id": 1}
    ) == {
        "error_message": "safe:workflow_execution_error",
        "id": 1,
    }
    assert workflows.sanitize_node_execution_payload({}) == {"error_message": None}


@pytest.mark.asyncio
async def test_workflow_stats_cover_empty_and_completed_runs(monkeypatch):
    workflow_id = uuid4()
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())

    empty_query = QueryStub()
    monkeypatch.setattr(workflows.WorkflowRun, "filter", empty_query.filter)
    empty = await workflows.get_workflow_stats(workflow_id, SimpleNamespace())
    assert empty["data"]["last_run_at"] is None

    created = datetime(2026, 1, 2, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            status=RunStatus.SUCCESS,
            total_duration_ms=10,
            created_at=created,
        ),
        SimpleNamespace(
            status=RunStatus.FAILED,
            total_duration_ms=None,
            created_at=created - timedelta(days=1),
        ),
        SimpleNamespace(
            status=RunStatus.TIMEOUT,
            total_duration_ms=20,
            created_at=created - timedelta(days=2),
        ),
    ]
    populated_query = QueryStub(rows=rows)
    monkeypatch.setattr(workflows.WorkflowRun, "filter", populated_query.filter)
    result = await workflows.get_workflow_stats(workflow_id, SimpleNamespace())

    assert result["data"] == {
        "total_runs": 3,
        "success_count": 1,
        "failed_count": 1,
        "timeout_count": 1,
        "avg_duration_ms": 15.0,
        "last_run_at": created.isoformat(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("search", "expected_filter"),
    [(str(uuid4()), "id"), ("not-a-uuid", "id__isnull"), ("  ", None)],
)
async def test_list_workflow_runs_search_paths(monkeypatch, search, expected_filter):
    query = QueryStub()
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowRun, "filter", query.filter)

    result = await workflows.list_workflow_runs(
        uuid4(),
        status=RunStatus.SUCCESS,
        is_debug=False,
        search=search,
        created_after=datetime(2026, 1, 1),
        created_before=datetime(2026, 1, 2),
        page=1,
        page_size=20,
        current_user=SimpleNamespace(),
    )

    assert result["data"]["items"] == []
    assert {next(iter(item)) for item in query.filters} >= {
        "workflow_id",
        "status",
        "is_debug",
        "created_at__gte",
        "created_at__lte",
    }
    if expected_filter:
        assert any(expected_filter in item for item in query.filters)
    else:
        assert not any(
            "id" in item or "id__isnull" in item for item in query.filters[1:]
        )


@pytest.mark.asyncio
async def test_stream_workflow_run_access_edges(monkeypatch):
    run_id = uuid4()

    async def invoke(row, user=None):
        query = QueryStub(first=row)
        monkeypatch.setattr(workflows.WorkflowRun, "filter", query.filter)
        return await workflows.stream_workflow_run(run_id, current_user=user)

    with pytest.raises(BusinessError) as missing:
        await invoke(None)
    assert missing.value.status_code == 404

    with pytest.raises(BusinessError) as orphan:
        await invoke(SimpleNamespace(workflow_id=None, triggered_by_id=None))
    assert orphan.value.msg_key == "workflow_not_found"

    with pytest.raises(BusinessError) as unauthorized:
        await invoke(SimpleNamespace(workflow_id=uuid4(), triggered_by_id=uuid4()))
    assert unauthorized.value.status_code == 401

    access = AsyncMock()
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    response = await invoke(
        SimpleNamespace(workflow_id=uuid4(), triggered_by_id=uuid4()),
        SimpleNamespace(),
    )
    assert response.media_type == "text/event-stream"
    access.assert_awaited_once()

    access.reset_mock()
    response = await invoke(SimpleNamespace(workflow_id=uuid4(), triggered_by_id=None))
    assert response.headers["cache-control"] == "no-cache"
    access.assert_not_awaited()


@pytest.mark.asyncio
async def test_benchmark_run_failure_cancellation_and_cleanup(monkeypatch):
    runner = WorkflowBenchmark()
    monkeypatch.setattr(
        runner,
        "_run_concurrent",
        AsyncMock(side_effect=ValueError("bad inputs")),
    )
    failed = await runner.run(
        "failed", AsyncMock(), dict, BenchmarkConfig(warmup_requests=0)
    )
    assert failed.status is BenchmarkStatus.FAILED
    assert failed.errors == {"benchmark_error": "bad inputs"}
    assert runner.get_running() == []

    monkeypatch.setattr(
        runner,
        "_run_concurrent",
        AsyncMock(side_effect=asyncio.CancelledError),
    )
    cancelled = await runner.run(
        "cancelled", AsyncMock(), dict, BenchmarkConfig(warmup_requests=0)
    )
    assert cancelled.status is BenchmarkStatus.CANCELLED
    assert await runner.cancel(cancelled.benchmark_id) is False


@pytest.mark.asyncio
async def test_execute_request_covers_response_sizes_error_and_timeout(monkeypatch):
    runner = WorkflowBenchmark()
    clock = iter([1_000_000, 4_000_000] * 4)
    monkeypatch.setattr(benchmark_module.time, "perf_counter_ns", lambda: next(clock))

    text = await runner._execute_request("text", AsyncMock(return_value=b"abc"), {}, 1)
    mapping = await runner._execute_request(
        "mapping", AsyncMock(return_value={"a": 1}), {}, 1
    )
    failed = await runner._execute_request(
        "failed", AsyncMock(side_effect=RuntimeError("boom")), {}, 1
    )

    async def blocked(_inputs):
        await asyncio.sleep(1)

    timed_out = await runner._execute_request("timeout", blocked, {}, 0)

    assert text.success and text.response_size == 3 and text.duration_ms == 3
    assert mapping.success and mapping.response_size == len('{"a": 1}')
    assert not failed.success and failed.error == "boom"
    assert not timed_out.success and timed_out.error == "timeout"


def test_benchmark_stats_status_histogram_and_singleton(monkeypatch):
    runner = WorkflowBenchmark()
    result = BenchmarkResult(
        benchmark_id="stats",
        status=BenchmarkStatus.RUNNING,
        config=BenchmarkConfig(),
        start_time=datetime.now(UTC),
        total_duration_seconds=2,
        results=[
            make_request_result("one", duration_ms=10, response_size=20),
            make_request_result("two", duration_ms=30, response_size=40),
            make_request_result("bad", success=False, error="x" * 60),
            make_request_result("ignored", success=False),
        ],
    )
    runner._calculate_stats(result)

    assert (result.successful_requests, result.failed_requests) == (2, 2)
    assert result.stddev_latency == pytest.approx(14.1421356)
    assert result.requests_per_second == 1
    assert result.bytes_per_second == 30
    assert result.errors == {"x" * 50: 1}

    runner._running_benchmarks["stats"] = result
    runner._cancel_events["stats"] = asyncio.Event()
    assert runner.get_status("stats")["failed"] == 2
    assert runner.get_status("missing") is None

    histogram = LatencyHistogram([10, 20])
    for latency in (5, 15, 30):
        histogram.observe(latency)
    assert histogram.get_distribution() == {"<=10ms": 1, "<=20ms": 0, ">20ms": 1}
    assert histogram.get_percentile(0.5) == 20
    assert histogram.get_percentile(1) == 20
    assert LatencyHistogram([10]).get_percentile(0.5) == 0

    monkeypatch.setattr(benchmark_module, "_benchmark", None)
    assert get_benchmark() is get_benchmark()
