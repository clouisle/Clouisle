from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.password_history import PasswordHistory
from app.models.site_setting import SiteSetting
from app.services import password_expiration
from app.services.password_expiration import PasswordExpirationService


class HistoryQuery:
    def __init__(self, entries):
        self.entries = entries
        self.ordering = None
        self.limit_value = None

    def order_by(self, ordering):
        self.ordering = ordering
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def __await__(self):
        async def result():
            return self.entries

        return result().__await__()


@pytest.mark.asyncio
async def test_calculate_expiration_enforces_enabled_policy_and_sso_exemption():
    changed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    local_user = SimpleNamespace(
        auth_source="local",
        password_expiration_exempt=False,
        is_superuser=False,
        password_changed_at=changed_at,
    )
    sso_user = SimpleNamespace(
        auth_source="sso",
        password_expiration_exempt=False,
        is_superuser=False,
        password_changed_at=changed_at,
    )

    with patch.object(
        SiteSetting, "get_value", new=AsyncMock(side_effect=[True, 30, True])
    ) as get_value:
        expires_at = await PasswordExpirationService.calculate_expiration_date(
            local_user
        )
        sso_expires_at = await PasswordExpirationService.calculate_expiration_date(
            sso_user
        )

    assert expires_at == changed_at + timedelta(days=30)
    assert sso_expires_at is None
    assert get_value.await_args_list[2].args == ("password_expiration_enabled", False)


@pytest.mark.asyncio
async def test_password_history_detects_reuse_and_skips_lookup_when_disabled():
    user = SimpleNamespace()
    query = HistoryQuery([SimpleNamespace(hashed_password="old-hash")])

    with (
        patch.object(SiteSetting, "get_value", new=AsyncMock(side_effect=[2, 0])),
        patch.object(PasswordHistory, "filter", return_value=query) as history_filter,
        patch.object(
            password_expiration.security, "verify_password", return_value=True
        ) as verify_password,
    ):
        assert await PasswordExpirationService.check_password_history(user, "OldPass1")
        assert not await PasswordExpirationService.check_password_history(
            user, "NewPass1"
        )

    history_filter.assert_called_once_with(user=user)
    assert query.ordering == "-created_at"
    assert query.limit_value == 2
    verify_password.assert_called_once_with("OldPass1", "old-hash")


@pytest.mark.asyncio
async def test_expired_password_and_minimum_age_are_enforced():
    user = SimpleNamespace(
        password_changed_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    with (
        patch.object(
            PasswordExpirationService,
            "calculate_expiration_date",
            new=AsyncMock(
                return_value=datetime.now(timezone.utc) - timedelta(seconds=1)
            ),
        ),
        patch.object(SiteSetting, "get_value", new=AsyncMock(return_value=3)),
    ):
        expired = await PasswordExpirationService.is_password_expired(user)
        (
            can_change,
            days_remaining,
        ) = await PasswordExpirationService.can_change_password(user)

    assert expired is True
    assert can_change is False
    assert days_remaining == 2


@pytest.mark.asyncio
async def test_password_update_records_history_and_clears_sensitive_state():
    user = SimpleNamespace(
        username="alice",
        hashed_password="old-hash",
        force_password_change=True,
        password_expiration_notified_at=datetime.now(timezone.utc),
        save=AsyncMock(),
    )
    expires_at = datetime(2026, 4, 1, tzinfo=timezone.utc)

    with (
        patch.object(
            PasswordExpirationService, "add_to_password_history", new=AsyncMock()
        ) as add_history,
        patch.object(
            PasswordExpirationService,
            "calculate_expiration_date",
            new=AsyncMock(return_value=expires_at),
        ) as calculate_expiration,
    ):
        await PasswordExpirationService.update_password_with_expiration(
            user, "new-hash"
        )

    add_history.assert_awaited_once_with(user, "old-hash")
    calculate_expiration.assert_awaited_once_with(user)
    user.save.assert_awaited_once()
    assert user.hashed_password == "new-hash"
    assert user.password_changed_at.tzinfo is timezone.utc
    assert user.password_expires_at == expires_at
    assert user.force_password_change is False
    assert user.password_expiration_notified_at is None
