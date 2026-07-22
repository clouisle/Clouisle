from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints import login
from app.models.notification import AutoNotificationType
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value


class User:
    def __init__(self, **overrides):
        values = {
            "id": "user-id",
            "username": "alice",
            "email": "alice@example.test",
            "locale": "en",
            "hashed_password": "hashed",
            "is_active": True,
            "approval_status": "approved",
            "totp_enabled": False,
            "totp_secret": "encrypted-secret",
            "email_verified": True,
            "is_superuser": False,
            "force_password_change": False,
            "last_login": None,
            "failed_login_attempts": 2,
            "locked_until": object(),
        }
        values.update(overrides)
        self.__dict__.update(values)
        self.save = AsyncMock()


def request():
    return SimpleNamespace(headers={"user-agent": "pytest"}, client=None)


def patch_user_filter(monkeypatch, user):
    model = SimpleNamespace(
        filter=MagicMock(return_value=Query(user)),
        get_or_none=AsyncMock(return_value=user),
    )
    monkeypatch.setattr(login, "User", model)
    return model


def patch_settings(monkeypatch, **overrides):
    values = {
        "sso_enabled": False,
        "sso_allow_password_login": True,
        "enable_captcha": False,
        "require_totp": False,
        "email_verification": False,
        "session_timeout_days": 7,
        "single_session": False,
        "smtp_enabled": True,
    }
    values.update(overrides)
    getter = AsyncMock(side_effect=lambda key, default=None: values.get(key, default))
    monkeypatch.setattr(login.SiteSetting, "get_value", getter)
    return getter


@pytest.mark.anyio
async def test_login_wrong_password_lock_sends_security_notification(monkeypatch):
    user = User()
    patch_user_filter(monkeypatch, user)
    patch_settings(monkeypatch)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login.security, "verify_password", MagicMock(return_value=False)
    )
    monkeypatch.setattr(
        login, "record_failed_login", AsyncMock(return_value=(True, 0, 600))
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(login, "t", MagicMock(side_effect=lambda key, **_: key))

    with pytest.raises(BusinessError) as exc_info:
        await login.login_access_token(request(), "alice", "wrong")

    assert exc_info.value.code == ResponseCode.ACCOUNT_LOCKED
    assert exc_info.value.data == {"lockout_seconds": 600}
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["notification_type"] == (
        AutoNotificationType.SECURITY_ACCOUNT_LOCKED
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("user", "settings", "expected_key"),
    [
        (User(totp_enabled=True), {}, "requires_totp"),
        (User(), {"require_totp": True}, "requires_totp_setup"),
    ],
)
async def test_login_returns_temporary_token_for_totp_branches(
    monkeypatch, user, settings, expected_key
):
    patch_user_filter(monkeypatch, user)
    patch_settings(monkeypatch, **settings)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.security, "verify_password", MagicMock(return_value=True))
    create_token = MagicMock(return_value="temporary-jwt")
    monkeypatch.setattr(login.security, "create_access_token", create_token)

    response = await login.login_access_token(request(), "alice", "correct")

    assert response["data"] == {expected_key: True, "temp_token": "temporary-jwt"}
    assert create_token.call_args.args == (user.id,)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("decode_error", "expected_code"),
    [
        (jwt.ExpiredSignatureError(), ResponseCode.TOKEN_EXPIRED),
        (jwt.DecodeError(), ResponseCode.INVALID_TOKEN),
    ],
)
async def test_verify_totp_rejects_bad_temporary_jwt(
    monkeypatch, decode_error, expected_code
):
    monkeypatch.setattr(login.jwt, "decode", MagicMock(side_effect=decode_error))

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(request(), "bad-jwt", "123456")

    assert exc_info.value.code == expected_code


