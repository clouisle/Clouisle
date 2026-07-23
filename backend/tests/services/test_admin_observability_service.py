from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services import admin_observability


def test_continuous_percentile_handles_empty_and_single_value():
    assert admin_observability.continuous_percentile([], 0.5) is None
    assert admin_observability.continuous_percentile([42], 0.95) == 42


def test_continuous_percentile_interpolates_even_count():
    values = [10, 20, 30, 40]

    assert admin_observability.continuous_percentile(values, 0.5) == 25
    assert admin_observability.continuous_percentile(values, 0.9) == pytest.approx(37)
    assert admin_observability.continuous_percentile(values, 0.95) == pytest.approx(
        38.5
    )
    assert admin_observability.continuous_percentile(values, 0.99) == pytest.approx(
        39.7
    )


def test_extract_token_total_accepts_total_and_prompt_completion_shapes():
    assert admin_observability.extract_token_total({"total": 12}) == 12
    assert admin_observability.extract_token_total({"total_tokens": 13}) == 13
    assert admin_observability.extract_token_total({"prompt": 7, "completion": 5}) == 12
    assert (
        admin_observability.extract_token_total(
            {"prompt_tokens": 3, "completion_tokens": 4}
        )
        == 7
    )
    assert admin_observability.extract_token_total(None) == 0


@pytest.mark.asyncio
async def test_cached_payload_returns_cached_value():
    redis = AsyncMock()
    redis.get.return_value = '{"cached": true}'
    producer = AsyncMock(return_value={"cached": False})

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.cached_payload("test", {}, producer)

    assert result == {"cached": True}
    producer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_payload_computes_when_redis_fails():
    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis down")
    redis.setex.side_effect = RuntimeError("redis down")
    producer = AsyncMock(return_value={"fresh": True})

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.cached_payload("test", {}, producer)

    assert result == {"fresh": True}
    producer.assert_awaited_once()


@pytest.mark.asyncio
async def test_overview_reports_ttft_separately_from_total_duration():
    agent_rows = [
        {
            "duration_ms": 30000,
            "first_token_ms": 900,
            "round_status": "completed",
            "tokens": 10,
            "created_at": "2026-06-05T10:00:00+00:00",
        },
        {
            "duration_ms": 60000,
            "first_token_ms": 1300,
            "round_status": "completed",
            "tokens": 20,
            "created_at": "2026-06-05T10:01:00+00:00",
        },
        {
            "duration_ms": 90000,
            "first_token_ms": None,
            "round_status": "completed",
            "tokens": 30,
            "created_at": "2026-06-05T10:02:00+00:00",
        },
    ]
    workflow_rows = [
        {
            "duration_ms": 120000,
            "status": "success",
            "tokens": 40,
            "created_at": "2026-06-05T10:03:00+00:00",
        }
    ]

    with (
        patch(
            "app.services.admin_observability.normalize_time_range",
            return_value=(None, admin_observability.to_utc(admin_observability.now())),
        ),
        patch(
            "app.services.admin_observability._agent_message_rows",
            new=AsyncMock(return_value=agent_rows),
        ),
        patch(
            "app.services.admin_observability._workflow_run_rows",
            new=AsyncMock(return_value=workflow_rows),
        ),
    ):
        result = await admin_observability.get_overview("30d")

    assert result["latency"]["p95_ms"] == 115500
    assert result["ttft"]["p95_ms"] == 1280


@pytest.mark.asyncio
async def test_slow_queries_returns_unavailable_when_pg_stat_statements_missing():
    conn = MagicMock()
    conn.execute_query = AsyncMock(side_effect=RuntimeError("relation does not exist"))

    with patch(
        "app.services.admin_observability.Tortoise.get_connection", return_value=conn
    ):
        result = await admin_observability.get_slow_queries(1000, 1, 20)

    assert result["available"] is False
    assert result["items"] == []


@pytest.mark.asyncio
async def test_workers_return_unknown_when_inspect_fails():
    with patch(
        "app.services.admin_observability.celery_app.control.inspect",
        side_effect=RuntimeError("no workers"),
    ):
        result = await admin_observability.get_workers()

    assert result["status"] == "unknown"
    assert result["worker_count"] == 0


def test_normalizers_and_pagination_boundaries():
    fixed_now = datetime(2026, 6, 5, tzinfo=timezone.utc)

    with patch("app.services.admin_observability.now", return_value=fixed_now):
        start, end = admin_observability.normalize_time_range("invalid")
        all_start, all_end = admin_observability.normalize_time_range("all")

    assert (end - start).days == 30
    assert all_start is None
    assert all_end == end
    assert admin_observability.normalize_granularity("7d") == "hour"
    assert admin_observability.normalize_granularity("90d", "hour") == "hour"
    assert admin_observability.safe_rate(1, 0) == 0
    assert admin_observability.safe_rate(1, 4) == 25
    assert admin_observability._paginate([1, 2], 0, 500) == {
        "items": [1, 2],
        "total": 2,
        "page": 1,
        "page_size": 100,
    }


