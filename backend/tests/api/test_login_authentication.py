from unittest.mock import AsyncMock, Mock

import jwt
import pytest

from app.api.v1.endpoints import login as login_endpoints
from app.schemas.response import BusinessError, ResponseCode


class Request:
    headers = {"user-agent": "pytest"}
    client = None


class User:
    id = "user-id"
    username = "alice"
    email = "alice@example.com"
    locale = "en"
    hashed_password = "hashed"
    is_active = True
    approval_status = "approved"
    totp_enabled = False
    totp_secret = None
    email_verified = True
    is_superuser = False
    force_password_change = False
    last_login = None

    def __init__(self) -> None:
        self.save = AsyncMock()


class Query:
    def __init__(self, user: User | None) -> None:
        self.user = user

    async def first(self) -> User | None:
        return self.user


def patch_login_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    values = {
        "sso_enabled": False,
        "sso_allow_password_login": True,
        "enable_captcha": False,
        **overrides,
    }

    async def get_value(key: str, default: object = None) -> object:
        return values.get(key, default)

    monkeypatch.setattr(login_endpoints.SiteSetting, "get_value", get_value)


def patch_user_lookup(monkeypatch: pytest.MonkeyPatch, user: User | None) -> Mock:
    model = Mock()
    model.filter.side_effect = lambda **_kwargs: Query(user)
    model.get_or_none = AsyncMock(return_value=user)
    monkeypatch.setattr(login_endpoints, "User", model)
    return model


@pytest.mark.asyncio
async def test_password_login_rejects_disabled_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_login_settings(monkeypatch, sso_enabled=True, sso_allow_password_login=False)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.login_access_token(Request(), "alice", "password")

    assert exc_info.value.code == ResponseCode.PASSWORD_LOGIN_DISABLED


@pytest.mark.asyncio
async def test_password_login_unknown_user_is_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_login_settings(monkeypatch)
    patch_user_lookup(monkeypatch, None)
    audit = AsyncMock()
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.login_access_token(
            Request(), "missing@example.com", "password"
        )

    assert exc_info.value.code == ResponseCode.INVALID_CREDENTIALS
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["error_message"] == "user_not_found"


@pytest.mark.asyncio
async def test_password_failure_that_locks_account_notifies_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User()
    patch_login_settings(monkeypatch)
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login_endpoints, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login_endpoints.security, "verify_password", Mock(return_value=False)
    )
    monkeypatch.setattr(
        login_endpoints,
        "record_failed_login",
        AsyncMock(return_value=(True, 0, 300)),
    )
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(login_endpoints.AutoNotificationService, "send_to_user", notify)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.login_access_token(Request(), "alice", "wrong")

    assert exc_info.value.code == ResponseCode.ACCOUNT_LOCKED
    assert exc_info.value.data == {"lockout_seconds": 300}
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["user_id"] == user.id


@pytest.mark.asyncio
async def test_password_login_returns_totp_challenge_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User()
    user.totp_enabled = True
    patch_login_settings(monkeypatch)
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login_endpoints, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login_endpoints.security, "verify_password", Mock(return_value=True)
    )
    create_token = Mock(return_value="temporary-token")
    monkeypatch.setattr(login_endpoints.security, "create_access_token", create_token)

    result = await login_endpoints.login_access_token(Request(), "alice", "password")

    assert result["data"] == {
        "requires_totp": True,
        "temp_token": "temporary-token",
    }
    assert create_token.call_args.kwargs["expires_delta"].total_seconds() == 300
    user.save.assert_not_awaited()


