from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.api.v1.endpoints import login
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value


class UserModel:
    value = None

    @classmethod
    def filter(cls, **_kwargs):
        return Query(cls.value)

    @classmethod
    async def get_or_none(cls, **_kwargs):
        return cls.value


class User:
    def __init__(self, **overrides):
        values = {
            "id": "user-id",
            "username": "alice",
            "email": "alice@example.com",
            "locale": "en",
            "hashed_password": "hash",
            "is_active": True,
            "approval_status": "approved",
            "totp_enabled": False,
            "totp_secret": "secret",
            "email_verified": True,
            "is_superuser": False,
            "force_password_change": False,
            "last_login": None,
        }
        values.update(overrides)
        self.__dict__.update(values)
        self.save = AsyncMock()


def request(headers=()):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/login",
            "headers": list(headers),
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


def settings(values):
    async def get_value(key, default=None):
        return values.get(key, default)

    return get_value


def assert_error(error, code):
    assert error.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("password_disabled", ResponseCode.PASSWORD_LOGIN_DISABLED),
        ("missing_user", ResponseCode.INVALID_CREDENTIALS),
        ("locked", ResponseCode.ACCOUNT_LOCKED),
        ("no_password", ResponseCode.INVALID_CREDENTIALS),
        ("inactive_pending", ResponseCode.INACTIVE_USER),
        ("inactive", ResponseCode.INACTIVE_USER),
        ("email_unverified", ResponseCode.EMAIL_NOT_VERIFIED),
    ],
)
async def test_login_rejection_matrix(monkeypatch, case, expected):
    user = User()
    UserModel.value = user
    values = {"email_verification": False}
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login.SiteSetting, "get_value", settings(values))
    monkeypatch.setattr(login.security, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())

    if case == "password_disabled":
        values.update(sso_enabled=True, sso_allow_password_login=False)
    elif case == "missing_user":
        UserModel.value = None
    elif case == "locked":
        monkeypatch.setattr(
            login, "check_account_locked", AsyncMock(return_value=(True, 30))
        )
    elif case == "no_password":
        user.hashed_password = ""
    elif case.startswith("inactive"):
        user.is_active = False
        user.approval_status = "pending" if case.endswith("pending") else "approved"
    else:
        values["email_verification"] = True
        user.email_verified = False

    with pytest.raises(BusinessError) as exc:
        await login.login_access_token(request(), "alice@example.com", "password")

    assert_error(exc, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("locked", [False, True])
async def test_login_bad_password_matrix(monkeypatch, locked):
    user = User()
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login.SiteSetting, "get_value", settings({}))
    monkeypatch.setattr(login.security, "verify_password", lambda *_: False)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login,
        "record_failed_login",
        AsyncMock(return_value=(locked, 2, 120 if locked else None)),
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", notify)

    with pytest.raises(BusinessError) as exc:
        await login.login_access_token(request(), "alice", "wrong")

    assert_error(
        exc, ResponseCode.ACCOUNT_LOCKED if locked else ResponseCode.INVALID_CREDENTIALS
    )
    assert notify.await_count == int(locked)


@pytest.mark.asyncio
@pytest.mark.parametrize("required", [False, True])
async def test_login_totp_gate_matrix(monkeypatch, required):
    user = User(totp_enabled=not required)
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(
        login.SiteSetting, "get_value", settings({"require_totp": required})
    )
    monkeypatch.setattr(login.security, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        login.security, "create_access_token", lambda *_args, **_kw: "temp"
    )
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )

    result = await login.login_access_token(request(), "alice", "password")

    assert result["data"] == {
        "requires_totp_setup" if required else "requires_totp": True,
        "temp_token": "temp",
    }


