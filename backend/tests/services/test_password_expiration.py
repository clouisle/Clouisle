from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import password_expiration


Service = password_expiration.PasswordExpirationService
NOW = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class Query:
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
        async def resolve():
            return self.entries[: self.limit_value]

        return resolve().__await__()


def user(**overrides):
    values = {
        "username": "alice",
        "auth_source": "local",
        "password_expiration_exempt": False,
        "is_superuser": False,
        "password_changed_at": NOW,
        "hashed_password": "old-hash",
        "force_password_change": True,
        "password_expiration_notified_at": NOW,
        "password_expires_at": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, False),
        ({"auth_source": "saml"}, True),
        ({"password_expiration_exempt": True}, True),
        ({"is_superuser": True}, True),
    ],
)
async def test_is_user_exempt_covers_each_exemption(overrides, expected):
    assert await Service.is_user_exempt(user(**overrides)) is expected


@pytest.mark.asyncio
async def test_calculate_expiration_date_covers_disabled_exempt_and_missing_date(
    monkeypatch,
):
    get_value = AsyncMock(return_value=False)
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)
    assert await Service.calculate_expiration_date(user()) is None

    get_value.return_value = True
    assert await Service.calculate_expiration_date(user(auth_source="oidc")) is None
    assert (
        await Service.calculate_expiration_date(user(password_changed_at=None)) is None
    )


@pytest.mark.asyncio
async def test_calculate_expiration_date_uses_configured_days(monkeypatch):
    async def get_value(key, default):
        return {"password_expiration_enabled": True, "password_expiration_days": 30}[
            key
        ]

    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)

    assert await Service.calculate_expiration_date(user()) == NOW + timedelta(days=30)


@pytest.mark.asyncio
async def test_expiry_days_and_warning_boundaries(monkeypatch):
    monkeypatch.setattr(password_expiration, "datetime", FixedDateTime)
    calculate = AsyncMock(return_value=None)
    monkeypatch.setattr(Service, "calculate_expiration_date", calculate)

    assert await Service.is_password_expired(user()) is False
    assert await Service.days_until_expiration(user()) is None
    assert await Service.should_warn_user(user()) is False

    calculate.return_value = NOW - timedelta(seconds=1)
    assert await Service.is_password_expired(user()) is True
    assert await Service.days_until_expiration(user()) == -1

    calculate.return_value = NOW + timedelta(days=5)
    monkeypatch.setattr(
        password_expiration.SiteSetting, "get_value", AsyncMock(return_value=5)
    )
    assert await Service.is_password_expired(user()) is False
    assert await Service.days_until_expiration(user()) == 5
    assert await Service.should_warn_user(user()) is True

    calculate.return_value = NOW
    assert await Service.should_warn_user(user()) is False


@pytest.mark.asyncio
async def test_add_to_password_history_creates_and_trims_old_entries(monkeypatch):
    entries = [SimpleNamespace(delete=AsyncMock()) for _ in range(4)]
    query = Query(entries)
    create = AsyncMock()
    monkeypatch.setattr(password_expiration.PasswordHistory, "create", create)
    monkeypatch.setattr(
        password_expiration.PasswordHistory,
        "filter",
        MagicMock(return_value=query),
    )
    monkeypatch.setattr(
        password_expiration.SiteSetting, "get_value", AsyncMock(return_value=2)
    )
    account = user()

    await Service.add_to_password_history(account, "stored-hash")

    create.assert_awaited_once_with(user=account, hashed_password="stored-hash")
    assert query.ordering == "-created_at"
    entries[0].delete.assert_not_awaited()
    entries[1].delete.assert_not_awaited()
    entries[2].delete.assert_awaited_once()
    entries[3].delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_password_history_handles_disabled_match_and_miss(monkeypatch):
    get_value = AsyncMock(return_value=0)
    history_filter = MagicMock()
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(password_expiration.PasswordHistory, "filter", history_filter)

    assert await Service.check_password_history(user(), "candidate") is False
    history_filter.assert_not_called()

    get_value.return_value = 2
    query = Query(
        [
            SimpleNamespace(hashed_password="first"),
            SimpleNamespace(hashed_password="matching"),
            SimpleNamespace(hashed_password="outside-limit"),
        ]
    )
    history_filter.return_value = query
    verify = MagicMock(side_effect=lambda _password, hashed: hashed == "matching")
    monkeypatch.setattr(password_expiration.security, "verify_password", verify)

    assert await Service.check_password_history(user(), "candidate") is True
    assert query.ordering == "-created_at"
    assert query.limit_value == 2
    assert [call.args for call in verify.call_args_list] == [
        ("candidate", "first"),
        ("candidate", "matching"),
    ]

    verify.return_value = False
    verify.side_effect = None
    assert await Service.check_password_history(user(), "different") is False


@pytest.mark.asyncio
async def test_can_change_password_covers_unrestricted_elapsed_and_waiting(monkeypatch):
    monkeypatch.setattr(password_expiration, "datetime", FixedDateTime)
    get_value = AsyncMock(return_value=0)
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)

    assert await Service.can_change_password(user()) == (True, None)

    get_value.return_value = 2
    assert await Service.can_change_password(user(password_changed_at=None)) == (
        True,
        None,
    )
    assert await Service.can_change_password(
        user(password_changed_at=NOW - timedelta(days=2))
    ) == (True, None)
    assert await Service.can_change_password(
        user(password_changed_at=NOW - timedelta(hours=12))
    ) == (False, 2)


@pytest.mark.asyncio
async def test_update_password_updates_metadata_saves_and_archives_old_hash(
    monkeypatch,
):
    monkeypatch.setattr(password_expiration, "datetime", FixedDateTime)
    add_history = AsyncMock()
    expiration = NOW + timedelta(days=90)
    monkeypatch.setattr(Service, "add_to_password_history", add_history)
    monkeypatch.setattr(
        Service, "calculate_expiration_date", AsyncMock(return_value=expiration)
    )
    account = user()

    await Service.update_password_with_expiration(account, "new-hash")

    add_history.assert_awaited_once_with(account, "old-hash")
    assert account.hashed_password == "new-hash"
    assert account.password_changed_at == NOW
    assert account.password_expires_at == expiration
    assert account.force_password_change is False
    assert account.password_expiration_notified_at is None
    account.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_password_without_old_hash_skips_history(monkeypatch):
    add_history = AsyncMock()
    monkeypatch.setattr(Service, "add_to_password_history", add_history)
    monkeypatch.setattr(
        Service, "calculate_expiration_date", AsyncMock(return_value=None)
    )
    account = user(hashed_password=None)

    await Service.update_password_with_expiration(account, "first-hash")

    add_history.assert_not_awaited()
    account.save.assert_awaited_once()