@pytest.mark.asyncio
async def test_cached_payload_writes_fresh_value():
    redis = AsyncMock()
    producer = AsyncMock(return_value={"generated_at": datetime(2026, 6, 5)})

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.cached_payload(
            "overview", {"range": "7d"}, producer
        )

    assert result == {"generated_at": datetime(2026, 6, 5)}
    redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_and_detail_aggregations_sort_filter_and_handle_empty_rows():
    agent_id = uuid4()
    workflow_id = uuid4()
    agents = [
        {"agent_id": uuid4(), "request_count": 2},
        {"agent_id": agent_id, "request_count": 5},
    ]
    workflows = [
        {"workflow_id": workflow_id, "failed_nodes": 1},
        {"workflow_id": uuid4(), "failed_nodes": 4},
    ]

    with (
        patch(
            "app.services.admin_observability.normalize_time_range",
            return_value=(None, datetime(2026, 6, 5, tzinfo=timezone.utc)),
        ),
        patch(
            "app.services.admin_observability._agent_performance_rows",
            new=AsyncMock(return_value=agents),
        ),
        patch(
            "app.services.admin_observability._workflow_performance_rows",
            new=AsyncMock(return_value=workflows),
        ),
        patch(
            "app.services.admin_observability._agent_trend_rows",
            new=AsyncMock(return_value=[{"bucket": "agent"}]),
        ),
        patch(
            "app.services.admin_observability._workflow_trend_rows",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.services.admin_observability._workflow_node_rows",
            new=AsyncMock(return_value=[{"node_type": "llm"}]),
        ),
    ):
        agent_page = await admin_observability.get_agents(
            "30d", 1, 1, "requests", "desc"
        )
        workflow_page = await admin_observability.get_workflows(
            "30d", 1, 10, "failed_nodes", "asc"
        )
        agent_detail = await admin_observability.get_agent_detail(agent_id, "7d")
        missing_workflow = await admin_observability.get_workflow_detail(uuid4(), "30d")

    assert agent_page["items"] == [agents[1]]
    assert workflow_page["items"] == workflows
    assert agent_detail["agent"] == agents[1]
    assert agent_detail["trend"] == [{"bucket": "agent"}]
    assert missing_workflow["workflow"] is None
    assert missing_workflow["nodes"] == [{"node_type": "llm"}]


@pytest.mark.asyncio
async def test_timeout_throughput_and_token_aggregations():
    timestamp = datetime(2026, 6, 5, 10, tzinfo=timezone.utc)
    with (
        patch(
            "app.services.admin_observability.normalize_time_range",
            return_value=(None, timestamp),
        ),
        patch(
            "app.services.admin_observability._workflow_timeout_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "workflow_id": "workflow-1",
                        "workflow_name": None,
                        "created_at": timestamp,
                        "duration_ms": 100,
                        "status": "timeout",
                    }
                ]
            ),
        ),
        patch(
            "app.services.admin_observability._agent_timeout_like_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "agent_id": "agent-1",
                        "agent_name": "Agent",
                        "model_used": "model-a",
                        "created_at": timestamp,
                        "duration_ms": 200,
                        "round_status": "error",
                    }
                ]
            ),
        ),
        patch(
            "app.services.admin_observability._bucket_count_rows",
            new=AsyncMock(
                side_effect=[
                    [{"bucket": timestamp, "count": 2}],
                    [{"bucket": timestamp, "count": 3}],
                ]
            ),
        ),
        patch(
            "app.services.admin_observability._scalar_count",
            new=AsyncMock(return_value=4),
        ),
        patch(
            "app.services.admin_observability._current_qps",
            new=AsyncMock(return_value=0.25),
        ),
        patch(
            "app.services.admin_observability._agent_message_rows",
            new=AsyncMock(
                return_value=[
                    {"model_used": "model-a", "tokens": 5},
                    {"model_used": None, "tokens": 2},
                ]
            ),
        ),
        patch(
            "app.services.admin_observability._workflow_run_rows",
            new=AsyncMock(return_value=[{"tokens": 7}]),
        ),
    ):
        timeouts = await admin_observability.get_timeouts("30d", "all", 1, 10)
        throughput = await admin_observability.get_throughput("7d", None)
        tokens = await admin_observability.get_tokens("30d")

    assert timeouts["distribution"] == {"workflow": 1, "agent": 1}
    assert timeouts["items"][0]["created_at"] == timestamp.isoformat()
    assert throughput["current"] == {
        "qps": 0.25,
        "tps": 0.25,
        "running_workflows": 4,
    }
    assert throughput["buckets"] == [
        {
            "bucket": timestamp.isoformat(),
            "agent_requests": 2,
            "workflow_runs": 3,
            "total_requests": 5,
        }
    ]
    assert tokens["total_tokens"] == 14
    assert tokens["by_model"] == [
        {"model": "model-a", "tokens": 5},
        {"model": "unknown", "tokens": 2},
    ]


