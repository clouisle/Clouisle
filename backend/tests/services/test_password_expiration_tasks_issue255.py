from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks import password_expiration as tasks


NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def user(**overrides):
    values = {
        "id": uuid4(),
        "username": "alice",
        "locale": "en",
        "password_expires_at": NOW + timedelta(days=30),
        "password_expiration_notified_at": None,
        "force_password_change": False,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def user_query(users):
    query = MagicMock()
    query.all = AsyncMock(return_value=users)
    return query


@pytest.mark.asyncio
async def test_disabled_policy_skips_users_and_notifications():
    with (
        patch.object(tasks.SiteSetting, "get_value", new=AsyncMock(return_value=False)),
        patch.object(tasks.User, "filter") as filter_users,
        patch.object(
            tasks.AutoNotificationService, "send_to_user", new=AsyncMock()
        ) as send,
    ):
        await tasks._check_password_expiration()

    filter_users.assert_not_called()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_processes_expired_and_warning_users_without_duplicate_notifications():
    expired = user(
        username="expired",
        locale="zh",
        password_expires_at=NOW - timedelta(days=1),
    )
    already_notified = user(
        username="already-notified",
        password_expires_at=NOW - timedelta(days=2),
        password_expiration_notified_at=NOW,
        force_password_change=True,
    )
    warning = user(username="warning", password_expires_at=NOW + timedelta(days=7))
    ignored_warning = user(password_expires_at=NOW + timedelta(days=5))
    recent_warning = user(
        password_expires_at=NOW + timedelta(days=3),
        password_expiration_notified_at=NOW,
    )
    missing_expiration = user(password_expires_at=None)
    users = [
        expired,
        already_notified,
        warning,
        ignored_warning,
        recent_warning,
        missing_expiration,
    ]
    settings = AsyncMock(side_effect=[True, 7])
    send = AsyncMock()

    with (
        patch.object(tasks, "datetime", FixedDateTime),
        patch.object(tasks.SiteSetting, "get_value", new=settings),
        patch.object(
            tasks.User, "filter", return_value=user_query(users)
        ) as filter_users,
        patch.object(tasks.AutoNotificationService, "send_to_user", new=send),
        patch.object(tasks, "t", side_effect=lambda key, **kwargs: key) as translate,
    ):
        await tasks._check_password_expiration()

    filter_users.assert_called_once_with(
        auth_source="local",
        is_superuser=False,
        password_expiration_exempt=False,
        password_changed_at__isnull=False,
        password_expires_at__isnull=False,
    )
    assert expired.force_password_change is True
    assert expired.password_expiration_notified_at == NOW
    assert expired.save.await_count == 2
    assert warning.password_expiration_notified_at == NOW
    warning.save.assert_awaited_once()
    already_notified.save.assert_not_awaited()
    ignored_warning.save.assert_not_awaited()
    recent_warning.save.assert_not_awaited()
    missing_expiration.save.assert_not_awaited()
    assert send.await_args_list == [
        call(
            notification_type=AutoNotificationType.PASSWORD_EXPIRED,
            user_id=expired.id,
            title="notify_password_expired_title",
            content="notify_password_expired_content",
            level=NotificationLevel.HIGH,
            data={
                "user_id": str(expired.id),
                "username": "expired",
                "expired_at": expired.password_expires_at.isoformat(),
            },
        ),
        call(
            notification_type=AutoNotificationType.PASSWORD_EXPIRING,
            user_id=warning.id,
            title="notify_password_expiring_title",
            content="notify_password_expiring_content",
            level=NotificationLevel.MEDIUM,
            data={
                "user_id": str(warning.id),
                "username": "warning",
                "expires_at": warning.password_expires_at.isoformat(),
                "days_remaining": 7,
            },
        ),
    ]
    assert translate.call_args_list[-1] == call(
        "notify_password_expiring_content", lang="en", days=7
    )


def test_event_loop_reuses_open_loop_and_replaces_closed_or_missing_loop():
    open_loop = MagicMock(is_closed=MagicMock(return_value=False))
    closed_loop = MagicMock(is_closed=MagicMock(return_value=True))
    replacement = MagicMock()

    with patch("asyncio.get_event_loop", return_value=open_loop):
        assert tasks._get_event_loop() is open_loop

    with (
        patch("asyncio.get_event_loop", return_value=closed_loop),
        patch("asyncio.new_event_loop", return_value=replacement),
        patch("asyncio.set_event_loop") as set_loop,
    ):
        assert tasks._get_event_loop() is replacement
        set_loop.assert_called_once_with(replacement)

    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=replacement),
        patch("asyncio.set_event_loop") as set_loop,
    ):
        assert tasks._get_event_loop() is replacement
        set_loop.assert_called_once_with(replacement)


def test_celery_entrypoint_runs_check_and_reraises_failure():
    loop = MagicMock()
    failure = RuntimeError("database unavailable")

    with (
        patch.object(tasks, "_get_event_loop", return_value=loop),
        patch.object(
            tasks, "_check_password_expiration", new=MagicMock(return_value="check")
        ),
    ):
        tasks.check_password_expiration_task.run()
    loop.run_until_complete.assert_called_once_with("check")

    loop.run_until_complete.side_effect = failure
    with (
        patch.object(tasks, "_get_event_loop", return_value=loop),
        patch.object(
            tasks, "_check_password_expiration", new=MagicMock(return_value="check")
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        tasks.check_password_expiration_task.run()
