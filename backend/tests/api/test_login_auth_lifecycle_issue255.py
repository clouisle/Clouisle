from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.api.v1.endpoints import login
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.verification import SendVerificationRequest


def _request(path: str = "/api/v1/login/access-token") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 50000),
        }
    )


def _user(**overrides: object) -> SimpleNamespace:
    values = {
        "id": "user-id",
        "username": "alice",
        "email": "alice@example.com",
        "locale": "en",
        "hashed_password": "stored-hash",
        "is_active": True,
        "approval_status": "approved",
        "totp_enabled": False,
        "email_verified": True,
        "is_superuser": False,
        "force_password_change": False,
        "last_login": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> AsyncMock:
    values = {
        "sso_enabled": False,
        "sso_allow_password_login": True,
        "enable_captcha": False,
        "require_totp": False,
        "email_verification": True,
        "session_timeout_days": 7,
        "single_session": False,
        **overrides,
    }
    get_value = AsyncMock(side_effect=lambda key, default: values.get(key, default))
    monkeypatch.setattr(login.SiteSetting, "get_value", get_value)
    return get_value


def _patch_user_lookup(
    monkeypatch: pytest.MonkeyPatch, user: SimpleNamespace | None
) -> Mock:
    query = Mock()
    query.first = AsyncMock(return_value=user)
    model = Mock()
    model.filter.return_value = query
    model.get_or_none = AsyncMock(return_value=user)
    monkeypatch.setattr(login, "User", model)
    return model


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_overrides", "locked", "password_valid", "expected_code"),
    [
        ({}, (True, 30), True, ResponseCode.ACCOUNT_LOCKED),
        ({"hashed_password": ""}, (False, 0), True, ResponseCode.INVALID_CREDENTIALS),
        ({}, (False, 0), False, ResponseCode.INVALID_CREDENTIALS),
        ({"is_active": False}, (False, 0), True, ResponseCode.INACTIVE_USER),
        (
            {"is_active": False, "approval_status": "pending"},
            (False, 0),
            True,
            ResponseCode.INACTIVE_USER,
        ),
    ],
)
async def test_password_login_rejects_account_guard_failures(
    monkeypatch: pytest.MonkeyPatch,
    user_overrides: dict[str, object],
    locked: tuple[bool, int],
    password_valid: bool,
    expected_code: ResponseCode,
) -> None:
    user = _user(**user_overrides)
    _patch_settings(monkeypatch)
    _patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(login, "check_account_locked", AsyncMock(return_value=locked))
    monkeypatch.setattr(
        login.security, "verify_password", Mock(return_value=password_valid)
    )
    monkeypatch.setattr(
        login, "record_failed_login", AsyncMock(return_value=(False, 2, None))
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await login.login_access_token(_request(), "alice", "test-password")

    assert exc_info.value.code == expected_code
    if locked[0]:
        assert exc_info.value.data == {"remaining_seconds": 30}
    elif not password_valid:
        assert exc_info.value.data == {"remaining_attempts": 2}


@pytest.mark.asyncio
async def test_password_login_creates_single_session_for_expired_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    _patch_settings(monkeypatch, session_timeout_days=2, single_session=True)
    _patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.security, "verify_password", Mock(return_value=True))
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login.PasswordExpirationService, "is_user_exempt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "should_warn_user",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "days_until_expiration",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        login,
        "check_login_anomaly",
        AsyncMock(
            return_value=(
                True,
                {
                    "ip_address": "127.0.0.1",
                    "login_time": "now",
                    "user_agent": "pytest",
                },
            )
        ),
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(
        login.AuditLogService, "get_client_ip", Mock(return_value="127.0.0.1")
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    invalidate = AsyncMock()
    store_session = AsyncMock()
    monkeypatch.setattr(login, "invalidate_user_session", invalidate)
    monkeypatch.setattr(login, "set_user_session", store_session)
    monkeypatch.setattr(
        login.security, "create_access_token", Mock(return_value="access-token")
    )

    result = await login.login_access_token(
        _request(), "alice@example.com", "test-password"
    )

    assert result["data"] == {
        "access_token": "access-token",
        "token_type": "bearer",
        "force_password_change": True,
        "reason": "expired",
    }
    assert user.force_password_change is True
    assert user.save.await_count == 2
    notify.assert_awaited_once()
    invalidate.assert_awaited_once_with(user.id, token_expires_in=5)
    store_session.assert_awaited_once_with(user.id, "access-token", 172800)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "decode_error", "blacklist_calls", "clear_calls", "audit_calls"),
    [
        ({"sub": "user-id", "exp": 2147483647}, None, 1, 1, 1),
        ({"sub": "user-id", "exp": 0}, None, 0, 1, 1),
        ({"exp": 2147483647}, None, 1, 0, 0),
        ({}, jwt.InvalidTokenError(), 0, 0, 0),
    ],
)
async def test_logout_safely_invalidates_available_session_state(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    decode_error: Exception | None,
    blacklist_calls: int,
    clear_calls: int,
    audit_calls: int,
) -> None:
    user = _user()
    decode = Mock(side_effect=decode_error, return_value=payload)
    monkeypatch.setattr(login.jwt, "decode", decode)
    _patch_user_lookup(monkeypatch, user)
    blacklist = AsyncMock()
    clear = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(login, "add_token_to_blacklist", blacklist)
    monkeypatch.setattr("app.core.redis.clear_user_session", clear)
    monkeypatch.setattr(login.AuditLogService, "log", audit)

    result = await login.logout(_request("/api/v1/logout"), "access-token")

    assert result["data"] is None
    assert blacklist.await_count == blacklist_calls
    assert clear.await_count == clear_calls
    assert audit.await_count == audit_calls
    if blacklist_calls:
        blacklist.assert_awaited_once_with("access-token", 5)


@pytest.mark.asyncio
async def test_send_verification_enforces_cooldown_without_sending_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_settings(monkeypatch, smtp_enabled=True)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(False, 42))
    )
    generate = AsyncMock()
    send_email = AsyncMock()
    monkeypatch.setattr(login, "generate_verification_code", generate)
    monkeypatch.setattr(login, "send_verification_email", send_email)

    with pytest.raises(BusinessError) as exc_info:
        await login.send_verification(
            data=SendVerificationRequest(email="alice@example.com", purpose="register"),
            background_tasks=BackgroundTasks(),
        )

    assert exc_info.value.code == ResponseCode.EMAIL_SEND_TOO_FREQUENT
    assert exc_info.value.data == {"remaining_seconds": 42}
    generate.assert_not_awaited()
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_verification_queues_email_for_unverified_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user(email_verified=False)
    _patch_settings(monkeypatch, smtp_enabled=True)
    _patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        login,
        "generate_verification_code",
        AsyncMock(return_value=("test-code", "test-token")),
    )
    cooldown = AsyncMock()
    send_email = AsyncMock()
    monkeypatch.setattr(login, "set_email_cooldown", cooldown)
    monkeypatch.setattr(login, "send_verification_email", send_email)
    background_tasks = BackgroundTasks()

    result = await login.send_verification(
        data=SendVerificationRequest(email=user.email, purpose="register"),
        background_tasks=background_tasks,
    )

    assert result["data"] is None
    cooldown.assert_awaited_once_with(user.email, "register", 60)
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is send_email
