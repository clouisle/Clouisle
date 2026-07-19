from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks.password_expiration import (
    _check_password_expiration,
    _get_event_loop,
    check_password_expiration_task,
)

NOW = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)


def make_user(days_remaining: int, **overrides):
    values = {
        "id": uuid4(),
        "username": f"user-{days_remaining}",
        "password_expires_at": NOW + timedelta(days=days_remaining),
        "password_expiration_notified_at": None,
        "force_password_change": False,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def run_check(users, *, enabled=True, warning_days=7):
    query = MagicMock()
    query.all = AsyncMock(return_value=users)
    with (
        patch(
            "app.tasks.password_expiration.SiteSetting.get_value",
            new=AsyncMock(side_effect=[enabled, warning_days]),
        ) as get_value,
        patch(
            "app.tasks.password_expiration.User.filter", return_value=query
        ) as filter_users,
        patch("app.tasks.password_expiration.datetime") as mocked_datetime,
        patch(
            "app.tasks.password_expiration.AutoNotificationService.send_to_user",
            new=AsyncMock(),
        ) as send,
        patch(
            "app.tasks.password_expiration.t", side_effect=lambda key, **_: key
        ) as translate,
    ):
        mocked_datetime.now.return_value = NOW
        await _check_password_expiration()
    return get_value, filter_users, send, translate


@pytest.mark.asyncio
async def test_disabled_policy_skips_query_and_notifications():
    get_value, filter_users, send, _ = await run_check([], enabled=False)

    get_value.assert_awaited_once_with("password_expiration_enabled", False)
    filter_users.assert_not_called()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_password_forces_change_and_sends_daily_localized_notice():
    user = make_user(-1, locale="zh")

    _, filter_users, send, translate = await run_check([user])

    filter_users.assert_called_once_with(
        auth_source="local",
        is_superuser=False,
        password_expiration_exempt=False,
        password_changed_at__isnull=False,
        password_expires_at__isnull=False,
    )
    assert user.force_password_change is True
    assert user.password_expiration_notified_at == NOW
    assert user.save.await_count == 2
    assert translate.call_args_list == [
        call("notify_password_expired_title", lang="zh"),
        call("notify_password_expired_content", lang="zh"),
    ]
    send.assert_awaited_once_with(
        notification_type=AutoNotificationType.PASSWORD_EXPIRED,
        user_id=user.id,
        title="notify_password_expired_title",
        content="notify_password_expired_content",
        level=NotificationLevel.HIGH,
        data={
            "user_id": str(user.id),
            "username": user.username,
            "expired_at": user.password_expires_at.isoformat(),
        },
    )


@pytest.mark.asyncio
async def test_expired_password_skips_repeat_notice_but_still_forces_change():
    user = make_user(
        -1,
        password_expiration_notified_at=NOW - timedelta(hours=23),
    )

    _, _, send, _ = await run_check([user])

    assert user.force_password_change is True
    user.save.assert_awaited_once()
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("days_remaining", [7, 3, 1])
async def test_warning_thresholds_send_notice_in_user_locale(days_remaining):
    user = make_user(days_remaining, locale="zh")

    _, _, send, translate = await run_check([user])

    assert user.password_expiration_notified_at == NOW
    user.save.assert_awaited_once()
    assert translate.call_args_list == [
        call("notify_password_expiring_title", lang="zh"),
        call(
            "notify_password_expiring_content",
            lang="zh",
            days=days_remaining,
        ),
    ]
    send.assert_awaited_once_with(
        notification_type=AutoNotificationType.PASSWORD_EXPIRING,
        user_id=user.id,
        title="notify_password_expiring_title",
        content="notify_password_expiring_content",
        level=NotificationLevel.MEDIUM,
        data={
            "user_id": str(user.id),
            "username": user.username,
            "expires_at": user.password_expires_at.isoformat(),
            "days_remaining": days_remaining,
        },
    )


@pytest.mark.asyncio
async def test_non_threshold_recent_and_missing_expirations_are_skipped():
    users = [
        make_user(5),
        make_user(3, password_expiration_notified_at=NOW - timedelta(hours=23)),
        make_user(0),
        make_user(1, password_expires_at=None),
    ]

    _, _, send, translate = await run_check(users)

    send.assert_not_awaited()
    translate.assert_not_called()
    for user in users:
        user.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_locale_defaults_to_english():
    user = make_user(1)

    _, _, _, translate = await run_check([user])

    assert translate.call_args_list == [
        call("notify_password_expiring_title", lang="en"),
        call("notify_password_expiring_content", lang="en", days=1),
    ]


@pytest.mark.asyncio
async def test_notification_failure_propagates_without_marking_notice_sent():
    user = make_user(1)
    query = MagicMock()
    query.all = AsyncMock(return_value=[user])
    with (
        patch(
            "app.tasks.password_expiration.SiteSetting.get_value",
            new=AsyncMock(side_effect=[True, 7]),
        ),
        patch("app.tasks.password_expiration.User.filter", return_value=query),
        patch("app.tasks.password_expiration.datetime") as mocked_datetime,
        patch("app.tasks.password_expiration.t", return_value="translated"),
        patch(
            "app.tasks.password_expiration.AutoNotificationService.send_to_user",
            new=AsyncMock(side_effect=RuntimeError("delivery failed")),
        ),
    ):
        mocked_datetime.now.return_value = NOW
        with pytest.raises(RuntimeError, match="delivery failed"):
            await _check_password_expiration()

    assert user.password_expiration_notified_at is None
    user.save.assert_not_awaited()


def test_get_event_loop_reuses_open_loop():
    loop = MagicMock()
    loop.is_closed.return_value = False
    with patch("asyncio.get_event_loop", return_value=loop):
        assert _get_event_loop() is loop


def test_get_event_loop_replaces_closed_loop():
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    new_loop = MagicMock()
    with (
        patch("asyncio.get_event_loop", return_value=closed_loop),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_recovers_when_no_loop_exists():
    new_loop = MagicMock()
    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_task_runs_async_check_on_event_loop():
    loop = MagicMock()
    loop.run_until_complete.side_effect = lambda coroutine: coroutine.close()
    with (
        patch("app.tasks.password_expiration._get_event_loop", return_value=loop),
        patch(
            "app.tasks.password_expiration._check_password_expiration"
        ) as async_check,
    ):
        check_password_expiration_task.run()

    async_check.assert_called_once_with()
    loop.run_until_complete.assert_called_once()


def test_task_reraises_event_loop_failure():
    loop = MagicMock()

    def fail(coroutine):
        coroutine.close()
        raise RuntimeError("check failed")

    loop.run_until_complete.side_effect = fail
    with (
        patch("app.tasks.password_expiration._get_event_loop", return_value=loop),
        patch("app.tasks.password_expiration._check_password_expiration"),
        pytest.raises(RuntimeError, match="check failed"),
    ):
        check_password_expiration_task.run()
