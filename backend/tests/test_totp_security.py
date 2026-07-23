from unittest.mock import AsyncMock, call

import pytest

from app.core import totp_security


@pytest.mark.asyncio
async def test_check_totp_rate_limit_only_locks_for_positive_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = AsyncMock()
    redis.ttl.side_effect = [120, 0]
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.check_totp_rate_limit("user") == (True, 120)
    assert await totp_security.check_totp_rate_limit("user") == (False, None)


@pytest.mark.asyncio
async def test_record_totp_failure_sets_window_on_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = AsyncMock()
    redis.incr.return_value = 1
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.record_totp_failure("user") == (False, 4, None)
    redis.expire.assert_awaited_once_with("totp:attempts:user", 300)
    redis.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_totp_failure_locks_at_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = AsyncMock()
    redis.incr.return_value = 5
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.record_totp_failure("user") == (True, 0, 900)
    redis.setex.assert_awaited_once_with("totp:attempts:user:locked", 900, "1")


@pytest.mark.asyncio
async def test_reset_totp_attempts_deletes_attempt_and_lock_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = AsyncMock()
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    await totp_security.reset_totp_attempts("user")

    redis.delete.assert_has_awaits(
        [call("totp:attempts:user"), call("totp:attempts:user:locked")]
    )
