import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks import password_expiration as task


class Query:
    def __init__(self, users):
        self.all = AsyncMock(return_value=users)


def user(now, days, **overrides):
    values = {
        "id": uuid4(),
        "username": "alice",
        "locale": "zh",
        "password_expires_at": None if days is None else now + timedelta(days=days),
        "force_password_change": False,
        "password_expiration_notified_at": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_event_loop_reuses_open_and_replaces_unavailable_loops(monkeypatch):
    open_loop = MagicMock(is_closed=MagicMock(return_value=False))
    monkeypatch.setattr(asyncio, "get_event_loop", MagicMock(return_value=open_loop))
    assert task._get_event_loop() is open_loop

    closed_loop = MagicMock(is_closed=MagicMock(return_value=True))
    replacement = MagicMock()
    monkeypatch.setattr(asyncio, "get_event_loop", MagicMock(return_value=closed_loop))
    monkeypatch.setattr(asyncio, "new_event_loop", MagicMock(return_value=replacement))
    monkeypatch.setattr(asyncio, "set_event_loop", MagicMock())
    assert task._get_event_loop() is replacement
    asyncio.set_event_loop.assert_called_once_with(replacement)

    asyncio.get_event_loop.side_effect = RuntimeError("no current loop")
    assert task._get_event_loop() is replacement
    assert asyncio.set_event_loop.call_count == 2


def test_celery_wrapper_runs_check_and_propagates_failure(monkeypatch):
    loop = MagicMock()
    check_result = object()
    monkeypatch.setattr(task, "_get_event_loop", MagicMock(return_value=loop))
    monkeypatch.setattr(
        task, "_check_password_expiration", MagicMock(return_value=check_result)
    )

    task.check_password_expiration_task.run()
    loop.run_until_complete.assert_called_once_with(check_result)

    loop.run_until_complete.side_effect = RuntimeError("check failed")
    with pytest.raises(RuntimeError, match="check failed"):
        task.check_password_expiration_task.run()


@pytest.mark.anyio
async def test_disabled_policy_skips_user_query(monkeypatch):
    monkeypatch.setattr(task.SiteSetting, "get_value", AsyncMock(return_value=False))
    user_filter = MagicMock()
    monkeypatch.setattr(task.User, "filter", user_filter)

    await task._check_password_expiration()

    user_filter.assert_not_called()


@pytest.mark.anyio
async def test_check_handles_expired_warning_and_throttled_users(monkeypatch):
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    missing_expiry = user(now, None)
    expired = user(now, -1)
    expired_recent = user(
        now,
        -2,
        username="recent-expired",
        force_password_change=True,
        password_expiration_notified_at=now,
    )
    expired_old = user(
        now,
        -3,
        username="old-expired",
        force_password_change=True,
        password_expiration_notified_at=now - timedelta(days=1),
    )
    warning = user(now, 7, username="warning")
    warning_old = user(
        now,
        3,
        username="old-warning",
        password_expiration_notified_at=now - timedelta(days=1),
    )
    warning_recent = user(
        now,
        1,
        password_expiration_notified_at=now - timedelta(hours=1),
    )
    non_interval = user(now, 2)
    expires_today = user(now, 0)
    users = [
        missing_expiry,
        expired,
        expired_recent,
        expired_old,
        warning,
        warning_old,
        warning_recent,
        non_interval,
        expires_today,
    ]
    query = Query(users)
    get_value = AsyncMock(side_effect=[True, 7])
    send = AsyncMock()
    monkeypatch.setattr(task, "datetime", FixedDateTime)
    monkeypatch.setattr(task.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(task.User, "filter", MagicMock(return_value=query))
    monkeypatch.setattr(task.AutoNotificationService, "send_to_user", send)
    monkeypatch.setattr(
        task, "t", lambda key, **kwargs: f"{key}:{kwargs.get('lang', 'en')}"
    )

    await task._check_password_expiration()

    task.User.filter.assert_called_once_with(
        auth_source="local",
        is_superuser=False,
        password_expiration_exempt=False,
        password_changed_at__isnull=False,
        password_expires_at__isnull=False,
    )
    assert expired.force_password_change is True
    assert expired.save.await_count == 2
    expired_recent.save.assert_not_awaited()
    expired_old.save.assert_awaited_once()
    warning.save.assert_awaited_once()
    warning_old.save.assert_awaited_once()
    warning_recent.save.assert_not_awaited()
    non_interval.save.assert_not_awaited()
    expires_today.save.assert_not_awaited()
    assert send.await_count == 4

    expired_call, old_expired_call, warning_call, old_warning_call = (
        send.await_args_list
    )
    assert (
        expired_call.kwargs["notification_type"]
        == AutoNotificationType.PASSWORD_EXPIRED
    )
    assert expired_call.kwargs["level"] == NotificationLevel.HIGH
    assert expired_call.kwargs["title"] == "notify_password_expired_title:zh"
    assert expired_call.kwargs["data"]["username"] == "alice"
    assert old_expired_call.kwargs["data"]["username"] == "old-expired"
    assert (
        warning_call.kwargs["notification_type"]
        == AutoNotificationType.PASSWORD_EXPIRING
    )
    assert warning_call.kwargs["level"] == NotificationLevel.MEDIUM
    assert warning_call.kwargs["data"]["days_remaining"] == 7
    assert old_warning_call.kwargs["data"]["days_remaining"] == 3
