"""Per-chat serialization for Feishu Agent receipt acceptance and processing."""

import asyncio
import hashlib
from contextlib import asynccontextmanager

import asyncpg
from tortoise import connections

_SQLITE_LOCKS: dict[str, asyncio.Lock] = {}


def chat_lock_key(integration_id, chat_id: str, user_id) -> int:
    """Stable PostgreSQL advisory-lock key for one external chat actor."""
    value = f"feishu-agent:{integration_id}:{chat_id}:{user_id}"
    return int.from_bytes(
        hashlib.sha256(value.encode()).digest()[:8], "big", signed=True
    )


@asynccontextmanager
async def chat_lock(integration_id, chat_id: str, user_id):
    """Serialize workers for one chat across processes, not just one event loop."""
    database = connections.get("default")
    name = f"{integration_id}:{chat_id}:{user_id}"
    if database.capabilities.dialect == "sqlite":
        lock = _SQLITE_LOCKS.setdefault(name, asyncio.Lock())
        async with lock:
            yield
        return

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
        await connection.execute(
            "SELECT pg_advisory_lock($1::bigint)",
            chat_lock_key(integration_id, chat_id, user_id),
        )
        yield
    finally:
        await connection.close()
