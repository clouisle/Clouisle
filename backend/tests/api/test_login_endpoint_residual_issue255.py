from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from app.api.v1.endpoints import login
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.user import UserCreate
from app.schemas.verification import (
    ResendVerificationRequest,
    ResetPasswordConfirmRequest,
    ResetPasswordRequest,
    SendVerificationRequest,
    VerifyCodeRequest,
)


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value


class CountQuery:
    def __init__(self, count: int):
        self.count_value = count

    async def count(self):
        return self.count_value


class AwaitableUser:
    def __init__(self, user):
        self.user = user

    def prefetch_related(self, *_args):
        return self

    def __await__(self):
        async def result():
            return self.user

        return result().__await__()


class FakeUser:
    def __init__(self, **overrides):
        self.id = "user-id"
        self.username = "alice"
        self.email = "alice@example.com"
        self.locale = "en"
        self.hashed_password = "hashed"
        self.is_active = True
        self.approval_status = "approved"
        self.totp_enabled = False
        self.totp_secret = "encrypted-secret"
        self.email_verified = True
        self.is_superuser = False
        self.force_password_change = False
        self.failed_login_attempts = 3
        self.locked_until = "locked"
        self.last_login = None
        self.saved = 0
        self.roles = SimpleNamespace(add=AsyncMock())
        for key, value in overrides.items():
            setattr(self, key, value)

    async def save(self):
        self.saved += 1


def request(path: str = "/api/v1/login/access-token") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"user-agent", b"pytest")],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("127.0.0.1", 1234),
        }
    )


def patch_settings(monkeypatch, **values):
    async def get_value(key, default=None):
        return values.get(key, default)

    monkeypatch.setattr(login.SiteSetting, "get_value", get_value)


def patch_user_lookup(monkeypatch, user):
    class UserModel:
        @staticmethod
        def filter(**_kwargs):
            return Query(user)

        get_or_none = AsyncMock(return_value=user)

    monkeypatch.setattr(login, "User", UserModel)


def patch_login_dependencies(monkeypatch, user, **settings):
    defaults = {
        "sso_enabled": False,
        "sso_allow_password_login": True,
        "enable_captcha": False,
        "require_totp": False,
        "email_verification": False,
        "session_timeout_days": 2,
        "single_session": False,
    }
    defaults.update(settings)
    patch_settings(monkeypatch, **defaults)
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(login.security, "verify_password", Mock(return_value=True))
    monkeypatch.setattr(
        login.security, "create_access_token", Mock(return_value="mock-jwt")
    )
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(False, {}))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        login.AuditLogService, "get_client_ip", Mock(return_value="127.0.0.1")
    )
    monkeypatch.setattr(login.AutoNotificationService, "send_to_user", AsyncMock())
    monkeypatch.setattr(login, "invalidate_user_session", AsyncMock())
    monkeypatch.setattr(login, "set_user_session", AsyncMock())
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "settings", "code"),
    [
        (None, {}, ResponseCode.INVALID_CREDENTIALS),
        (FakeUser(hashed_password=""), {}, ResponseCode.INVALID_CREDENTIALS),
        (
            FakeUser(is_active=False, approval_status="pending"),
            {},
            ResponseCode.INACTIVE_USER,
        ),
        (
            FakeUser(email_verified=False),
            {"email_verification": True},
            ResponseCode.EMAIL_NOT_VERIFIED,
        ),
    ],
)
async def test_login_rejects_residual_account_states(monkeypatch, user, settings, code):
    patch_login_dependencies(monkeypatch, user, **settings)

    with pytest.raises(BusinessError) as exc:
        await login.login_access_token(request(), "alice", "not-a-real-password")

    assert exc.value.code == code


@pytest.mark.asyncio
async def test_login_rejects_locked_account(monkeypatch):
    user = FakeUser()
    patch_login_dependencies(monkeypatch, user)
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(True, 45))
    )

    with pytest.raises(BusinessError) as exc:
        await login.login_access_token(request(), "alice", "not-a-real-password")

    assert exc.value.code == ResponseCode.ACCOUNT_LOCKED
    assert exc.value.data == {"remaining_seconds": 45}


