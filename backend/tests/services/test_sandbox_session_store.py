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
async def test_create_saves_session_index_and_conversation_lookup(store, redis):
    session = await store.create(
        session_id="session-1",
        conversation_id="conversation-1",
        agent_id="agent-1",
        team_id="team-1",
        ttl_hours=2,
    )

    assert session.created_at == FROZEN_NOW
    assert session.expires_at == FROZEN_NOW + timedelta(hours=2)
    redis.zadd.assert_awaited_once_with(
        store.INDEX_KEY, {"session-1": session.expires_at.timestamp()}
    )
    assert redis.setex.await_args_list[0].args[:2] == (
        "sandbox:session:session-1",
        7200,
    )
    assert (
        SandboxSession.model_validate_json(redis.setex.await_args_list[0].args[2])
        == session
    )
    redis.setex.assert_awaited_with(
        "sandbox:conversation:conversation-1", 7200, "session-1"
    )


@pytest.mark.asyncio
async def test_save_clamps_expired_session_ttl_and_skips_missing_conversation(
    store, redis
):
    session = SandboxSession(
        session_id="expired",
        created_at=FROZEN_NOW - timedelta(hours=1),
        expires_at=FROZEN_NOW,
        last_accessed_at=FROZEN_NOW,
    )

    await store.save(session)

    redis.setex.assert_awaited_once()
    assert redis.setex.await_args.args[:2] == ("sandbox:session:expired", 1)
    redis.zadd.assert_awaited_once_with(
        store.INDEX_KEY, {"expired": FROZEN_NOW.timestamp()}
    )


@pytest.mark.asyncio
async def test_get_returns_session_or_removes_missing_index_entry(store, redis):
    redis.get.return_value = None

    assert await store.get("missing") is None
    redis.zrem.assert_awaited_once_with(store.INDEX_KEY, "missing")

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
async def test_delete_and_cleanup_remove_sessions_and_conversation_mapping(
    store, redis
):
    store.get = AsyncMock(return_value=None)

    await store.delete("missing")

    redis.delete.assert_awaited_once_with("sandbox:session:missing")
    redis.zrem.assert_awaited_once_with(store.INDEX_KEY, "missing")

    session = SandboxSession(
        session_id="session-1",
        conversation_id="conversation-1",
        expires_at=FROZEN_NOW + timedelta(hours=1),
    )
    store.get = AsyncMock(return_value=session)

    await store.delete("session-1")

    redis.delete.assert_has_awaits(
        [
            call("sandbox:session:missing"),
            call("sandbox:session:session-1"),
            call("sandbox:conversation:conversation-1"),
        ]
    )
    redis.zrem.assert_has_awaits(
        [call(store.INDEX_KEY, "missing"), call(store.INDEX_KEY, "session-1")]
    )

    store.expired_session_ids = AsyncMock(return_value=["old-1", "old-2"])
    store.delete = AsyncMock()

    assert await store.cleanup_expired(limit=3) == 2
    store.expired_session_ids.assert_awaited_once_with(limit=3)
    store.delete.assert_has_awaits([call("old-1"), call("old-2")])


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