@pytest.mark.parametrize(
    ("decode_effect", "expected_code"),
    [
        (jwt.ExpiredSignatureError(), ResponseCode.TOKEN_EXPIRED),
        (jwt.DecodeError(), ResponseCode.INVALID_TOKEN),
        ({}, ResponseCode.INVALID_TOKEN),
    ],
)
@pytest.mark.asyncio
async def test_totp_rejects_invalid_temporary_tokens(
    monkeypatch: pytest.MonkeyPatch,
    decode_effect: Exception | dict[str, str],
    expected_code: ResponseCode,
) -> None:
    decode = Mock(
        side_effect=decode_effect if isinstance(decode_effect, Exception) else None,
        return_value=decode_effect if isinstance(decode_effect, dict) else None,
    )
    monkeypatch.setattr(login_endpoints.jwt, "decode", decode)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.verify_totp(Request(), "temporary-token", "123456")

    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_totp_rate_limit_stops_code_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User()
    user.totp_enabled = True
    user.totp_secret = "encrypted"
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login_endpoints.jwt, "decode", Mock(return_value={"sub": user.id})
    )
    monkeypatch.setattr(
        login_endpoints.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(True, 42)),
    )
    verify = Mock()
    monkeypatch.setattr(login_endpoints.totp_service, "verify_totp_code", verify)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.verify_totp(Request(), "temporary-token", "123456")

    assert exc_info.value.code == ResponseCode.TOTP_RATE_LIMITED
    assert exc_info.value.data == {"seconds": 42}
    verify.assert_not_called()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ((False, 2, None), ResponseCode.TOTP_INVALID),
        ((True, 0, 300), ResponseCode.TOTP_RATE_LIMITED),
    ],
)
@pytest.mark.asyncio
async def test_invalid_totp_records_failure_and_audit(
    monkeypatch: pytest.MonkeyPatch,
    failure: tuple[bool, int, int | None],
    expected_code: ResponseCode,
) -> None:
    user = User()
    user.totp_enabled = True
    user.totp_secret = "encrypted"
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login_endpoints.jwt, "decode", Mock(return_value={"sub": user.id})
    )
    monkeypatch.setattr(
        login_endpoints.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )
    monkeypatch.setattr(
        login_endpoints.totp_service, "decrypt_secret", Mock(return_value="secret")
    )
    monkeypatch.setattr(
        login_endpoints.totp_service, "verify_totp_code", Mock(return_value=False)
    )
    monkeypatch.setattr(
        login_endpoints.totp_security,
        "record_totp_failure",
        AsyncMock(return_value=failure),
    )
    audit = AsyncMock()
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", audit)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.verify_totp(
            Request(), "temporary-token", "bad-code", is_backup_code=False
        )

    assert exc_info.value.code == expected_code
    assert audit.await_args.kwargs["action"] == "verify_totp_failed"
    assert audit.await_args.kwargs["metadata"] == {"remaining_attempts": failure[1]}


@pytest.mark.asyncio
async def test_backup_code_login_persists_code_and_single_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User()
    user.totp_enabled = True
    patch_user_lookup(monkeypatch, user)
    patch_login_settings(
        monkeypatch,
        session_timeout_days=2,
        single_session=True,
    )
    monkeypatch.setattr(
        login_endpoints.jwt, "decode", Mock(return_value={"sub": user.id})
    )
    monkeypatch.setattr(
        login_endpoints.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )
    monkeypatch.setattr(
        login_endpoints.totp_service,
        "verify_backup_code",
        Mock(return_value=(True, 7)),
    )
    monkeypatch.setattr(
        login_endpoints.totp_security, "reset_totp_attempts", AsyncMock()
    )
    monkeypatch.setattr(login_endpoints, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "is_user_exempt",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "should_warn_user",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "days_until_expiration",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        login_endpoints, "check_login_anomaly", AsyncMock(return_value=(False, {}))
    )
    monkeypatch.setattr(login_endpoints, "record_login", AsyncMock())
    monkeypatch.setattr(login_endpoints, "invalidate_user_session", AsyncMock())
    set_session = AsyncMock()
    monkeypatch.setattr(login_endpoints, "set_user_session", set_session)
    monkeypatch.setattr(
        login_endpoints.security,
        "create_access_token",
        Mock(return_value="access-token"),
    )
    audit = AsyncMock()
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", audit)

    result = await login_endpoints.verify_totp(
        Request(), "temporary-token", "backup-code", is_backup_code=True
    )

    assert result["data"] == {"access_token": "access-token", "token_type": "bearer"}
    assert user.save.await_count == 2
    set_session.assert_awaited_once_with(user.id, "access-token", 172800)
    assert [call.kwargs["action"] for call in audit.await_args_list] == [
        "use_backup_code",
        "verify_totp_success",
        "login_success",
    ]
