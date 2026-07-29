from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.core import login_anomaly


@pytest.mark.asyncio
async def test_check_login_anomaly_detects_new_ip_and_user_agent(monkeypatch):
    user_id = uuid4()
    redis = MagicMock()
    redis.smembers = AsyncMock(side_effect=[{"192.0.2.1"}, {"known browser"}])
    monkeypatch.setattr(login_anomaly, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(
        login_anomaly, "now_utc", lambda: datetime(2026, 7, 20, tzinfo=UTC)
    )

    is_anomaly, details = await login_anomaly.check_login_anomaly(
        user_id, "198.51.100.1", "new browser"
    )

    assert is_anomaly is True
    assert details == {
        "new_ip": True,
        "new_user_agent": True,
        "ip_address": "198.51.100.1",
        "user_agent": "new browser",
        "login_time": "2026-07-20T00:00:00+00:00",
        "known_ips_count": 1,
        "known_uas_count": 1,
    }


@pytest.mark.asyncio
async def test_known_login_and_below_limit_history_need_no_anomaly_or_trimming(
    monkeypatch,
):
    user_id = uuid4()
    redis = MagicMock()
    redis.smembers = AsyncMock(side_effect=[{"192.0.2.1"}, {"known browser"}, set()])
    redis.sadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.scard = AsyncMock(return_value=1)
    redis.spop = AsyncMock()
    monkeypatch.setattr(login_anomaly, "get_redis", AsyncMock(return_value=redis))

    is_anomaly, details = await login_anomaly.check_login_anomaly(
        user_id, "192.0.2.1", "known browser"
    )
    assert is_anomaly is False
    assert details["new_ip"] is False
    assert details["new_user_agent"] is False

    is_anomaly, _ = await login_anomaly.check_login_anomaly(user_id, "192.0.2.1")
    assert is_anomaly is False

    await login_anomaly.record_login(user_id, "192.0.2.1")
    await login_anomaly.record_login(user_id, "192.0.2.1", "known browser")
    redis.spop.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_login_anomaly_handles_redis_failures(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        login_anomaly, "get_redis", AsyncMock(side_effect=ConnectionError())
    )
    assert await login_anomaly.check_login_anomaly(user_id, "192.0.2.1") == (False, {})

    redis = MagicMock()
    redis.smembers = AsyncMock(side_effect=RuntimeError())
    monkeypatch.setattr(login_anomaly, "get_redis", AsyncMock(return_value=redis))
    assert await login_anomaly.check_login_anomaly(user_id, "192.0.2.1") == (False, {})


@pytest.mark.asyncio
async def test_record_login_tracks_normalized_values_and_trims_history(monkeypatch):
    user_id = uuid4()
    user_agent = "a" * 201
    redis = MagicMock()
    redis.sadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.scard = AsyncMock(
        side_effect=[
            login_anomaly.MAX_TRACKED_IPS + 2,
            login_anomaly.MAX_TRACKED_UAS + 1,
        ]
    )
    redis.spop = AsyncMock()
    redis.delete = AsyncMock()
    monkeypatch.setattr(login_anomaly, "get_redis", AsyncMock(return_value=redis))

    await login_anomaly.record_login(user_id, "192.0.2.1", user_agent)

    ip_key = login_anomaly.LOGIN_IPS_KEY.format(user_id=user_id)
    ua_key = login_anomaly.LOGIN_UAS_KEY.format(user_id=user_id)
    redis.sadd.assert_has_awaits(
        [call(ip_key, "192.0.2.1"), call(ua_key, user_agent[:200])]
    )
    redis.expire.assert_has_awaits(
        [
            call(ip_key, login_anomaly.LOGIN_HISTORY_TTL),
            call(ua_key, login_anomaly.LOGIN_HISTORY_TTL),
        ]
    )
    assert redis.spop.await_count == 3

    await login_anomaly.clear_login_history(user_id)
    redis.delete.assert_awaited_once_with(ip_key, ua_key)


@pytest.mark.asyncio
async def test_record_and_clear_login_history_handle_redis_failures(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        login_anomaly, "get_redis", AsyncMock(side_effect=ConnectionError())
    )
    assert await login_anomaly.record_login(user_id, "192.0.2.1") is None
    assert await login_anomaly.clear_login_history(user_id) is None

    redis = MagicMock()
    redis.sadd = AsyncMock(side_effect=RuntimeError())
    redis.delete = AsyncMock(side_effect=RuntimeError())
    monkeypatch.setattr(login_anomaly, "get_redis", AsyncMock(return_value=redis))
    assert await login_anomaly.record_login(user_id, "192.0.2.1") is None
    assert await login_anomaly.clear_login_history(user_id) is None
