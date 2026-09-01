from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services import admin_observability


def test_normalizers_pagination_and_bucket_merge_cover_defaults_and_bounds():
    start, end = admin_observability.normalize_time_range("invalid")
    assert end - start == admin_observability.timedelta(days=30)
    assert admin_observability.normalize_time_range("all")[0] is None
    assert admin_observability.normalize_granularity("7d") == "hour"
    assert admin_observability.normalize_granularity("30d", "hour") == "hour"

    payload = admin_observability._paginate(
        [{"id": index} for index in range(3)], 0, 500
    )
    assert payload == {
        "items": [{"id": 0}, {"id": 1}, {"id": 2}],
        "total": 3,
        "page": 1,
        "page_size": 100,
    }
    merged = admin_observability._merge_count_buckets(
        [{"bucket": "b", "count": 2}],
        [{"bucket": "a", "count": 1}, {"bucket": "b", "count": 3}],
    )
    assert merged == [
        {"bucket": "a", "agent_requests": 0, "workflow_runs": 1, "total_requests": 1},
        {"bucket": "b", "agent_requests": 2, "workflow_runs": 3, "total_requests": 5},
    ]


@pytest.mark.anyio
async def test_timeouts_cover_source_filters_sorting_distribution_and_defaults():
    workflow_id = uuid4()
    agent_id = uuid4()
    with (
        patch.object(
            admin_observability,
            "normalize_time_range",
            return_value=(None, datetime.now(UTC)),
        ),
        patch.object(
            admin_observability,
            "_workflow_timeout_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "workflow_id": workflow_id,
                        "workflow_name": None,
                        "created_at": "2026-01-01",
                        "duration_ms": 3,
                        "status": "timeout",
                    }
                ]
            ),
        ),
        patch.object(
            admin_observability,
            "_agent_timeout_like_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "agent_id": agent_id,
                        "agent_name": None,
                        "created_at": "2026-01-02",
                        "duration_ms": 2,
                        "round_status": "error",
                        "model_used": "m",
                    }
                ]
            ),
        ),
    ):
        result = await admin_observability.get_timeouts("30d", "all", 1, 20)

    assert [item["source"] for item in result["items"]] == ["agent", "workflow"]
    assert result["distribution"] == {"agent": 1, "workflow": 1}
    assert all(item["entity_name"] == "Unknown" for item in result["items"])
    assert result["agent_timeout_type_available"] is False


@pytest.mark.anyio
async def test_system_trend_skips_invalid_items_and_handles_redis_failure():
    redis = AsyncMock()
    redis.lrange.return_value = [b'{"value": 2}', b"invalid", b'{"value": 1}']
    with patch.object(
        admin_observability, "get_redis", new=AsyncMock(return_value=redis)
    ):
        assert await admin_observability.get_system_trend() == {
            "items": [{"value": 1}, {"value": 2}]
        }

    with patch.object(
        admin_observability,
        "get_redis",
        new=AsyncMock(side_effect=RuntimeError("down")),
    ):
        assert await admin_observability.get_system_trend() == {"items": []}


@pytest.mark.anyio
async def test_slow_queries_covers_missing_extension_reason_mapping_and_success():
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=(0, []))
    with patch.object(
        admin_observability.Tortoise, "get_connection", return_value=conn
    ):
        result = await admin_observability.get_slow_queries(100, 1, 20)
    assert result["available"] is False
    assert "extension is not created" in result["reason"]

    for message, expected in [
        ("must be loaded via shared_preload_libraries", "must be added"),
        ("PERMISSION DENIED", "cannot create or read"),
    ]:
        conn.execute_query = AsyncMock(side_effect=RuntimeError(message))
        with patch.object(
            admin_observability.Tortoise, "get_connection", return_value=conn
        ):
            result = await admin_observability.get_slow_queries(100, 1, 20)
        assert expected in result["reason"]

    conn.execute_query = AsyncMock(
        side_effect=[(1, [{"exists": 1}]), (1, [{"avg_ms": 1.234, "id": uuid4()}])]
    )
    with patch.object(
        admin_observability.Tortoise, "get_connection", return_value=conn
    ):
        result = await admin_observability.get_slow_queries(100, 0, 200)
    assert result["available"] is True
    assert result["items"][0]["avg_ms"] == 1.23
    assert isinstance(result["items"][0]["id"], str)
    assert conn.execute_query.await_args_list[1].args[1] == [100, 100, 0]


@pytest.mark.anyio
async def test_health_helpers_cover_success_degradation_and_queue_fallback():
    non_postgres = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(return_value=(1, [])),
    )
    with patch.object(
        admin_observability.Tortoise, "get_connection", return_value=non_postgres
    ):
        assert (await admin_observability._database_health())["active_connections"] == 1

    redis = AsyncMock()
    redis.info.return_value = {
        "keyspace_hits": 3,
        "keyspace_misses": 1,
        "used_memory": 4,
        "connected_clients": 2,
        "instantaneous_ops_per_sec": 5,
    }
    redis.llen.side_effect = [1, 0, 2, 3, 0]
    with patch.object(
        admin_observability, "get_redis", new=AsyncMock(return_value=redis)
    ):
        assert (await admin_observability._redis_health())["hit_rate"] == 75
        assert [
            item["pending"] for item in await admin_observability._queue_lengths()
        ] == [1, 0, 2, 3, 0]

    with patch.object(
        admin_observability,
        "get_redis",
        new=AsyncMock(side_effect=RuntimeError("down")),
    ):
        assert (await admin_observability._redis_health())["status"] == "unhealthy"
        assert all(
            item["pending"] == 0 for item in await admin_observability._queue_lengths()
        )

    assert admin_observability._status_for_percent(90, 70, 90) == "danger"
    assert admin_observability._status_for_percent(70, 70, 90) == "warning"
    assert admin_observability._status_for_percent(69, 70, 90) == "healthy"
