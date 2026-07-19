from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import password, totp_security
from app.services.password_expiration import PasswordExpirationService


@pytest.mark.asyncio
async def test_validate_password_enforces_configured_rules_and_history(monkeypatch):
    settings = {
        "min_password_length": 12,
        "require_uppercase": True,
        "require_number": True,
        "require_special_char": True,
    }
    monkeypatch.setattr(
        password.SiteSetting,
        "get_value",
        AsyncMock(side_effect=lambda key, default: settings.get(key, default)),
    )
    monkeypatch.setattr(
        PasswordExpirationService,
        "check_password_history",
        AsyncMock(return_value=True),
    )

    valid, errors = await password.validate_password("short", SimpleNamespace())

    assert not valid
    assert errors == [
        "password_min_length:12",
        "password_require_uppercase",
        "password_require_number",
        "password_require_special",
        "password_recently_used",
    ]


@pytest.mark.asyncio
async def test_validate_password_accepts_compliant_password_without_user(monkeypatch):
    monkeypatch.setattr(
        password.SiteSetting,
        "get_value",
        AsyncMock(side_effect=[8, True, True, True]),
    )

    assert await password.validate_password("Valid12!") == (True, [])


def test_password_error_translation_and_requirements(monkeypatch):
    monkeypatch.setattr(
        password,
        "t",
        lambda key, **kwargs: f"{key}:{kwargs.get('length', '')}",
    )

    assert password.translate_password_validation_errors(
        ["password_min_length:14", "password_require_number"]
    ) == ["password_min_length:14", "password_require_number:"]
    assert password.get_password_requirements_sync(10, False, False, False) == [
        "至少 10 个字符"
    ]
    assert password.get_password_requirements_sync(8, True, True, True) == [
        "至少 8 个字符",
        "至少一个大写字母",
        "至少一个数字",
        "至少一个特殊字符",
    ]


@pytest.mark.asyncio
async def test_totp_rate_limit_reports_lock_state(monkeypatch):
    redis = SimpleNamespace(ttl=AsyncMock(side_effect=[0, 120]))
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.check_totp_rate_limit("user-1") == (False, None)
    assert await totp_security.check_totp_rate_limit("user-1") == (True, 120)
    redis.ttl.assert_awaited_with("totp:attempts:user-1:locked")


@pytest.mark.asyncio
async def test_totp_failure_first_attempt_and_lockout(monkeypatch):
    redis = SimpleNamespace(
        incr=AsyncMock(side_effect=[1, totp_security.MAX_ATTEMPTS]),
        expire=AsyncMock(),
        setex=AsyncMock(),
    )
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.record_totp_failure("user-1") == (False, 4, None)
    assert await totp_security.record_totp_failure("user-1") == (
        True,
        0,
        totp_security.LOCKOUT_DURATION,
    )
    redis.expire.assert_awaited_once_with(
        "totp:attempts:user-1", totp_security.ATTEMPT_WINDOW
    )
    redis.setex.assert_awaited_once_with(
        "totp:attempts:user-1:locked", totp_security.LOCKOUT_DURATION, "1"
    )


@pytest.mark.asyncio
async def test_reset_totp_attempts_removes_attempt_and_lock_keys(monkeypatch):
    redis = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(totp_security, "get_redis", AsyncMock(return_value=redis))

    assert await totp_security.reset_totp_attempts("user-1") is None
    assert redis.delete.await_args_list == [
        (("totp:attempts:user-1",), {}),
        (("totp:attempts:user-1:locked",), {}),
    ]