@pytest.mark.asyncio
@pytest.mark.parametrize("locked", [False, True])
async def test_login_bad_password_records_failure_and_optional_lock(
    monkeypatch, locked
):
    user = FakeUser()
    patch_login_dependencies(monkeypatch, user)
    monkeypatch.setattr(login.security, "verify_password", Mock(return_value=False))
    monkeypatch.setattr(
        login, "record_failed_login", AsyncMock(return_value=(locked, 2, 600))
    )

    with pytest.raises(BusinessError) as exc:
        await login.login_access_token(request(), "alice", "not-a-real-password")

    assert exc.value.code == (
        ResponseCode.ACCOUNT_LOCKED if locked else ResponseCode.INVALID_CREDENTIALS
    )
    assert login.AuditLogService.log.await_count == 1
    assert login.AutoNotificationService.send_to_user.await_count == int(locked)


@pytest.mark.asyncio
async def test_login_returns_totp_and_required_setup_tokens(monkeypatch):
    user = FakeUser(totp_enabled=True)
    patch_login_dependencies(monkeypatch, user)

    result = await login.login_access_token(request(), "alice", "not-a-real-password")
    assert result["data"] == {"requires_totp": True, "temp_token": "mock-jwt"}

    user.totp_enabled = False
    patch_login_dependencies(monkeypatch, user, require_totp=True)
    result = await login.login_access_token(request(), "alice", "not-a-real-password")
    assert result["data"] == {"requires_totp_setup": True, "temp_token": "mock-jwt"}


@pytest.mark.asyncio
async def test_login_expired_password_anomaly_and_single_session(monkeypatch):
    user = FakeUser()
    patch_login_dependencies(monkeypatch, user, single_session=True)
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=True),
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

    result = await login.login_access_token(request(), "alice", "not-a-real-password")

    assert result["data"]["reason"] == "expired"
    assert user.force_password_change is True
    login.invalidate_user_session.assert_awaited_once_with(
        "user-id", token_expires_in=5
    )
    login.set_user_session.assert_awaited_once_with("user-id", "mock-jwt", 172800)
    login.AutoNotificationService.send_to_user.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decode_effect", "code"),
    [
        (jwt.ExpiredSignatureError(), ResponseCode.TOKEN_EXPIRED),
        (jwt.InvalidTokenError(), ResponseCode.INVALID_TOKEN),
        ({}, ResponseCode.INVALID_TOKEN),
    ],
)
async def test_verify_totp_rejects_bad_temporary_jwt(monkeypatch, decode_effect, code):
    decoder = Mock()
    if isinstance(decode_effect, BaseException):
        decoder.side_effect = decode_effect
    else:
        decoder.return_value = decode_effect
    monkeypatch.setattr(login.jwt, "decode", decoder)

    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(
            request(), "mock-temp-jwt", "000000", is_backup_code=False
        )

    assert exc.value.code == code


@pytest.mark.asyncio
async def test_verify_totp_rate_limit_and_missing_secret(monkeypatch):
    user = FakeUser(totp_enabled=True)
    patch_login_dependencies(monkeypatch, user)
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(True, 30))
    )

    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(
            request(), "mock-temp-jwt", "000000", is_backup_code=False
        )
    assert exc.value.code == ResponseCode.TOTP_RATE_LIMITED

    user.totp_secret = None
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(
            request(), "mock-temp-jwt", "000000", is_backup_code=False
        )
    assert exc.value.code == ResponseCode.TOTP_NOT_ENABLED


@pytest.mark.asyncio
@pytest.mark.parametrize("locked", [False, True])
async def test_verify_totp_invalid_code_records_failure(monkeypatch, locked):
    user = FakeUser(totp_enabled=True)
    patch_login_dependencies(monkeypatch, user)
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(
        login.totp_security,
        "record_totp_failure",
        AsyncMock(return_value=(locked, 1, 120)),
    )
    monkeypatch.setattr(
        login.totp_service, "decrypt_secret", Mock(return_value="secret")
    )
    monkeypatch.setattr(
        login.totp_service, "verify_totp_code", Mock(return_value=False)
    )

    with pytest.raises(BusinessError) as exc:
        await login.verify_totp(
            request(), "mock-temp-jwt", "000000", is_backup_code=False
        )

    assert exc.value.code == (
        ResponseCode.TOTP_RATE_LIMITED if locked else ResponseCode.TOTP_INVALID
    )


