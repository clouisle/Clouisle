import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks.api_key import (
    _check_api_key_expiration,
    _get_event_loop,
    check_api_key_expiration_task,
)


class Query:
    def __init__(self, results):
        self.results = results

    def prefetch_related(self, *_args):
        async def resolve():
            return self.results

        return resolve()


@pytest.mark.asyncio
async def test_check_api_key_expiration_sends_expiring_and_expired_notifications():
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    user = SimpleNamespace(id=uuid4(), locale="zh")
    expiring_key = SimpleNamespace(
        id=uuid4(),
        user=user,
        name="Soon",
        key_prefix="clou_soon",
        expires_at=now + timedelta(days=3),
    )
    expired_key = SimpleNamespace(
        id=uuid4(),
        user=user,
        name="Past",
        key_prefix="clou_past",
        expires_at=now - timedelta(hours=1),
    )
    filters = MagicMock(side_effect=[Query([expiring_key]), Query([expired_key])])

    with (
        patch("app.tasks.api_key.now_utc", return_value=now),
        patch("app.tasks.api_key.APIKey.filter", filters),
        patch("app.tasks.api_key.t", side_effect=lambda key, **_kwargs: key),
        patch(
            "app.tasks.api_key.AutoNotificationService.send_to_user", new=AsyncMock()
        ) as send_notification,
    ):
        await _check_api_key_expiration()

    assert filters.call_args_list[0].kwargs == {
        "is_active": True,
        "expires_at__isnull": False,
        "expires_at__gt": now,
        "expires_at__lte": now + timedelta(days=7),
    }
    assert filters.call_args_list[1].kwargs == {
        "is_active": True,
        "expires_at__isnull": False,
        "expires_at__gt": now - timedelta(hours=24),
        "expires_at__lte": now,
    }
    assert send_notification.await_args_list[0].kwargs == {
        "notification_type": AutoNotificationType.APIKEY_EXPIRING,
        "user_id": user.id,
        "title": "notify_apikey_expiring_title",
        "content": "notify_apikey_expiring_content",
        "level": NotificationLevel.HIGH,
        "data": {
            "api_key_id": str(expiring_key.id),
            "key_name": "Soon",
            "key_prefix": "clou_soon",
            "expires_at": expiring_key.expires_at.isoformat(),
            "days_remaining": 3,
        },
    }
    assert send_notification.await_args_list[1].kwargs == {
        "notification_type": AutoNotificationType.APIKEY_EXPIRED,
        "user_id": user.id,
        "title": "notify_apikey_expired_title",
        "content": "notify_apikey_expired_content",
        "level": NotificationLevel.HIGH,
        "data": {
            "api_key_id": str(expired_key.id),
            "key_name": "Past",
            "key_prefix": "clou_past",
            "expired_at": expired_key.expires_at.isoformat(),
        },
    }


@pytest.mark.asyncio
async def test_check_api_key_expiration_skips_non_reminder_day_and_uses_default_locale():
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    skipped_key = SimpleNamespace(expires_at=now + timedelta(days=2))
    expired_key = SimpleNamespace(
        id=uuid4(),
        user=SimpleNamespace(id=uuid4()),
        name="Past",
        key_prefix="clou_past",
        expires_at=now,
    )

    with (
        patch(
            "app.tasks.api_key.APIKey.filter",
            side_effect=[Query([skipped_key]), Query([expired_key])],
        ),
        patch("app.tasks.api_key.now_utc", return_value=now),
        patch("app.tasks.api_key.t", side_effect=lambda key, **kwargs: kwargs["lang"]),
        patch(
            "app.tasks.api_key.AutoNotificationService.send_to_user", new=AsyncMock()
        ) as send_notification,
    ):
        await _check_api_key_expiration()

    send_notification.assert_awaited_once()
    assert send_notification.await_args.kwargs["title"] == "en"


def test_check_api_key_expiration_task_logs_and_reraises_failure(caplog):
    loop = MagicMock()

    with (
        patch("app.tasks.api_key._get_event_loop", return_value=loop),
        patch(
            "app.tasks.api_key._check_api_key_expiration",
            new=MagicMock(return_value=object()),
        ),
        patch.object(loop, "run_until_complete", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError, match="boom"),
        caplog.at_level("ERROR"),
    ):
        check_api_key_expiration_task.run()

    assert "Failed to check API key expiration: boom" in caplog.text


def test_get_event_loop_replaces_closed_loop():
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    replacement_loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(closed_loop)
        with patch("asyncio.new_event_loop", return_value=replacement_loop):
            assert _get_event_loop() is replacement_loop
    finally:
        replacement_loop.close()
        asyncio.set_event_loop(None)