@pytest.mark.asyncio
async def test_system_trend_skips_invalid_snapshots_and_redis_failure():
    redis = AsyncMock()
    redis.lrange.return_value = [b'{"cpu_percent": 10}', b"invalid", None]

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.get_system_trend()
    assert result == {"items": [{"cpu_percent": 10}]}

    with patch(
        "app.services.admin_observability.get_redis", side_effect=RuntimeError("down")
    ):
        assert await admin_observability.get_system_trend() == {"items": []}


@pytest.mark.asyncio
async def test_slow_queries_handles_absent_extension_success_and_permission_failure():
    absent = MagicMock()
    absent.execute_query = AsyncMock(return_value=(0, []))
    success = MagicMock()
    success.execute_query = AsyncMock(
        side_effect=[
            (1, [{"exists": 1}]),
            (1, [{"query": "SELECT 1", "avg_ms": 12.345, "calls": 2}]),
        ]
    )
    denied = MagicMock()
    denied.execute_query = AsyncMock(side_effect=RuntimeError("Permission denied"))

    with patch(
        "app.services.admin_observability.Tortoise.get_connection",
        side_effect=[absent, success, denied],
    ):
        unavailable = await admin_observability.get_slow_queries(10, 0, 200)
        available = await admin_observability.get_slow_queries(10, 2, 5)
        permission = await admin_observability.get_slow_queries(10, 1, 5)

    assert unavailable["available"] is False
    assert available["items"] == [{"query": "SELECT 1", "avg_ms": 12.35, "calls": 2}]
    assert success.execute_query.await_args_list[1].args[1] == [10, 5, 5]
    assert (
        permission["reason"] == "database user cannot create or read pg_stat_statements"
    )


@pytest.mark.asyncio
async def test_workers_and_health_dependencies_cover_happy_and_failure_states():
    inspect = MagicMock()
    inspect.active.return_value = {"worker": [{"id": 1}]}
    inspect.reserved.return_value = {"worker": [{"id": 2}]}
    inspect.scheduled.return_value = {"worker": []}
    inspect.stats.return_value = {"worker": {}}
    redis = AsyncMock()
    redis.info.return_value = {
        "keyspace_hits": 3,
        "keyspace_misses": 1,
        "used_memory": 10,
        "connected_clients": 2,
        "instantaneous_ops_per_sec": 7,
    }
    redis.llen.side_effect = [1, None, 3]

    with (
        patch(
            "app.services.admin_observability.celery_app.control.inspect",
            return_value=inspect,
        ),
        patch(
            "app.services.admin_observability._queue_lengths",
            new=AsyncMock(return_value=[{"queue": "default", "pending": 1}]),
        ),
    ):
        workers = await admin_observability.get_workers()
    assert workers["status"] == "healthy"
    assert workers["active_tasks"] == 1

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        assert (await admin_observability._redis_health())["hit_rate"] == 75
        assert await admin_observability._queue_lengths() == [
            {"queue": "default", "pending": 1},
            {"queue": "workflow", "pending": 0},
            {"queue": "sandbox", "pending": 3},
        ]

    with patch(
        "app.services.admin_observability.get_redis", side_effect=RuntimeError("down")
    ):
        assert (await admin_observability._redis_health())["status"] == "unhealthy"
        assert all(
            item["pending"] == 0 for item in await admin_observability._queue_lengths()
        )


@pytest.mark.asyncio
async def test_database_health_execute_helpers_and_row_decoration():
    sqlite = MagicMock(capabilities=SimpleNamespace(dialect="sqlite"))
    sqlite.execute_query = AsyncMock(return_value=(1, []))
    postgres = MagicMock(capabilities=SimpleNamespace(dialect="postgres"))
    postgres.execute_query = AsyncMock(
        side_effect=[(1, []), (1, [{"active_connections": 3, "max_connections": 10}])]
    )
    failed = MagicMock()
    failed.execute_query = AsyncMock(side_effect=RuntimeError("db down"))

    with patch(
        "app.services.admin_observability.Tortoise.get_connection",
        side_effect=[sqlite, postgres, failed],
    ):
        assert (await admin_observability._database_health())["active_connections"] == 1
        assert (await admin_observability._database_health())["max_connections"] == 10
        assert (await admin_observability._database_health())["status"] == "unhealthy"

    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=(1, ({"count": 3},)))
    with patch(
        "app.services.admin_observability.Tortoise.get_connection", return_value=conn
    ):
        assert (
            await admin_observability._scalar_count("items", "active = $1", [True]) == 3
        )

    row = admin_observability._decorate_performance_row(
        {
            "request_count": 2,
            "success_count": 1,
            "timeout_count": 1,
            "total_tokens": 5,
            "p50_ms": 12.6,
        },
        "request_count",
    )
    assert row["success_rate"] == 50
    assert row["timeout_rate"] == 50
    assert row["avg_tokens"] == 2.5
    assert row["p50_ms"] == 13


@pytest.mark.parametrize(
    ("value", "expected"),
    [(69, "healthy"), (70, "warning"), (90, "danger")],
)
def test_status_for_percent_boundaries(value, expected):
    assert admin_observability._status_for_percent(value, 70, 90) == expected