@pytest.mark.asyncio
async def test_verify_totp_backup_code_success_uses_mocked_sessions(monkeypatch):
    user = FakeUser(totp_enabled=True, force_password_change=True)
    patch_login_dependencies(monkeypatch, user, single_session=True)
    monkeypatch.setattr(login.jwt, "decode", Mock(return_value={"sub": user.id}))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.totp_security, "reset_totp_attempts", AsyncMock())
    monkeypatch.setattr(
        login.totp_service, "verify_backup_code", Mock(return_value=(True, 4))
    )

    result = await login.verify_totp(
        request(), "mock-temp-jwt", "mock-backup-code", is_backup_code=True
    )

    assert result["data"]["reason"] == "force"
    login.invalidate_user_session.assert_awaited_once()
    login.set_user_session.assert_awaited_once_with("user-id", "mock-jwt", 172800)
    assert login.AuditLogService.log.await_count == 3


@pytest.mark.asyncio
async def test_logout_blacklists_and_clears_mocked_session(monkeypatch):
    user = FakeUser()
    monkeypatch.setattr(
        login.jwt, "decode", Mock(return_value={"sub": user.id, "exp": 9999999999})
    )
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(login, "add_token_to_blacklist", AsyncMock())
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    clear_session = AsyncMock()
    monkeypatch.setattr("app.core.redis.clear_user_session", clear_session)

    result = await login.logout(request("/api/v1/logout"), "mock-jwt")

    assert result["code"] == ResponseCode.SUCCESS
    login.add_token_to_blacklist.assert_awaited_once_with("mock-jwt", 5)
    clear_session.assert_awaited_once_with("user-id")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "user_in", "code"),
    [
        ({"allow_registration": False}, {}, ResponseCode.REGISTRATION_DISABLED),
        (
            {"allow_registration": True, "require_terms_acceptance_on_register": True},
            {"terms_accepted": False},
            ResponseCode.VALIDATION_ERROR,
        ),
    ],
)
async def test_register_rejects_disabled_or_missing_terms(
    monkeypatch, settings, user_in, code
):
    class UserModel:
        @staticmethod
        def all():
            return CountQuery(1)

    monkeypatch.setattr(login, "User", UserModel)
    patch_settings(monkeypatch, **settings)
    data = UserCreate(
        username="alice",
        email="alice@example.com",
        password="MockStrongPassword123!",
        **user_in,
    )

    with pytest.raises(BusinessError) as exc:
        await login.register(request=request("/api/v1/register"), user_in=data)

    assert exc.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("password_result", "username_user", "email_user", "code"),
    [
        ((False, ["too_short"]), None, None, ResponseCode.VALIDATION_ERROR),
        ((True, []), object(), None, ResponseCode.USERNAME_EXISTS),
        ((True, []), None, object(), ResponseCode.EMAIL_EXISTS),
    ],
)
async def test_register_rejects_password_and_duplicates(
    monkeypatch, password_result, username_user, email_user, code
):
    class UserModel:
        @staticmethod
        def all():
            return CountQuery(1)

        @staticmethod
        def filter(**kwargs):
            return Query(username_user if "username" in kwargs else email_user)

    monkeypatch.setattr(login, "User", UserModel)
    patch_settings(monkeypatch, allow_registration=True)
    monkeypatch.setattr(
        login, "validate_password", AsyncMock(return_value=password_result)
    )

    with pytest.raises(BusinessError) as exc:
        await login.register(
            request=request("/api/v1/register"),
            user_in=UserCreate(
                username="alice",
                email="alice@example.com",
                password="MockStrongPassword123!",
            ),
        )

    assert exc.value.code == code


