from datetime import timedelta

import pytest

from app.core import login_security
from app.core.timezone import now_utc


class FakeUser:
    def __init__(
        self, *, failed_attempts: int = 0, locked_until: object = None
    ) -> None:
        self.failed_login_attempts = failed_attempts
        self.locked_until = locked_until
        self.save_count = 0

    async def save(self) -> None:
        self.save_count += 1


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: list[tuple[str, int]] = []

    async def get(self, key: str) -> int | None:
        return self.values.get(key)

    async def incr(self, key: str) -> None:
        self.values[key] = self.values.get(key, 0) + 1

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations.append((key, ttl))

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_check_account_locked_resets_only_expired_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = now_utc()
    monkeypatch.setattr(login_security, "now_utc", lambda: now)

    active_user = FakeUser(locked_until=now + timedelta(seconds=12))
    assert await login_security.check_account_locked(active_user) == (True, 12)
    assert active_user.save_count == 0

    expired_user = FakeUser(failed_attempts=3, locked_until=now - timedelta(seconds=1))
    assert await login_security.check_account_locked(expired_user) == (False, None)
    assert expired_user.locked_until is None
    assert expired_user.failed_login_attempts == 0
    assert expired_user.save_count == 1


@pytest.mark.asyncio
async def test_check_account_locked_returns_false_when_user_not_locked():
    user = FakeUser()

    assert await login_security.check_account_locked(user) == (False, None)
    assert user.save_count == 0


@pytest.mark.asyncio
async def test_record_failed_login_locks_at_configured_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_value(key: str, default: object = None) -> object:
        return {"max_login_attempts": 2, "lockout_duration_minutes": 3}.get(
            key, default
        )

    now = now_utc()
    monkeypatch.setattr(login_security.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(login_security, "now_utc", lambda: now)

    user = FakeUser(failed_attempts=0)
    assert await login_security.record_failed_login(user) == (False, 1, None)
    assert await login_security.record_failed_login(user) == (True, 0, 180)
    assert user.locked_until == now + timedelta(minutes=3)
    assert user.save_count == 2


@pytest.mark.asyncio
async def test_reset_login_attempts_avoids_unneeded_save() -> None:
    clean_user = FakeUser()
    await login_security.reset_login_attempts(clean_user)
    assert clean_user.save_count == 0

    user = FakeUser(failed_attempts=1, locked_until=now_utc())
    await login_security.reset_login_attempts(user)
    assert (user.failed_login_attempts, user.locked_until, user.save_count) == (
        0,
        None,
        1,
    )


@pytest.mark.asyncio
async def test_ip_login_attempts_increment_expire_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(login_security, "get_redis", fake_get_redis)

    assert await login_security.get_login_attempts_by_ip("127.0.0.1") == 0
    await login_security.record_ip_login_attempt("127.0.0.1", ttl=60)
    assert await login_security.get_login_attempts_by_ip("127.0.0.1") == 1
    assert redis.expirations == [("login:attempts:ip:127.0.0.1", 60)]
    await login_security.reset_ip_login_attempts("127.0.0.1")
    assert await login_security.get_login_attempts_by_ip("127.0.0.1") == 0