async def patch_successful_login(
    monkeypatch, user, *, expired=False, exempt=False, anomaly=False, single=False
):
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(
        login.SiteSetting,
        "get_value",
        settings(
            {
                "email_verification": False,
                "session_timeout_days": 2,
                "single_session": single,
            }
        ),
    )
    monkeypatch.setattr(login.security, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        login.security, "create_access_token", lambda *_args, **_kw: "jwt"
    )
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(anomaly, {}))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(login, "invalidate_user_session", AsyncMock())
    monkeypatch.setattr(login, "set_user_session", AsyncMock())
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", AsyncMock())
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_user_exempt",
        AsyncMock(return_value=exempt),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=expired),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "should_warn_user",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "days_until_expiration",
        AsyncMock(return_value=3),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expired", "forced", "exempt", "anomaly", "single", "reason"),
    [
        (True, False, False, True, True, "expired"),
        (False, True, False, False, False, "force"),
        (True, True, True, False, False, None),
    ],
)
async def test_login_success_residual_matrix(
    monkeypatch, expired, forced, exempt, anomaly, single, reason
):
    user = User(force_password_change=forced)
    await patch_successful_login(
        monkeypatch,
        user,
        expired=expired,
        exempt=exempt,
        anomaly=anomaly,
        single=single,
    )

    result = await login.login_access_token(
        request([(b"user-agent", b"test")]), "alice", "password"
    )

    assert result["data"]["access_token"] == "jwt"
    assert result["data"].get("reason") == reason
    if expired and not forced and not exempt:
        user.save.assert_awaited()
    if single:
        login.invalidate_user_session.assert_awaited_once()
        login.set_user_session.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decode_effect", "user", "rate_limit", "expected"),
    [
        ({}, User(totp_enabled=True), (False, 0), ResponseCode.INVALID_TOKEN),
        (jwt.ExpiredSignatureError(), User(), (False, 0), ResponseCode.TOKEN_EXPIRED),
        (jwt.DecodeError(), User(), (False, 0), ResponseCode.INVALID_TOKEN),
        ({"sub": "user-id"}, None, (False, 0), ResponseCode.TOTP_NOT_ENABLED),
        (
            {"sub": "user-id"},
            User(totp_enabled=False),
            (False, 0),
            ResponseCode.TOTP_NOT_ENABLED,
        ),
        (
            {"sub": "user-id"},
            User(totp_enabled=True),
            (True, 20),
            ResponseCode.TOTP_RATE_LIMITED,
        ),
    ],
)
async def test_verify_totp_rejection_matrix(
    monkeypatch, decode_effect, user, rate_limit, expected
):
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    decode = (
        Mock(side_effect=decode_effect)
        if isinstance(decode_effect, Exception)
        else Mock(return_value=decode_effect)
    )
    monkeypatch.setattr(login.jwt, "decode", decode)
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=rate_limit)
    )

    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(request(), "temp", "123456")

    assert_error(exc, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backup,locked", [(False, False), (False, True), (True, False)]
)
async def test_verify_totp_invalid_code_matrix(monkeypatch, backup, locked):
    user = User(totp_enabled=True, totp_secret=None if not backup else "secret")
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login.jwt, "decode", lambda *_args, **_kw: {"sub": "user-id"})
    monkeypatch.setattr(
        login.totp_security,
        "check_totp_rate_limit",
        AsyncMock(return_value=(False, 0)),
    )
    monkeypatch.setattr(
        login.totp_security,
        "record_totp_failure",
        AsyncMock(return_value=(locked, 1, 60)),
    )
    monkeypatch.setattr(login.totp_service, "verify_backup_code", lambda *_: (False, 0))
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())

    expected = (
        ResponseCode.TOTP_NOT_ENABLED
        if not backup and user.totp_secret is None
        else (ResponseCode.TOTP_RATE_LIMITED if locked else ResponseCode.TOTP_INVALID)
    )
    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(request(), "temp", "bad", is_backup_code=backup)

    assert_error(exc, expected)


@pytest.mark.asyncio
async def test_verify_totp_backup_success_uses_session_and_force_change(monkeypatch):
    user = User(totp_enabled=True, force_password_change=True)
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login.jwt, "decode", lambda *_args, **_kw: {"sub": "user-id"})
    monkeypatch.setattr(login.totp_service, "verify_backup_code", lambda *_: (True, 4))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.totp_security, "reset_totp_attempts", AsyncMock())
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(True, {}))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(login, "invalidate_user_session", AsyncMock())
    monkeypatch.setattr(login, "set_user_session", AsyncMock())
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", AsyncMock())
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
        login.SiteSetting, "get_value", settings({"single_session": True})
    )
    monkeypatch.setattr(
        login.security, "create_access_token", lambda *_args, **_kw: "jwt"
    )

    result = await login.verify_totp(request(), "temp", "backup", is_backup_code=True)

    assert result["data"]["reason"] == "force"
    assert login.AuditLogService.log.await_count == 3
    login.set_user_session.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [False, True])
