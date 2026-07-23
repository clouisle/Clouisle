from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from starlette.requests import Request

from app.api.v1.endpoints import login
from app.schemas.response import BusinessError, ResponseCode


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/login/verify-totp",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("127.0.0.1", 50000),
        }
    )


def _user(**overrides: object) -> SimpleNamespace:
    values = {
        "id": "user-id",
        "username": "alice",
        "locale": "en",
        "totp_enabled": True,
        "totp_secret": "encrypted",
        "force_password_change": False,
        "last_login": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (jwt.ExpiredSignatureError(), ResponseCode.TOKEN_EXPIRED),
        (jwt.InvalidTokenError(), ResponseCode.INVALID_TOKEN),
    ],
)
async def test_verify_totp_rejects_invalid_temporary_tokens(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_code: ResponseCode,
) -> None:
    monkeypatch.setattr(login.jwt, "decode", Mock(side_effect=error))

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "bad-token", "123456")

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_verify_totp_rejects_token_without_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={}))

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "token", "123456", False)

    assert exc_info.value.code == ResponseCode.INVALID_TOKEN


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [None, _user(totp_enabled=False)])
async def test_verify_totp_requires_enabled_user(
    monkeypatch: pytest.MonkeyPatch, user: SimpleNamespace | None
) -> None:
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": "user-id"}))
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "token", "123456", False)

    assert exc_info.value.code == ResponseCode.TOTP_NOT_ENABLED


@pytest.mark.asyncio
async def test_verify_totp_enforces_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(True, 45)),
    )

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "token", "123456", False)

    assert exc_info.value.code == ResponseCode.TOTP_RATE_LIMITED
    assert exc_info.value.data == {"seconds": 45}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locked", "expected_code"),
    [
        (False, ResponseCode.TOTP_INVALID),
        (True, ResponseCode.TOTP_RATE_LIMITED),
    ],
)
async def test_verify_totp_records_invalid_codes(
    monkeypatch: pytest.MonkeyPatch,
    locked: bool,
    expected_code: ResponseCode,
) -> None:
    user = _user()
    audit = AsyncMock()
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )
    monkeypatch.setattr(
        login.totp_service, "decrypt_secret", Mock(return_value="secret")
    )
    monkeypatch.setattr(
        login.totp_service, "verify_totp_code", Mock(return_value=False)
    )
    monkeypatch.setattr(
        login.totp_security,
        "record_totp_failure",
        AsyncMock(return_value=(locked, 2, 60)),
    )
    monkeypatch.setattr(login.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "token", "000000", False)

    assert exc_info.value.code == expected_code
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_totp_rejects_missing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user(totp_secret=None)
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(_request(), "token", "123456", False)

    assert exc_info.value.code == ResponseCode.TOTP_NOT_ENABLED


@pytest.mark.asyncio
@pytest.mark.parametrize("backup_code", [False, True])
async def test_verify_totp_completes_secure_login(
    monkeypatch: pytest.MonkeyPatch, backup_code: bool
) -> None:
    user = _user()
    audit = AsyncMock()
    notify = AsyncMock()
    invalidate = AsyncMock()
    store_session = AsyncMock()
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )
    monkeypatch.setattr(login.totp_security, "reset_totp_attempts", AsyncMock())
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login.totp_service,
        "verify_backup_code",
        Mock(return_value=(True, 7)),
    )
    monkeypatch.setattr(
        login.totp_service, "decrypt_secret", Mock(return_value="secret")
    )
    monkeypatch.setattr(login.totp_service, "verify_totp_code", Mock(return_value=True))
    monkeypatch.setattr(
        login.PasswordExpirationService, "is_user_exempt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=False),
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
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(
        login.AuditLogService, "get_client_ip", Mock(return_value="127.0.0.1")
    )
    monkeypatch.setattr(login.AuditLogService, "log", audit)
    monkeypatch.setattr(
        login.SiteSetting,
        "get_value",
        AsyncMock(
            side_effect=lambda key, default: {"single_session": True}.get(key, default)
        ),
    )
    monkeypatch.setattr(login, "invalidate_user_session", invalidate)
    monkeypatch.setattr(login, "set_user_session", store_session)
    monkeypatch.setattr(login.security, "create_access_token", Mock(return_value="jwt"))

    result = await login.verify_totp(
        _request(), "token", "backup" if backup_code else "123456", backup_code
    )

    assert result["data"] == {"access_token": "jwt", "token_type": "bearer"}
    assert user.last_login is not None
    assert user.save.await_count == (2 if backup_code else 1)
    assert audit.await_count == (3 if backup_code else 2)
    notify.assert_awaited_once()
    invalidate.assert_awaited_once_with(user.id, token_expires_in=5)
    store_session.assert_awaited_once_with(user.id, "jwt", 604800)
