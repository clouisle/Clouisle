from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow import metrics as metrics_module
from app.services.workflow.metrics import MetricConfig, MetricsCollector, Timer


@pytest.fixture
def redis():
    return AsyncMock()


@pytest.fixture
def collector(redis):
    collector = MetricsCollector(
        MetricConfig(prefix="test:", latency_buckets=(10, 100))
    )
    collector._redis = redis
    return collector


@pytest.mark.asyncio
async def test_record_workflow_start(redis, collector):
    with patch.object(metrics_module.time, "time", return_value=125.0):
        await collector.record_workflow_start("run-1", "workflow-1")

    redis.hset.assert_awaited_once_with(
        "test:runs:run-1",
        mapping={
            "workflow_id": "workflow-1",
            "start_time": "125.0",
            "status": "running",
        },
    )
    redis.incr.assert_any_await("test:workflow:workflow-1:running")
    redis.incr.assert_any_await("test:ts:workflow-1:starts:2")
    assert redis.expire.await_count == 2


@pytest.mark.asyncio
async def test_record_failed_workflow_completion(redis, collector):
    with patch.object(metrics_module.time, "time", return_value=180.0):
        await collector.record_workflow_complete(
            "run-1",
            "workflow-1",
            duration_ms=101,
            status="failed",
            node_count=3,
            error="ValueError: bad input",
        )

    redis.hset.assert_awaited_once_with(
        "test:runs:run-1",
        mapping={
            "end_time": "180.0",
            "duration_ms": "101",
            "status": "failed",
            "node_count": "3",
            "error": "ValueError: bad input",
        },
    )
    redis.decr.assert_awaited_once_with("test:workflow:workflow-1:running")
    redis.incr.assert_any_await("test:workflow:workflow-1:failed")
    redis.incr.assert_any_await("test:workflow:workflow-1:duration:100")
    redis.zadd.assert_awaited_once_with(
        "test:workflow:workflow-1:durations", {"run-1": 101}
    )
    redis.incrby.assert_awaited_once_with("test:workflow:workflow-1:nodes", 3)
    redis.hincrby.assert_awaited_once_with(
        "test:workflow:workflow-1:errors", "ValueError", 1
    )


@pytest.mark.asyncio
async def test_record_node_execution_and_disabled_boundary(redis):
    disabled = MetricsCollector(MetricConfig(enable_node_metrics=False))
    disabled._redis = redis
    await disabled.record_node_execution("run", "node", "llm", 10)
    redis.incr.assert_not_awaited()

    collector = MetricsCollector(
        MetricConfig(prefix="test:", latency_buckets=(10, 100))
    )
    collector._redis = redis
    await collector.record_node_execution(
        "run", "node", "llm", 11, success=False, retries=2, error="timeout"
    )

    redis.incr.assert_any_await("test:node:llm:failed")
    redis.incr.assert_any_await("test:node:llm:duration:100")
    redis.zadd.assert_awaited_once_with("test:node:llm:durations", {"run:node": 11})
    redis.incrby.assert_awaited_once_with("test:node:llm:retries", 2)
    redis.hincrby.assert_awaited_once_with("test:node:llm:errors", "timeout", 1)


@pytest.mark.asyncio
async def test_get_workflow_metrics_aggregates_counts_durations_and_throughput(
    redis, collector
):
    values = {
        "test:workflow:workflow-1:success": "2",
        "test:workflow:workflow-1:failed": "1",
        "test:workflow:workflow-1:cancelled": "1",
        "test:workflow:workflow-1:nodes": "12",
        "test:ts:workflow-1:success:1": "2",
        "test:ts:workflow-1:failed:2": "1",
    }
    redis.get.side_effect = lambda key: values.get(key)
    redis.zrange.return_value = [("run-2", 30.0), ("run-1", 10.0)]
    redis.hgetall.return_value = {"ValueError": "1"}

    with patch.object(metrics_module.time, "time", return_value=120.0):
        result = await collector.get_workflow_metrics("workflow-1", 1)

    assert result.total_runs == 4
    assert result.error_rate == 0.25
    assert result.min_duration_ms == 10.0
    assert result.max_duration_ms == 30.0
    assert result.avg_duration_ms == 20.0
    assert result.p50_duration_ms == 30.0
    assert result.p95_duration_ms == 30.0
    assert result.total_nodes_executed == 12
    assert result.avg_nodes_per_run == 3.0
    assert result.errors_by_type == {"ValueError": 1}
    assert result.runs_per_minute == 3.0
    assert result.start_time is not None
    assert result.end_time is not None


