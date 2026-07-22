from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import totp as admin_totp
from app.api.v1.endpoints import totp
from app.schemas.response import BusinessError, ResponseCode
from app.services.password_expiration import PasswordExpirationService


def _totp_user(**overrides):
    values = {
        "id": uuid4(),
        "username": "coverage-user",
        "totp_enabled": True,
        "totp_enabled_at": None,
        "totp_secret": "encrypted-placeholder",
        "hashed_password": "hashed-placeholder",
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_disable_totp_rejects_invalid_backup_code_without_persisting(monkeypatch):
    user = _totp_user()
    monkeypatch.setattr(totp, "verify_password", lambda *_: True)
    monkeypatch.setattr(totp.totp_service, "decrypt_secret", lambda _: "secret")
    monkeypatch.setattr(totp.totp_service, "verify_backup_code", lambda *_: (False, 3))

    with pytest.raises(BusinessError) as exc_info:
        await totp.disable_totp(
            MagicMock(),
            totp.TOTPDisableRequest(
                password="redacted", code="redacted", is_backup_code=True
            ),
            user,
        )

    assert exc_info.value.code == ResponseCode.TOTP_INVALID
    user.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "valid_code", "expected_code"),
    [
        (_totp_user(totp_enabled=False), True, ResponseCode.TOTP_NOT_ENABLED),
        (_totp_user(totp_secret=None), True, ResponseCode.TOTP_NOT_ENABLED),
        (_totp_user(), False, ResponseCode.TOTP_INVALID),
    ],
    ids=["disabled", "missing-secret", "invalid-code"],
)
async def test_regenerate_backup_codes_rejects_invalid_state(
    monkeypatch, user, valid_code, expected_code
):
    monkeypatch.setattr(totp.totp_service, "decrypt_secret", lambda _: "secret")
    monkeypatch.setattr(totp.totp_service, "verify_totp_code", lambda *_: valid_code)

    with pytest.raises(BusinessError) as exc_info:
        await totp.regenerate_backup_codes(
            MagicMock(), totp.TOTPRegenerateRequest(code="redacted"), user
        )

    assert exc_info.value.code == expected_code
    user.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_totp_status_reports_remaining_codes_without_timestamp(monkeypatch):
    user = _totp_user(totp_enabled_at=None)
    monkeypatch.setattr(
        totp.totp_service, "get_remaining_backup_codes", AsyncMock(return_value=4)
    )

    response = await totp.get_totp_status(user)

    assert response["data"] == totp.TOTPStatusResponse(
        enabled=True, enabled_at=None, remaining_backup_codes=4
    )


@pytest.mark.asyncio
async def test_admin_disable_totp_rejects_unknown_user(monkeypatch):
    monkeypatch.setattr(admin_totp.User, "get_or_none", AsyncMock(return_value=None))

    with pytest.raises(BusinessError) as exc_info:
        await admin_totp.admin_disable_user_totp(MagicMock(), uuid4(), _totp_user())

    assert exc_info.value.code == ResponseCode.USER_NOT_FOUND


@pytest.mark.asyncio
async def test_password_history_within_limit_skips_deletion(monkeypatch):
    entries = [SimpleNamespace(delete=AsyncMock()) for _ in range(2)]
    query = SimpleNamespace(order_by=AsyncMock(return_value=entries))
    monkeypatch.setattr(
        "app.services.password_expiration.PasswordHistory.create", AsyncMock()
    )
    monkeypatch.setattr(
        "app.services.password_expiration.PasswordHistory.filter",
        MagicMock(return_value=query),
    )
    monkeypatch.setattr(
        "app.services.password_expiration.SiteSetting.get_value",
        AsyncMock(return_value=2),
    )

    await PasswordExpirationService.add_to_password_history(
        SimpleNamespace(username="coverage-user"), "hashed-placeholder"
    )

    assert all(entry.delete.await_count == 0 for entry in entries)
