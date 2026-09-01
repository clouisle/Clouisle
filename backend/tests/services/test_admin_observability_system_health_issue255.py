from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import admin_observability as service


@pytest.mark.asyncio
async def test_system_health_collects_components_and_stores_snapshot(monkeypatch):
    cpu = {"status": "healthy"}
    memory = {"status": "warning"}
    disk = {"status": "danger"}
    database = {"status": "healthy"}
    redis = {"status": "healthy"}
    workers = {"status": "healthy"}
    store = AsyncMock()
    monkeypatch.setattr(service, "_cpu_health", lambda: cpu)
    monkeypatch.setattr(service, "_memory_health", lambda: memory)
    monkeypatch.setattr(service, "_disk_health", lambda: disk)
    monkeypatch.setattr(service, "_database_health", AsyncMock(return_value=database))
    monkeypatch.setattr(service, "_redis_health", AsyncMock(return_value=redis))
    monkeypatch.setattr(service, "get_workers", AsyncMock(return_value=workers))
    monkeypatch.setattr(service, "_store_health_snapshot", store)

    result = await service.get_system_health()

    assert result["cpu"] is cpu
    assert result["memory"] is memory
    assert result["disk"] is disk
    assert result["database"] is database
    assert result["redis"] is redis
    assert result["workers"] is workers
    store.assert_awaited_once_with(result)


@pytest.mark.parametrize(
    ("percent", "expected"),
    [(69.9, "healthy"), (70, "warning"), (90, "danger")],
)
def test_host_health_reports_resources_and_thresholds(monkeypatch, percent, expected):
    psutil = SimpleNamespace(
        cpu_percent=lambda **_: percent,
        cpu_count=lambda: 8,
        virtual_memory=lambda: SimpleNamespace(percent=percent, used=10, total=20),
        disk_usage=lambda _: SimpleNamespace(percent=percent, used=30, total=40),
    )
    monkeypatch.setattr(service, "psutil", psutil)
    monkeypatch.setattr(service.platform, "machine", lambda: "test-arch")

    assert service._cpu_health() == {
        "status": expected,
        "usage_percent": percent,
        "cores": 8,
        "architecture": "test-arch",
    }
    resource_expected = service._status_for_percent(percent, 80, 90)
    assert service._memory_health()["status"] == resource_expected
    assert service._disk_health()["status"] == resource_expected


def test_host_health_degrades_without_psutil(monkeypatch):
    monkeypatch.setattr(service, "psutil", None)

    assert service._cpu_health()["status"] == "unknown"
    assert service._memory_health()["status"] == "unknown"
    assert service._disk_health()["status"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dialect", "rows", "expected"),
    [
        ("sqlite", [], {"active_connections": 1, "max_connections": None}),
        (
            "postgres",
            [{"active_connections": 3, "max_connections": 100}],
            {"active_connections": 3, "max_connections": 100},
        ),
        ("postgres", [], {"active_connections": 0, "max_connections": 0}),
    ],
)
async def test_database_health_supports_database_dialects(
    monkeypatch, dialect, rows, expected
):
    connection = SimpleNamespace(
        capabilities=SimpleNamespace(dialect=dialect),
        execute_query=AsyncMock(side_effect=[(1, []), (len(rows), rows)]),
    )
    monkeypatch.setattr(service.Tortoise, "get_connection", lambda _: connection)

    result = await service._database_health()

    assert result["status"] == "healthy"
    assert {key: result[key] for key in expected} == expected


@pytest.mark.asyncio
async def test_database_health_reports_connection_failure(monkeypatch):
    connection = SimpleNamespace(
        execute_query=AsyncMock(side_effect=RuntimeError("db down"))
    )
    monkeypatch.setattr(service.Tortoise, "get_connection", lambda _: connection)

    assert await service._database_health() == {
        "status": "unhealthy",
        "error": "db down",
    }


@pytest.mark.asyncio
async def test_redis_health_calculates_hit_rate_and_reports_failure(monkeypatch):
    redis = SimpleNamespace(
        info=AsyncMock(
            return_value={
                "keyspace_hits": 8,
                "keyspace_misses": 2,
                "used_memory": 100,
                "connected_clients": 3,
                "instantaneous_ops_per_sec": 7,
            }
        )
    )
    get_redis = AsyncMock(return_value=redis)
    monkeypatch.setattr(service, "get_redis", get_redis)

    result = await service._redis_health()

    assert result == {
        "status": "healthy",
        "used_memory": 100,
        "connected_clients": 3,
        "ops_per_sec": 7,
        "hit_rate": 80.0,
    }

    get_redis.side_effect = RuntimeError("redis down")
    assert await service._redis_health() == {
        "status": "unhealthy",
        "error": "redis down",
    }