@pytest.mark.asyncio
async def test_get_workflow_metrics_empty_and_zero_range(redis, collector):
    redis.get.return_value = None
    redis.zrange.return_value = []
    redis.hgetall.return_value = {}

    result = await collector.get_workflow_metrics("missing", 0)

    assert result.total_runs == 0
    assert result.error_rate == 0
    assert result.min_duration_ms == float("inf")
    assert result.runs_per_minute == 0


@pytest.mark.asyncio
async def test_get_node_metrics_aggregates(redis, collector):
    values = {
        "test:node:llm:success": "3",
        "test:node:llm:failed": "1",
        "test:node:llm:retries": "2",
    }
    redis.get.side_effect = lambda key: values.get(key)
    redis.zrange.return_value = [("b", 50.0), ("a", 10.0)]

    result = await collector.get_node_metrics("llm")

    assert result.total_executions == 4
    assert result.avg_duration_ms == 30.0
    assert result.min_duration_ms == 10.0
    assert result.max_duration_ms == 50.0
    assert result.p50_duration_ms == 50.0
    assert result.total_retries == 2
    assert result.avg_retries == 0.5


@pytest.mark.asyncio
async def test_get_all_node_metrics_filters_inactive_types(collector):
    async def node_metrics(node_type):
        result = metrics_module.NodeMetrics(node_type=node_type)
        result.total_executions = 1 if node_type == "llm" else 0
        return result

    collector.get_node_metrics = AsyncMock(side_effect=node_metrics)

    result = await collector.get_all_node_metrics()

    assert list(result) == ["llm"]
    assert collector.get_node_metrics.await_count == 21


@pytest.mark.asyncio
async def test_running_workflows_are_filtered_and_sorted(redis, collector):
    redis.keys.return_value = ["test:runs:new", "test:runs:done", "test:runs:old"]
    redis.hgetall.side_effect = [
        {"status": "running", "workflow_id": "wf", "start_time": "90"},
        {"status": "success", "workflow_id": "wf", "start_time": "80"},
        {"status": "running", "workflow_id": "wf", "start_time": "70"},
    ]

    with patch.object(metrics_module.time, "time", return_value=100.0):
        result = await collector.get_running_workflows()

    assert [run["run_id"] for run in result] == ["old", "new"]
    assert [run["duration_s"] for run in result] == [30.0, 10.0]


@pytest.mark.asyncio
async def test_dashboard_summary_aggregates_workflows(redis, collector):
    redis.keys.side_effect = [
        ["test:workflow:a:success", "test:workflow:b:success"],
        ["test:workflow:a:failed"],
    ]
    redis.get.side_effect = ["2", "3", "1"]
    collector.get_running_workflows = AsyncMock(
        return_value=[{"run_id": str(index)} for index in range(12)]
    )

    result = await collector.get_dashboard_summary()

    assert result == {
        "total_runs": 6,
        "successful_runs": 5,
        "failed_runs": 1,
        "success_rate": 5 / 6,
        "currently_running": 12,
        "running_workflows": [{"run_id": str(index)} for index in range(10)],
    }


@pytest.mark.asyncio
async def test_redis_failures_are_contained(redis, collector, caplog):
    redis.incr.side_effect = RuntimeError("redis unavailable")
    await collector.record_workflow_start("run", "workflow")

    redis.get.side_effect = RuntimeError("redis unavailable")
    workflow = await collector.get_workflow_metrics("workflow")
    node = await collector.get_node_metrics("llm")
    running = await collector.get_running_workflows()
    redis.keys.side_effect = RuntimeError("redis unavailable")
    dashboard = await collector.get_dashboard_summary()

    assert workflow.total_runs == 0
    assert node.total_executions == 0
    assert running == []
    assert dashboard == {}
    assert "redis unavailable" in caplog.text


@pytest.mark.asyncio
async def test_helpers_timer_connection_cache_and_singleton_boundaries(redis):
    collector = MetricsCollector(MetricConfig(latency_buckets=(10, 100)))
    with patch.object(
        metrics_module, "get_redis", AsyncMock(return_value=redis)
    ) as get:
        assert await collector._get_redis() is redis
        assert await collector._get_redis() is redis
    get.assert_awaited_once()

    assert collector._get_bucket(10) == 10
    assert collector._get_bucket(101) == 100
    assert collector._percentile([], 95) == 0.0
    assert collector._percentile([1.0, 2.0], 100) == 2.0
    assert collector._extract_error_type("") == "UnknownError"

    with patch.object(metrics_module.time, "time", side_effect=[1.0, 1.123]):
        async with Timer() as timer:
            pass
    assert timer.duration_ms == 123

    with patch.object(metrics_module, "_metrics_instance", None):
        assert (
            metrics_module.get_metrics_collector()
            is metrics_module.get_metrics_collector()
        )
