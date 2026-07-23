from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from app.services import password_expiration


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(
        username="alice",
        auth_source="local",
        password_expiration_exempt=False,
        is_superuser=False,
        password_changed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        hashed_password="old-hash",
        force_password_change=True,
        password_expiration_notified_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        password_expires_at=None,
        save=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attributes", "expected"),
    [
        ({"auth_source": "oidc"}, True),
        ({"password_expiration_exempt": True}, True),
        ({"is_superuser": True}, True),
        ({}, False),
    ],
)
async def test_is_user_exempt(
    user: SimpleNamespace, attributes: dict[str, object], expected: bool
) -> None:
    for name, value in attributes.items():
        setattr(user, name, value)
    assert (
        await password_expiration.PasswordExpirationService.is_user_exempt(user)
        is expected
    )


@pytest.mark.asyncio
async def test_calculate_expiration_date_honors_policy_and_exemptions(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_value = AsyncMock(
        side_effect=lambda key, default: {
            "password_expiration_enabled": True,
            "password_expiration_days": 30,
        }.get(key, default)
    )
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)

    assert (
        await password_expiration.PasswordExpirationService.calculate_expiration_date(
            user
        )
        == datetime(2026, 1, 31, tzinfo=timezone.utc)
    )

    get_value.reset_mock()
    get_value.side_effect = lambda key, default: (
        False if key == "password_expiration_enabled" else default
    )
    assert (
        await password_expiration.PasswordExpirationService.calculate_expiration_date(
            user
        )
        is None
    )
    get_value.assert_awaited_once_with("password_expiration_enabled", False)

    get_value.side_effect = lambda key, default: (
        True if key == "password_expiration_enabled" else default
    )
    user.is_superuser = True
    assert (
        await password_expiration.PasswordExpirationService.calculate_expiration_date(
            user
        )
        is None
    )

    user.is_superuser = False
    user.password_changed_at = None
    assert (
        await password_expiration.PasswordExpirationService.calculate_expiration_date(
            user
        )
        is None
    )


@pytest.mark.asyncio
async def test_expiration_status_warning_and_boundaries(user: SimpleNamespace) -> None:
    now = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)
    service = password_expiration.PasswordExpirationService

    with patch("app.services.password_expiration.datetime") as clock:
        clock.now.return_value = now
        with patch.object(
            service, "calculate_expiration_date", AsyncMock(return_value=now)
        ):
            assert await service.is_password_expired(user) is False
        with patch.object(
            service,
            "calculate_expiration_date",
            AsyncMock(return_value=now - timedelta(microseconds=1)),
        ):
            assert await service.is_password_expired(user) is True
        with patch.object(
            service, "calculate_expiration_date", AsyncMock(return_value=None)
        ):
            assert await service.is_password_expired(user) is False
            assert await service.days_until_expiration(user) is None
        with patch.object(
            service,
            "calculate_expiration_date",
            AsyncMock(return_value=now + timedelta(days=3, hours=23)),
        ):
            assert await service.days_until_expiration(user) == 3

    with (
        patch.object(
            service, "days_until_expiration", AsyncMock(side_effect=[None, 0, 7, 8])
        ),
        patch.object(
            password_expiration.SiteSetting, "get_value", AsyncMock(return_value=7)
        ),
    ):
        assert await service.should_warn_user(user) is False
        assert await service.should_warn_user(user) is False
        assert await service.should_warn_user(user) is True
        assert await service.should_warn_user(user) is False


class _HistoryQuery:
    def __init__(self, entries: list[SimpleNamespace]) -> None:
        self.entries = entries
        self.limit_value: int | None = None

    def order_by(self, field: str) -> "_HistoryQuery":
        assert field == "-created_at"
        return self

    def limit(self, count: int) -> "_HistoryQuery":
        self.limit_value = count
        return self

    def __await__(self):
        async def result() -> list[SimpleNamespace]:
            return (
                self.entries
                if self.limit_value is None
                else self.entries[: self.limit_value]
            )

        return result().__await__()


