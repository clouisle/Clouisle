from unittest.mock import AsyncMock

import pytest

from app.services import context_compression_state as state


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stored_count", "threshold", "expected"),
    [(None, 3, False), ("2", 3, False), ("3", 3, True), ("4", 3, True)],
)
async def test_is_breaker_open_handles_missing_and_threshold_counts(
    monkeypatch, stored_count, threshold, expected
):
    redis = AsyncMock()
    redis.get.return_value = stored_count
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    assert (
        await state.is_breaker_open(
            breaker_type="legacy_compact",
            conversation_id="conversation-1",
            failure_threshold=threshold,
            cooldown_seconds=60,
        )
        is expected
    )
    redis.get.assert_awaited_once_with(
        "compression_breaker:legacy_compact:conversation-1"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("redis", [None, AsyncMock()])
async def test_is_breaker_open_fails_closed_when_storage_unavailable(
    monkeypatch, redis
):
    if redis is not None:
        redis.get.side_effect = ValueError("invalid count")
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    assert not await state.is_breaker_open(
        breaker_type="session_memory_extractor",
        conversation_id="conversation-2",
        failure_threshold=2,
        cooldown_seconds=30,
    )


@pytest.mark.anyio
async def test_record_breaker_failure_increments_and_refreshes_ttl(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    await state.record_breaker_failure(
        breaker_type="session_memory_extractor",
        conversation_id="conversation-3",
        cooldown_seconds=45,
    )

    key = "compression_breaker:session_memory_extractor:conversation-3"
    redis.incr.assert_awaited_once_with(key)
    redis.expire.assert_awaited_once_with(key, 45)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["incr", "expire"])
async def test_record_breaker_failure_swallows_storage_errors(monkeypatch, operation):
    redis = AsyncMock()
    getattr(redis, operation).side_effect = RuntimeError("redis unavailable")
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    await state.record_breaker_failure(
        breaker_type="legacy_compact",
        conversation_id="conversation-4",
        cooldown_seconds=10,
    )


@pytest.mark.anyio
async def test_record_and_reset_are_noops_without_redis(monkeypatch):
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=None))

    await state.record_breaker_failure(
        breaker_type="legacy_compact",
        conversation_id="conversation-5",
        cooldown_seconds=10,
    )
    await state.reset_breaker(
        breaker_type="legacy_compact", conversation_id="conversation-5"
    )


@pytest.mark.anyio
async def test_reset_breaker_deletes_persisted_count(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    await state.reset_breaker(
        breaker_type="legacy_compact", conversation_id="conversation-6"
    )

    redis.delete.assert_awaited_once_with(
        "compression_breaker:legacy_compact:conversation-6"
    )


@pytest.mark.anyio
async def test_reset_breaker_swallows_storage_error(monkeypatch):
    redis = AsyncMock()
    redis.delete.side_effect = RuntimeError("redis unavailable")
    monkeypatch.setattr(state, "get_redis", AsyncMock(return_value=redis))

    await state.reset_breaker(
        breaker_type="legacy_compact", conversation_id="conversation-7"
    )
