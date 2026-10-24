"""Session-owned locks: expiry cannot give a paused worker's document to another."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

import asyncpg
from tortoise import connections


class CollectionBusy(RuntimeError):
    pass


_SQLITE_LOCKS: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def collection_lock(name: str):
    database = connections.get("default")
    if database.capabilities.dialect == "sqlite":
        lock = _SQLITE_LOCKS.setdefault(name, asyncio.Lock())
        if lock.locked():
            raise CollectionBusy()
        async with lock:
            yield
        return
    key = int.from_bytes(
        hashlib.sha256(f"wechat:{name}".encode()).digest()[:8], "big", signed=True
    )
    connection = await asyncpg.connect(
        host=database.host,
        port=database.port,
        user=database.user,
        password=database.password,
        database=database.database,
        server_settings=database.server_settings,
        **database.extra,
    )
    try:
        if not await connection.fetchval(
            "SELECT pg_try_advisory_lock($1::bigint)", key
        ):
            raise CollectionBusy()
        yield
    finally:
        await connection.close()