@pytest.mark.asyncio
async def test_add_to_password_history_creates_and_archives_old_entries(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    entries = [SimpleNamespace(delete=AsyncMock()) for _ in range(4)]
    create = AsyncMock()
    filter_mock = Mock(return_value=_HistoryQuery(entries))
    monkeypatch.setattr(password_expiration.PasswordHistory, "create", create)
    monkeypatch.setattr(password_expiration.PasswordHistory, "filter", filter_mock)
    monkeypatch.setattr(
        password_expiration.SiteSetting, "get_value", AsyncMock(return_value=2)
    )

    await password_expiration.PasswordExpirationService.add_to_password_history(
        user, "old-hash"
    )

    create.assert_awaited_once_with(user=user, hashed_password="old-hash")
    filter_mock.assert_called_once_with(user=user)
    entries[0].delete.assert_not_awaited()
    entries[1].delete.assert_not_awaited()
    entries[2].delete.assert_awaited_once()
    entries[3].delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_password_history_handles_disabled_match_and_miss(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = password_expiration.PasswordExpirationService
    get_value = AsyncMock(return_value=0)
    filter_mock = Mock()
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(password_expiration.PasswordHistory, "filter", filter_mock)
    assert await service.check_password_history(user, "new") is False
    filter_mock.assert_not_called()

    entries = [
        SimpleNamespace(hashed_password="first"),
        SimpleNamespace(hashed_password="second"),
    ]
    get_value.return_value = 2
    filter_mock.return_value = _HistoryQuery(entries)
    verify = Mock(side_effect=[False, True])
    monkeypatch.setattr(password_expiration.security, "verify_password", verify)
    assert await service.check_password_history(user, "reused") is True
    assert verify.call_args_list == [call("reused", "first"), call("reused", "second")]

    verify.reset_mock(side_effect=True)
    verify.side_effect = [False, False]
    assert await service.check_password_history(user, "unused") is False


@pytest.mark.asyncio
async def test_can_change_password_rounds_partial_days_up(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = password_expiration.PasswordExpirationService
    get_value = AsyncMock(return_value=0)
    monkeypatch.setattr(password_expiration.SiteSetting, "get_value", get_value)
    assert await service.can_change_password(user) == (True, None)

    get_value.return_value = 2
    user.password_changed_at = None
    assert await service.can_change_password(user) == (True, None)

    now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    user.password_changed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch("app.services.password_expiration.datetime") as clock:
        clock.now.return_value = now
        assert await service.can_change_password(user) == (False, 1)
        user.password_changed_at = datetime(2025, 12, 31, tzinfo=timezone.utc)
        assert await service.can_change_password(user) == (True, None)


@pytest.mark.asyncio
async def test_update_password_transitions_metadata_and_saves(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = password_expiration.PasswordExpirationService
    add_history = AsyncMock()
    expires_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    calculate = AsyncMock(return_value=expires_at)
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "add_to_password_history", add_history)
    monkeypatch.setattr(service, "calculate_expiration_date", calculate)

    with patch("app.services.password_expiration.datetime") as clock:
        clock.now.return_value = now
        await service.update_password_with_expiration(user, "new-hash")

    add_history.assert_awaited_once_with(user, "old-hash")
    assert user.hashed_password == "new-hash"
    assert user.password_changed_at == now
    assert user.force_password_change is False
    assert user.password_expiration_notified_at is None
    assert user.password_expires_at == expires_at
    calculate.assert_awaited_once_with(user)
    user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_password_without_existing_hash_skips_history_and_propagates_save_error(
    user: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = password_expiration.PasswordExpirationService
    user.hashed_password = ""
    user.save.side_effect = RuntimeError("save failed")
    add_history = AsyncMock()
    monkeypatch.setattr(service, "add_to_password_history", add_history)
    monkeypatch.setattr(
        service, "calculate_expiration_date", AsyncMock(return_value=None)
    )

    with pytest.raises(RuntimeError, match="save failed"):
        await service.update_password_with_expiration(user, "new-hash")

    add_history.assert_not_awaited()