async def test_logout_token_matrix(monkeypatch, valid):
    user = User()
    monkeypatch.setattr(
        login.jwt,
        "decode",
        Mock(return_value={"sub": "user-id", "exp": 9999999999})
        if valid
        else Mock(side_effect=jwt.DecodeError()),
    )
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(login, "add_token_to_blacklist", AsyncMock())
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    clear = AsyncMock()
    monkeypatch.setattr("app.core.redis.clear_user_session", clear)

    result = await login.logout(request(), "token")

    assert result["code"] == ResponseCode.SUCCESS
    assert clear.await_count == int(valid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "smtp", "cooldown", "expected"),
    [
        ("send_verification", False, (True, 0), ResponseCode.EMAIL_SEND_FAILED),
        ("resend_verification", True, (False, 9), ResponseCode.EMAIL_SEND_TOO_FREQUENT),
        ("forgot_password", False, (True, 0), ResponseCode.EMAIL_SEND_FAILED),
    ],
)
async def test_email_endpoint_rejection_matrix(
    monkeypatch, endpoint, smtp, cooldown, expected
):
    monkeypatch.setattr(
        login.SiteSetting, "get_value", settings({"smtp_enabled": smtp})
    )
    monkeypatch.setattr(login, "check_email_cooldown", AsyncMock(return_value=cooldown))
    schema = {
        "send_verification": login.SendVerificationRequest.model_construct(
            email="a@example.com", purpose="register"
        ),
        "resend_verification": login.ResendVerificationRequest.model_construct(
            email="a@example.com"
        ),
        "forgot_password": login.ResetPasswordRequest.model_construct(
            email="a@example.com"
        ),
    }[endpoint]

    with pytest.raises(BusinessError) as exc:
        await getattr(login, endpoint)(data=schema, background_tasks=BackgroundTasks())

    assert_error(exc, expected)


@pytest.mark.asyncio
async def test_email_verification_and_reset_residual_paths(monkeypatch):
    user = User(email_verified=False)
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=True))
    monkeypatch.setattr(
        login, "verify_token", AsyncMock(return_value=(user.email, "register"))
    )

    code_result = await login.verify_email_by_code(
        data=login.VerifyCodeRequest.model_construct(
            email=user.email, code="123456", purpose="register"
        )
    )
    token_result = await login.verify_email_by_token("token")

    assert code_result["data"].verified is True
    assert token_result["data"].email == user.email
    assert user.save.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_result", "code_valid", "password_valid", "user", "expected"),
    [
        (None, True, True, User(), ResponseCode.VERIFICATION_CODE_INVALID),
        (
            ("a@example.com", "register"),
            True,
            True,
            User(),
            ResponseCode.VERIFICATION_CODE_INVALID,
        ),
        (
            ("a@example.com", "reset_password"),
            True,
            False,
            User(),
            ResponseCode.VALIDATION_ERROR,
        ),
        (("a@example.com", "reset_password"), True, True, None, ResponseCode.NOT_FOUND),
        (None, False, True, User(), ResponseCode.VERIFICATION_CODE_INVALID),
    ],
)
async def test_reset_password_rejection_matrix(
    monkeypatch, token_result, code_valid, password_valid, user, expected
):
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login, "verify_token", AsyncMock(return_value=token_result))
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=code_valid))
    monkeypatch.setattr(
        login,
        "validate_password",
        AsyncMock(
            return_value=(password_valid, ["weak"] if not password_valid else [])
        ),
    )
    data = login.ResetPasswordConfirmRequest.model_construct(
        token="token" if token_result is not None or code_valid else None,
        email="a@example.com",
        code="123456",
        new_password="Password123!",
    )

    with pytest.raises(BusinessError) as exc:
        await login.reset_password(request=request(), data=data)

    assert_error(exc, expected)


@pytest.mark.asyncio
async def test_reset_password_code_success(monkeypatch):
    user = User()
    UserModel.value = user
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=True))
    monkeypatch.setattr(login, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(login.security, "get_password_hash", lambda _: "new-hash")
    update = AsyncMock()
    monkeypatch.setattr(
        login.PasswordExpirationService, "update_password_with_expiration", update
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    data = login.ResetPasswordConfirmRequest.model_construct(
        token=None,
        email=user.email,
        code="123456",
        new_password="Password123!",
    )

    result = await login.reset_password(request=request(), data=data)

    assert result["code"] == ResponseCode.SUCCESS
    update.assert_awaited_once_with(user, "new-hash")
    assert user.failed_login_attempts == 0
