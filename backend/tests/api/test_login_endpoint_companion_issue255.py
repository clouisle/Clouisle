from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.api.v1.endpoints import login as endpoint
from app.schemas.response import BusinessError, ResponseCode


class QueryStub:
    def __init__(self, first=None):
        self.first_value = first

    async def first(self):
        return self.first_value


class SettingsStub:
    def __init__(self, values=None):
        self.values = values or {}

    async def get_value(self, key, default=None):
        return self.values.get(key, default)


def user(**overrides):
    values = {
        "id": uuid4(),
        "username": "alice",
        "email": "alice@example.com",
        "hashed_password": "hashed",
        "is_active": True,
        "approval_status": "approved",
        "is_superuser": False,
        "email_verified": True,
        "totp_enabled": False,
        "totp_secret": "encrypted",
        "force_password_change": False,
        "locale": "en",
        "last_login": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def request():
    return SimpleNamespace(headers={"user-agent": "pytest"})


@pytest.mark.asyncio
async def test_login_rejects_sso_user_without_password_before_hash_check():
    current_user = user(hashed_password="")

    with (
        patch.object(endpoint.SiteSetting, "get_value", SettingsStub().get_value),
        patch.object(
            endpoint.User, "filter", Mock(return_value=QueryStub(current_user))
        ),
        patch.object(
            endpoint, "check_account_locked", AsyncMock(return_value=(False, 0))
        ),
        patch.object(endpoint.security, "verify_password", Mock()) as verify_password,
        patch.object(endpoint.AuditLogService, "log", AsyncMock()) as audit,
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.login_access_token(request(), "alice", "secret")

    assert exc_info.value.code == ResponseCode.INVALID_CREDENTIALS
    assert exc_info.value.msg_key == "incorrect_email_or_password"
    verify_password.assert_not_called()
    assert audit.await_args.kwargs["error_message"] == "sso_user_no_password"


@pytest.mark.asyncio
async def test_login_inactive_pending_user_uses_pending_approval_error():
    current_user = user(is_active=False, approval_status="pending")

    with (
        patch.object(endpoint.SiteSetting, "get_value", SettingsStub().get_value),
        patch.object(
            endpoint.User, "filter", Mock(return_value=QueryStub(current_user))
        ),
        patch.object(
            endpoint, "check_account_locked", AsyncMock(return_value=(False, 0))
        ),
        patch.object(endpoint.security, "verify_password", Mock(return_value=True)),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.login_access_token(request(), "alice", "secret")

    assert exc_info.value.code == ResponseCode.INACTIVE_USER
    assert exc_info.value.msg_key == "pending_approval_user"


@pytest.mark.asyncio
async def test_verify_totp_rejects_enabled_user_missing_secret():
    current_user = user(totp_enabled=True, totp_secret=None)

    with (
        patch.object(
            endpoint.jwt, "decode", Mock(return_value={"sub": str(current_user.id)})
        ),
        patch.object(
            endpoint.User, "get_or_none", AsyncMock(return_value=current_user)
        ),
        patch.object(
            endpoint.totp_security,
            "check_totp_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.verify_totp(
                request(), "temp", "123456", is_backup_code=False
            )

    assert exc_info.value.code == ResponseCode.TOTP_NOT_ENABLED
    assert exc_info.value.msg_key == "totp_not_enabled"


@pytest.mark.asyncio
async def test_verify_totp_backup_code_success_returns_expired_password_flag():
    current_user = user(totp_enabled=True)

    with (
        patch.object(
            endpoint.jwt, "decode", Mock(return_value={"sub": str(current_user.id)})
        ),
        patch.object(
            endpoint.User, "get_or_none", AsyncMock(return_value=current_user)
        ),
        patch.object(
            endpoint.totp_security,
            "check_totp_rate_limit",
            AsyncMock(return_value=(False, 0)),
        ),
        patch.object(
            endpoint.totp_service, "verify_backup_code", Mock(return_value=(True, 2))
        ),
        patch.object(endpoint.totp_security, "reset_totp_attempts", AsyncMock()),
        patch.object(endpoint, "reset_login_attempts", AsyncMock()),
        patch.object(
            endpoint.PasswordExpirationService,
            "is_user_exempt",
            AsyncMock(return_value=False),
        ),
        patch.object(
            endpoint.PasswordExpirationService,
            "is_password_expired",
            AsyncMock(return_value=True),
        ),
        patch.object(
            endpoint.PasswordExpirationService,
            "should_warn_user",
            AsyncMock(return_value=False),
        ),
        patch.object(
            endpoint.PasswordExpirationService,
            "days_until_expiration",
            AsyncMock(return_value=None),
        ),
        patch.object(
            endpoint.AuditLogService, "get_client_ip", Mock(return_value="127.0.0.1")
        ),
        patch.object(endpoint.AuditLogService, "log", AsyncMock()) as audit,
        patch.object(
            endpoint, "check_login_anomaly", AsyncMock(return_value=(False, {}))
        ),
        patch.object(endpoint, "record_login", AsyncMock()),
        patch.object(endpoint.SiteSetting, "get_value", SettingsStub().get_value),
        patch.object(
            endpoint.security, "create_access_token", Mock(return_value="access")
        ),
    ):
        result = await endpoint.verify_totp(
            request(), "temp", "backup-code", is_backup_code=True
        )

    assert result["data"] == {
        "access_token": "access",
        "token_type": "bearer",
        "force_password_change": True,
        "reason": "expired",
    }
    assert current_user.force_password_change is True
    assert current_user.save.await_count >= 2
    assert audit.await_args_list[0].kwargs["action"] == "use_backup_code"
