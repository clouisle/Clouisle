from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks import api_key as api_key_task


def _query_returning(items):
    query = MagicMock()
    query.prefetch_related = AsyncMock(return_value=items)
    return query


def test_get_event_loop_replaces_closed_loop():
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", return_value=closed_loop),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert api_key_task._get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_recovers_when_no_loop_is_set():
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError("no loop")),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert api_key_task._get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


@pytest.mark.asyncio
async def test_check_api_key_expiration_sends_only_scheduled_notifications():
    now = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    zh_user = SimpleNamespace(id="user-zh", locale="zh")
    default_locale_user = SimpleNamespace(id="user-en")
    expiring_keys = [
        SimpleNamespace(
            id="key-7",
            name="Seven days",
            key_prefix="cl_7",
            expires_at=now + timedelta(days=7),
            user=zh_user,
        ),
        SimpleNamespace(
            id="key-3",
            name="Three days",
            key_prefix="cl_3",
            expires_at=now + timedelta(days=3),
            user=zh_user,
        ),
        SimpleNamespace(
            id="key-under-one-day",
            name="Soon",
            key_prefix="cl_1",
            expires_at=now + timedelta(hours=12),
            user=default_locale_user,
        ),
        SimpleNamespace(
            id="key-2",
            name="Skipped",
            key_prefix="cl_2",
            expires_at=now + timedelta(days=2),
            user=zh_user,
        ),
    ]
    expired_key = SimpleNamespace(
        id="key-expired",
        name="Expired",
        key_prefix="cl_old",
        expires_at=now - timedelta(hours=1),
        user=default_locale_user,
    )
    expiring_query = _query_returning(expiring_keys)
    expired_query = _query_returning([expired_key])

    with (
        patch.object(api_key_task, "now_utc", return_value=now),
        patch.object(
            api_key_task.APIKey,
            "filter",
            side_effect=[expiring_query, expired_query],
        ) as filter_mock,
        patch.object(
            api_key_task,
            "t",
            side_effect=lambda key, **kwargs: f"{key}:{kwargs['lang']}",
        ),
        patch.object(
            api_key_task.AutoNotificationService,
            "send_to_user",
            new=AsyncMock(),
        ) as send,
    ):
        await api_key_task._check_api_key_expiration()

    assert filter_mock.call_args_list == [
        call(
            is_active=True,
            expires_at__isnull=False,
            expires_at__gt=now,
            expires_at__lte=now + timedelta(days=7),
        ),
        call(
            is_active=True,
            expires_at__isnull=False,
            expires_at__gt=now - timedelta(hours=24),
            expires_at__lte=now,
        ),
    ]
    expiring_query.prefetch_related.assert_awaited_once_with("user")
    expired_query.prefetch_related.assert_awaited_once_with("user")
    assert send.await_count == 4

    seven_day_call, three_day_call, one_day_call, expired_call = send.await_args_list
    assert seven_day_call.kwargs == {
        "notification_type": AutoNotificationType.APIKEY_EXPIRING,
        "user_id": "user-zh",
        "title": "notify_apikey_expiring_title:zh",
        "content": "notify_apikey_expiring_content:zh",
        "level": NotificationLevel.HIGH,
        "data": {
            "api_key_id": "key-7",
            "key_name": "Seven days",
            "key_prefix": "cl_7",
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "days_remaining": 7,
        },
    }
    assert three_day_call.kwargs["data"]["days_remaining"] == 3
    assert one_day_call.kwargs["title"] == "notify_apikey_expiring_title:en"
    assert one_day_call.kwargs["data"]["days_remaining"] == 1
    assert expired_call.kwargs == {
        "notification_type": AutoNotificationType.APIKEY_EXPIRED,
        "user_id": "user-en",
        "title": "notify_apikey_expired_title:en",
        "content": "notify_apikey_expired_content:en",
        "level": NotificationLevel.HIGH,
        "data": {
            "api_key_id": "key-expired",
            "key_name": "Expired",
            "key_prefix": "cl_old",
            "expired_at": (now - timedelta(hours=1)).isoformat(),
        },
    }


@pytest.mark.asyncio
async def test_check_api_key_expiration_does_nothing_without_matches():
    empty_expiring_query = _query_returning([])
    empty_expired_query = _query_returning([])

    with (
        patch.object(
            api_key_task.APIKey,
            "filter",
            side_effect=[empty_expiring_query, empty_expired_query],
        ),
        patch.object(
            api_key_task.AutoNotificationService,
            "send_to_user",
            new=AsyncMock(),
        ) as send,
    ):
        await api_key_task._check_api_key_expiration()

    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_api_key_expiration_propagates_notification_failure():
    now = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    expiring_key = SimpleNamespace(
        id="key-7",
        name="Seven days",
        key_prefix="cl_7",
        expires_at=now + timedelta(days=7),
        user=SimpleNamespace(id="user", locale="en"),
    )

    with (
        patch.object(api_key_task, "now_utc", return_value=now),
        patch.object(
            api_key_task.APIKey,
            "filter",
            return_value=_query_returning([expiring_key]),
        ) as filter_mock,
        patch.object(api_key_task, "t", return_value="translated"),
        patch.object(
            api_key_task.AutoNotificationService,
            "send_to_user",
            new=AsyncMock(side_effect=RuntimeError("notification unavailable")),
        ),
        pytest.raises(RuntimeError, match="notification unavailable"),
    ):
        await api_key_task._check_api_key_expiration()

    filter_mock.assert_called_once()


def test_task_wrapper_runs_check_and_propagates_failure():
    loop = MagicMock()
    loop.run_until_complete.side_effect = RuntimeError("check failed")

    with (
        patch.object(api_key_task, "_get_event_loop", return_value=loop),
        patch.object(
            api_key_task,
            "_check_api_key_expiration",
            new=MagicMock(return_value="check"),
        ),
        pytest.raises(RuntimeError, match="check failed"),
    ):
        api_key_task.check_api_key_expiration_task.run()

    loop.run_until_complete.assert_called_once_with("check")
