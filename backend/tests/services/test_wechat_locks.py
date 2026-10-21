import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import wechat_locks


@pytest.mark.asyncio
async def test_sqlite_collection_lock_excludes_concurrent_worker(monkeypatch):
    fake_connections = SimpleNamespace(
        get=lambda _: SimpleNamespace(capabilities=SimpleNamespace(dialect="sqlite"))
    )
    monkeypatch.setattr(wechat_locks, "connections", fake_connections)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock():
        async with wechat_locks.collection_lock("collection-a"):
            entered.set()
            await release.wait()

    owner = asyncio.create_task(hold_lock())
    await entered.wait()
    with pytest.raises(wechat_locks.CollectionBusy):
        async with wechat_locks.collection_lock("collection-a"):
            pytest.fail("a concurrent worker must not enter the held collection")
    release.set()
    await owner
    async with wechat_locks.collection_lock("collection-a"):
        assert True


@pytest.mark.asyncio
async def test_postgres_collection_lock_rejects_busy_and_closes_connection(monkeypatch):
    database = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        host="db",
        port=5432,
        user="app",
        password="secret",
        database="clouisle",
        server_settings={},
        extra={},
    )
    monkeypatch.setattr(
        wechat_locks, "connections", SimpleNamespace(get=lambda _: database)
    )
    connection = SimpleNamespace(
        fetchval=AsyncMock(return_value=False), close=AsyncMock()
    )
    connect = AsyncMock(return_value=connection)
    monkeypatch.setattr(wechat_locks.asyncpg, "connect", connect)

    with pytest.raises(wechat_locks.CollectionBusy):
        async with wechat_locks.collection_lock("collection-b"):
            pytest.fail("a collection with a held advisory lock must be rejected")

    connection.fetchval.assert_awaited_once()
    connection.close.assert_awaited_once()
    assert connect.await_args.kwargs["host"] == "db"


@pytest.mark.asyncio
async def test_postgres_collection_lock_yields_and_closes_after_work(monkeypatch):
    database = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        host="db",
        port=5432,
        user="app",
        password="secret",
        database="clouisle",
        server_settings={},
        extra={},
    )
    monkeypatch.setattr(
        wechat_locks, "connections", SimpleNamespace(get=lambda _: database)
    )
    connection = SimpleNamespace(
        fetchval=AsyncMock(return_value=True), close=AsyncMock()
    )
    monkeypatch.setattr(
        wechat_locks.asyncpg, "connect", AsyncMock(return_value=connection)
    )

    async with wechat_locks.collection_lock("collection-c"):
        assert not connection.close.await_count

    connection.close.assert_awaited_once()