@pytest.mark.anyio
async def test_verify_totp_invalid_secret_code_records_lockout(monkeypatch):
    user = User(totp_enabled=True)
    patch_user_filter(monkeypatch, user)
    monkeypatch.setattr(login.jwt, "decode", MagicMock(return_value={"sub": user.id}))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login.totp_service, "decrypt_secret", MagicMock(return_value="secret")
    )
    monkeypatch.setattr(
        login.totp_service, "verify_totp_code", MagicMock(return_value=False)
    )
    monkeypatch.setattr(
        login.totp_security,
        "record_totp_failure",
        AsyncMock(return_value=(True, 0, 300)),
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await login.verify_totp(request(), "jwt", "000000", False)

    assert exc_info.value.code == ResponseCode.TOTP_RATE_LIMITED
    assert exc_info.value.data == {"seconds": 300}
    login.totp_service.decrypt_secret.assert_called_once_with("encrypted-secret")


@pytest.mark.anyio
async def test_verify_backup_code_success_rotates_session_and_notifies(monkeypatch):
    user = User(totp_enabled=True)
    patch_user_filter(monkeypatch, user)
    patch_settings(monkeypatch, single_session=True)
    monkeypatch.setattr(login.jwt, "decode", MagicMock(return_value={"sub": user.id}))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login.totp_service, "verify_backup_code", MagicMock(return_value=(True, 4))
    )
    monkeypatch.setattr(login.totp_security, "reset_totp_attempts", AsyncMock())
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
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
    anomaly = {"ip_address": "127.0.0.1", "login_time": "now", "user_agent": "new"}
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(True, anomaly))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(login, "invalidate_user_session", AsyncMock())
    monkeypatch.setattr(login, "set_user_session", AsyncMock())
    monkeypatch.setattr(
        login.security, "create_access_token", MagicMock(return_value="jwt")
    )
    monkeypatch.setattr(
        login.AuditLogService, "get_client_ip", MagicMock(return_value="127.0.0.1")
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(login, "t", MagicMock(side_effect=lambda key, **_: key))

    response = await login.verify_totp(request(), "temporary-jwt", "backup", True)

    assert response["data"]["access_token"] == "jwt"
    assert user.save.await_count == 2
    login.invalidate_user_session.assert_awaited_once_with(user.id, token_expires_in=5)
    login.set_user_session.assert_awaited_once_with(user.id, "jwt", 604800)
    notify.assert_awaited_once()
    assert (
        login.AuditLogService.log.await_args_list[0].kwargs["action"]
        == "use_backup_code"
    )


@pytest.mark.anyio
async def test_send_verification_queues_generated_secret(monkeypatch):
    user = User(email_verified=False)
    patch_user_filter(monkeypatch, user)
    patch_settings(monkeypatch)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        login,
        "generate_verification_code",
        AsyncMock(return_value=("123456", "secret-token")),
    )
    monkeypatch.setattr(login, "set_email_cooldown", AsyncMock())
    tasks = BackgroundTasks()
    data = SimpleNamespace(email=user.email, purpose="register")

    response = await login.send_verification(data=data, background_tasks=tasks)

    assert response["msg"]
    login.set_email_cooldown.assert_awaited_once_with(user.email, "register", 60)
    assert tasks.tasks[0].args == (user.email, "123456", "secret-token", "register")


@pytest.mark.anyio
async def test_reset_password_token_updates_password_and_unlocks_user(monkeypatch):
    user = User()
    patch_user_filter(monkeypatch, user)
    monkeypatch.setattr(
        login, "verify_token", AsyncMock(return_value=(user.email, "reset_password"))
    )
    monkeypatch.setattr(login, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(
        login.security, "get_password_hash", MagicMock(return_value="new-hash")
    )
    update_password = AsyncMock()
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "update_password_with_expiration",
        update_password,
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    data = SimpleNamespace(
        token="secret", email=None, code=None, new_password="Strong123!"
    )

    await login.reset_password(request=request(), data=data)

    update_password.assert_awaited_once_with(user, "new-hash")
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    user.save.assert_awaited_once()


@pytest.mark.anyio
async def test_reset_password_rejects_wrong_token_purpose(monkeypatch):
    monkeypatch.setattr(
        login,
        "verify_token",
        AsyncMock(return_value=("alice@example.test", "register")),
    )
    data = SimpleNamespace(
        token="secret", email=None, code=None, new_password="Strong123!"
    )

    with pytest.raises(BusinessError) as exc_info:
        await login.reset_password(request=request(), data=data)

    assert exc_info.value.code == ResponseCode.VERIFICATION_CODE_INVALID