@pytest.mark.asyncio
async def test_workers_report_tasks_and_queue_depths(monkeypatch):
    inspect = SimpleNamespace(
        active=lambda: {"worker-1": [{}, {}]},
        reserved=lambda: {"worker-1": [{}]},
        scheduled=lambda: {},
        stats=lambda: {"worker-1": {}, "worker-2": {}},
    )
    monkeypatch.setattr(service.celery_app.control, "inspect", lambda **_: inspect)
    monkeypatch.setattr(
        service,
        "_queue_lengths",
        AsyncMock(return_value=[{"queue": "default", "pending": 4}]),
    )
    monkeypatch.setattr(
        service,
        "_pending_task_rows",
        AsyncMock(
            return_value=[
                {
                    "task": "send_notification_email",
                    "queue": "default",
                    "pending": 4,
                }
            ]
        ),
    )

    assert await service.get_workers() == {
        "status": "healthy",
        "worker_count": 2,
        "active_tasks": 2,
        "reserved_tasks": 1,
        "scheduled_tasks": 0,
        "queues": [{"queue": "default", "pending": 4}],
        "tasks": [
            {
                "task": "send_notification_email",
                "queue": "default",
                "pending": 4,
            }
        ],
    }


@pytest.mark.asyncio
async def test_queue_lengths_and_snapshot_use_redis_boundary(monkeypatch):
    redis = SimpleNamespace(
        llen=AsyncMock(side_effect=[2, 5, 0, 3, None]),
        lpush=AsyncMock(),
        ltrim=AsyncMock(),
        expire=AsyncMock(),
    )
    get_redis = AsyncMock(return_value=redis)
    monkeypatch.setattr(service, "get_redis", get_redis)

    assert await service._queue_lengths() == [
        {"queue": "default", "pending": 2},
        {"queue": "knowledge", "pending": 5},
        {"queue": "workflow", "pending": 0},
        {"queue": "agent", "pending": 3},
        {"queue": "sandbox", "pending": 0},
    ]
    await service._store_health_snapshot(
        {
            "generated_at": "now",
            "cpu": {"usage_percent": 1},
            "memory": {"usage_percent": 2},
            "disk": {"usage_percent": 3},
            "database": {"active_connections": 4},
            "redis": {"ops_per_sec": 5},
        }
    )

    redis.lpush.assert_awaited_once()
    redis.ltrim.assert_awaited_once_with(service.HEALTH_SNAPSHOT_KEY, 0, 120)
    redis.expire.assert_awaited_once_with(service.HEALTH_SNAPSHOT_KEY, 86400)

    get_redis.side_effect = RuntimeError("offline")
    assert await service._queue_lengths() == [
        {"queue": queue, "pending": 0} for queue in service.WORKER_QUEUES
    ]
    await service._store_health_snapshot({})


@pytest.mark.asyncio
async def test_system_trend_skips_invalid_snapshots_and_degrades(monkeypatch):
    redis = SimpleNamespace(
        lrange=AsyncMock(return_value=[b'{"at": 2}', b"invalid", b'{"at": 1}'])
    )
    get_redis = AsyncMock(return_value=redis)
    monkeypatch.setattr(service, "get_redis", get_redis)

    assert await service.get_system_trend() == {"items": [{"at": 1}, {"at": 2}]}

    get_redis.side_effect = RuntimeError("offline")
    assert await service.get_system_trend() == {"items": []}


@pytest.mark.asyncio
async def test_slow_queries_cover_unavailable_and_available_database_paths(monkeypatch):
    connection = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(service.Tortoise, "get_connection", lambda _: connection)

    missing = await service.get_slow_queries(500, 0, 200)
    assert missing["available"] is False
    assert "extension is not created" in missing["reason"]

    rows = [{"query": "SELECT 1", "avg_ms": 750.25}]
    connection.execute_query.side_effect = [(1, [{"exists": 1}]), (1, rows)]
    available = await service.get_slow_queries(500, 0, 200)

    assert available["available"] is True
    assert available["items"] == rows
    assert connection.execute_query.await_args_list[-1].args[1] == [500, 100, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "reason"),
    [
        (
            "must be loaded via shared_preload_libraries",
            "must be added to shared_preload_libraries",
        ),
        ("PERMISSION DENIED", "database user cannot create or read"),
    ],
)
async def test_slow_queries_explains_actionable_failures(monkeypatch, message, reason):
    connection = SimpleNamespace(
        execute_query=AsyncMock(side_effect=RuntimeError(message))
    )
    monkeypatch.setattr(service.Tortoise, "get_connection", lambda _: connection)

    result = await service.get_slow_queries(500, 1, 20)

    assert result["available"] is False
    assert reason in result["reason"]
