from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, call

import pytest

from app.services.sandbox import session_store
from app.services.sandbox.models import SandboxSession
from app.services.sandbox.session_store import SandboxSessionStore

FROZEN_NOW = datetime(2026, 7, 20, 12, tzinfo=UTC)


@pytest.fixture
def redis():
    client = AsyncMock()
    client.setex = AsyncMock()
    client.zadd = AsyncMock()
    client.get = AsyncMock()
    client.zrem = AsyncMock()
    client.delete = AsyncMock()
    client.zrangebyscore = AsyncMock()
    return client


@pytest.fixture
def store(redis, monkeypatch):
    monkeypatch.setattr(session_store, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(session_store, "now", lambda: FROZEN_NOW)
    return SandboxSessionStore()


@pytest.mark.asyncio
async def test_get_returns_session_without_discarding_expired_cleanup_entry(
    store, redis
):
    redis.get.return_value = None

    assert await store.get("missing") is None

    saved = SandboxSession(
        session_id="saved",
        expires_at=FROZEN_NOW + timedelta(hours=1),
    )
    redis.get.return_value = saved.model_dump_json()

    assert await store.get("saved") == saved


@pytest.mark.asyncio
async def test_conversation_lookup_handles_missing_and_stale_mappings(store, redis):
    redis.get.return_value = None
    assert await store.get_by_conversation("missing") is None

    redis.get.return_value = "stale-session"
    store.get = AsyncMock(return_value=None)

    assert await store.get_by_conversation("stale") is None
    redis.delete.assert_awaited_once_with("sandbox:conversation:stale")

    redis.get.return_value = "active-session"
    active = SandboxSession(
        session_id="active-session",
        expires_at=FROZEN_NOW + timedelta(hours=1),
    )
    store.get = AsyncMock(return_value=active)

    assert await store.get_by_conversation("active") == active


@pytest.mark.asyncio
async def test_touch_updates_existing_session_and_returns_none_when_absent(store):
    session = SandboxSession(
        session_id="session-1",
        expires_at=FROZEN_NOW + timedelta(hours=1),
    )
    store.get = AsyncMock(side_effect=[None, session, session])
    store.save = AsyncMock()

    assert await store.touch("missing") is None
    touched = await store.touch("session-1", disk_usage_bytes=128)
    untouched = await store.touch("session-1")

    assert touched is session
    assert untouched is session
    assert session.last_accessed_at == FROZEN_NOW
    assert session.disk_usage_bytes == 128
    store.save.assert_has_awaits([call(session), call(session)])


@pytest.mark.asyncio
async def test_touch_renews_configured_retention_from_last_activity(store):
    session = SandboxSession(
        session_id="custom-retention",
        ttl_seconds=7200,
        created_at=FROZEN_NOW - timedelta(hours=1),
        expires_at=FROZEN_NOW + timedelta(hours=1),
    )
    store.get = AsyncMock(return_value=session)
    store.save = AsyncMock()
    await store.touch(session.session_id)
    assert session.expires_at == FROZEN_NOW + timedelta(hours=2)
    assert session.created_at == FROZEN_NOW - timedelta(hours=1)


@pytest.mark.asyncio
async def test_expired_session_ids_uses_explicit_limit(store, redis):
    redis.zrangebyscore.return_value = ["expired"]

    assert await store.expired_session_ids(limit=4) == ["expired"]

    redis.zrangebyscore.assert_awaited_once_with(
        store.INDEX_KEY,
        min="-inf",
        max=FROZEN_NOW.timestamp(),
        start=0,
        num=4,
    )


def test_redis_text_decodes_bytes_and_passes_strings():
    assert session_store._redis_text(b"session-id") == "session-id"
    assert session_store._redis_text("session-id") == "session-id"
