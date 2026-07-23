from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import login
from app.models import user as user_models
from app.schemas.user import UserCreate
from app.services import team_role_sync


class Query:
    def __init__(self, value=None, count=0):
        self.value = value
        self.count_value = count

    async def first(self):
        return self.value

    async def count(self):
        return self.count_value

    def prefetch_related(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


def request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/login",
            "headers": [(b"user-agent", b"test-agent")],
            "client": ("127.0.0.1", 1234),
        }
    )


def patch_login_success_boundaries(monkeypatch, user):
    async def setting(key, default=None):
        return {"email_verification": False, "session_timeout_days": 7}.get(
            key, default
        )

    monkeypatch.setattr(login.SiteSetting, "get_value", setting)
    monkeypatch.setattr(login.User, "filter", lambda **_kwargs: Query(user))
    monkeypatch.setattr(login.security, "verify_password", lambda *_args: True)
    monkeypatch.setattr(
        login.security, "create_access_token", lambda *_args, **_kwargs: "fake-token"
    )
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(False, {}))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(
        login.AuditLogService, "get_client_ip", lambda _request: "127.0.0.1"
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
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


@pytest.mark.asyncio
async def test_expired_password_sets_force_change_during_password_login(monkeypatch):
    user = SimpleNamespace(
        id="user-id",
        username="test-user",
        email="test@example.invalid",
        hashed_password="fake-hash",
        is_active=True,
        is_superuser=False,
        email_verified=True,
        totp_enabled=False,
        force_password_change=False,
        locale="en",
        save=AsyncMock(),
    )
    patch_login_success_boundaries(monkeypatch, user)

    response = await login.login_access_token(request(), "test-user", "fake-password")

    assert user.force_password_change is True
    assert user.save.await_count == 2
    assert response["data"]["force_password_change"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [True, False])
async def test_totp_login_covers_expired_password_and_warning_branch(
    monkeypatch, expired
):
    user = SimpleNamespace(
        id="user-id",
        username="test-user",
        email="test@example.invalid",
        totp_enabled=True,
        totp_secret="fake-secret",
        force_password_change=False,
        locale="en",
        save=AsyncMock(),
    )
    patch_login_success_boundaries(monkeypatch, user)
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=expired),
    )
    monkeypatch.setattr(login.jwt, "decode", lambda *_args, **_kwargs: {"sub": user.id})
    monkeypatch.setattr(login.User, "get_or_none", AsyncMock(return_value=user))
    monkeypatch.setattr(
        login.totp_security, "check_totp_rate_limit", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.totp_security, "reset_totp_attempts", AsyncMock())
    monkeypatch.setattr(
        login.totp_service, "decrypt_secret", lambda _secret: "plain-secret"
    )
    monkeypatch.setattr(login.totp_service, "verify_totp_code", lambda *_args: True)
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

    response = await login.verify_totp(
        request(), "fake-temp-token", "123456", is_backup_code=False
    )

    assert user.force_password_change is expired
    assert user.save.await_count == 2 if expired else 1
    assert (
        response["data"]["force_password_change"] is True
        if expired
        else response["msg"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_count", "require_approval", "email_verification", "message_key"),
    [
        (0, False, False, "registration_successful_superadmin"),
        (1, True, False, "registration_pending_approval"),
        (1, False, True, "registration_pending_verification"),
        (1, False, False, "registration_successful"),
    ],
)
async def test_registration_response_arcs(
    monkeypatch, user_count, require_approval, email_verification, message_key
):
    roles = SimpleNamespace(add=AsyncMock())
    user = SimpleNamespace(
        id="new-user-id",
        username="new-user",
        email="new-user@example.com",
        roles=roles,
        save=AsyncMock(),
    )

    class FakeUser:
        @staticmethod
        def all():
            return Query(count=user_count)

        @staticmethod
        def filter(**_kwargs):
            return Query()

        @staticmethod
        async def create(**_kwargs):
            return user

        @staticmethod
        def get(**_kwargs):
            return Query(user)

    async def setting(key, default=None):
        return {
            "require_approval": require_approval,
            "email_verification": email_verification,
            "force_password_change_first_login": False,
        }.get(key, default)

    monkeypatch.setattr(login, "User", FakeUser)
    monkeypatch.setattr(login.SiteSetting, "get_value", setting)
    monkeypatch.setattr(login, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(
        login.security, "get_password_hash", lambda _password: "fake-hash"
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "calculate_expiration_date",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        login, "serialize_user_with_sso", AsyncMock(return_value={"id": user.id})
    )
    monkeypatch.setattr(user_models.Role, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(team_role_sync, "assign_default_role", AsyncMock())
    monkeypatch.setattr(
        team_role_sync, "assign_default_team", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(login, "get_default_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(
        login,
        "success",
        lambda *, data=None, msg_key=None: {"data": data, "msg_key": msg_key},
    )
    notify = AsyncMock()
    monkeypatch.setattr(login.AutoNotificationService, "send_global", notify)

    response = await login.register(
        request=request(),
        user_in=UserCreate(
            username="new-user",
            email="new-user@example.com",
            password="FakePassword123!",
        ),
    )

    assert response["msg_key"] == message_key
    if require_approval:
        notify.assert_awaited_once()
    if user_count == 0:
        roles.add.assert_not_awaited()