@pytest.mark.asyncio
async def test_register_pending_approval_sends_mocked_notification(monkeypatch):
    created = FakeUser(is_active=False, approval_status="pending", email_verified=False)

    class UserModel:
        @staticmethod
        def all():
            return CountQuery(1)

        @staticmethod
        def filter(**_kwargs):
            return Query()

        create = AsyncMock(return_value=created)

        @staticmethod
        def get(**_kwargs):
            return AwaitableUser(created)

    patch_settings(
        monkeypatch,
        allow_registration=True,
        require_approval=True,
        email_verification=True,
        force_password_change_first_login=True,
    )
    monkeypatch.setattr(login, "User", UserModel)
    monkeypatch.setattr(login, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(
        login.security, "get_password_hash", Mock(return_value="mock-hash")
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "calculate_expiration_date",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(login.AutoNotificationService, "send_global", AsyncMock())
    monkeypatch.setattr(login, "get_default_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(
        login, "serialize_user_with_sso", AsyncMock(return_value={"id": created.id})
    )
    monkeypatch.setattr("app.services.team_role_sync.assign_default_role", AsyncMock())
    monkeypatch.setattr(
        "app.services.team_role_sync.assign_default_team", AsyncMock(return_value=True)
    )

    result = await login.register(
        request=request("/api/v1/register"),
        user_in=UserCreate(
            username="alice",
            email="alice@example.com",
            password="MockStrongPassword123!",
        ),
    )

    assert result["data"] == {"id": "user-id"}
    login.AutoNotificationService.send_global.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_verification_success_mocks_email_and_cooldown(monkeypatch):
    user = FakeUser(email_verified=False)
    patch_settings(monkeypatch, smtp_enabled=True)
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    monkeypatch.setattr(
        login,
        "generate_verification_code",
        AsyncMock(return_value=("123456", "mock-token")),
    )
    monkeypatch.setattr(login, "set_email_cooldown", AsyncMock())
    send_email = AsyncMock()
    monkeypatch.setattr(login, "send_verification_email", send_email)
    tasks = BackgroundTasks()

    result = await login.send_verification(
        data=SendVerificationRequest(email=user.email), background_tasks=tasks
    )
    await tasks()

    assert result["code"] == ResponseCode.SUCCESS
    send_email.assert_awaited_once_with(user.email, "123456", "mock-token", "register")


@pytest.mark.asyncio
@pytest.mark.parametrize("by_token", [False, True])
async def test_verify_email_success_updates_user(monkeypatch, by_token):
    user = FakeUser(email_verified=False)
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=True))
    monkeypatch.setattr(
        login, "verify_token", AsyncMock(return_value=(user.email, "register"))
    )

    if by_token:
        result = await login.verify_email_by_token("mock-token")
    else:
        result = await login.verify_email_by_code(
            data=VerifyCodeRequest(email=user.email, code="123456")
        )

    assert result["data"].verified is True
    assert user.email_verified is True
    assert user.saved == 1


@pytest.mark.asyncio
async def test_resend_and_forgot_password_hide_unknown_email(monkeypatch):
    patch_settings(monkeypatch, smtp_enabled=True)
    patch_user_lookup(monkeypatch, None)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    generate = AsyncMock()
    monkeypatch.setattr(login, "generate_verification_code", generate)

    resend = await login.resend_verification(
        data=ResendVerificationRequest(email="unknown@example.com"),
        background_tasks=BackgroundTasks(),
    )
    forgot = await login.forgot_password(
        data=ResetPasswordRequest(email="unknown@example.com"),
        background_tasks=BackgroundTasks(),
    )

    assert resend["code"] == forgot["code"] == ResponseCode.SUCCESS
    generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_result", "password_result", "user", "code"),
    [
        (None, (True, []), FakeUser(), ResponseCode.VERIFICATION_CODE_INVALID),
        (
            ("alice@example.com", "register"),
            (True, []),
            FakeUser(),
            ResponseCode.VERIFICATION_CODE_INVALID,
        ),
        (
            ("alice@example.com", "reset_password"),
            (False, ["weak"]),
            FakeUser(),
            ResponseCode.VALIDATION_ERROR,
        ),
        (
            ("alice@example.com", "reset_password"),
            (True, []),
            None,
            ResponseCode.NOT_FOUND,
        ),
    ],
)
async def test_reset_password_rejects_invalid_token_password_or_user(
    monkeypatch, token_result, password_result, user, code
):
    monkeypatch.setattr(login, "verify_token", AsyncMock(return_value=token_result))
    monkeypatch.setattr(
        login, "validate_password", AsyncMock(return_value=password_result)
    )
    patch_user_lookup(monkeypatch, user)

    with pytest.raises(BusinessError) as exc:
        await login.reset_password(
            request=request("/api/v1/reset-password"),
            data=ResetPasswordConfirmRequest(
                token="mock-reset-token", new_password="MockNewPassword123!"
            ),
        )

    assert exc.value.code == code


@pytest.mark.asyncio
async def test_reset_password_code_success_mocks_hash_and_session_state(monkeypatch):
    user = FakeUser()
    patch_user_lookup(monkeypatch, user)
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=True))
    monkeypatch.setattr(login, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(
        login.security, "get_password_hash", Mock(return_value="mock-new-hash")
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "update_password_with_expiration",
        AsyncMock(),
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())

    result = await login.reset_password(
        request=request("/api/v1/reset-password"),
        data=ResetPasswordConfirmRequest(
            email=user.email,
            code="123456",
            new_password="MockNewPassword123!",
        ),
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    login.PasswordExpirationService.update_password_with_expiration.assert_awaited_once_with(
        user, "mock-new-hash"
    )
