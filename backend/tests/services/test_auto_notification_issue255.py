from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.notification import (
    AutoNotificationType,
    NotificationChannel,
    NotificationDeliveryStatus,
)
from app.services.auto_notification import AutoNotificationService


@pytest.mark.asyncio
async def test_config_and_channel_filters_cover_defaults_and_unknown_values():
    with patch(
        "app.services.auto_notification.SiteSetting.get_value",
        new=AsyncMock(return_value=None),
    ):
        assert await AutoNotificationService.get_config() == {}

    with (
        patch.object(
            AutoNotificationService,
            "get_config",
            new=AsyncMock(
                return_value={
                    "enabled_types": [AutoNotificationType.USER_ACTIVATED.value],
                    "channels": ["email", "unknown"],
                }
            ),
        ),
        patch("app.services.auto_notification.logger.warning") as warning,
    ):
        assert await AutoNotificationService.is_enabled(
            AutoNotificationType.USER_ACTIVATED
        )
        assert await AutoNotificationService.get_channels() == [
            NotificationChannel.EMAIL
        ]
        warning.assert_called_once()

    assert not await AutoNotificationService._is_channel_enabled(object())


@pytest.mark.asyncio
async def test_send_skips_disabled_type_without_creating_notification():
    with (
        patch.object(
            AutoNotificationService,
            "is_enabled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.auto_notification.Notification.create", new=AsyncMock()
        ) as create,
    ):
        assert (
            await AutoNotificationService.send_global(
                AutoNotificationType.USER_ACTIVATED, "title", "content"
            )
            is None
        )

    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_creates_audit_and_dispatches_configured_channels():
    notification = SimpleNamespace(id=uuid4())
    created_at = object()
    channels = [NotificationChannel.EMAIL]

    with (
        patch.object(
            AutoNotificationService, "is_enabled", new=AsyncMock(return_value=True)
        ),
        patch.object(
            AutoNotificationService,
            "get_channels",
            new=AsyncMock(return_value=channels),
        ),
        patch.object(
            AutoNotificationService,
            "_trigger_external_channels",
            new=AsyncMock(),
        ) as trigger,
        patch(
            "app.services.auto_notification.Notification.create",
            new=AsyncMock(return_value=notification),
        ) as create,
        patch(
            "app.services.auto_notification.create_notification", new=AsyncMock()
        ) as audit,
        patch("app.services.auto_notification.now_utc", return_value=created_at),
    ):
        result = await AutoNotificationService.send_to_user(
            AutoNotificationType.USER_ACTIVATED,
            uuid4(),
            "title",
            "content",
            data={"key": "value"},
        )

    assert result is notification
    assert create.await_args.kwargs["created_at"] is created_at
    assert create.await_args.kwargs["updated_at"] is created_at
    audit.assert_awaited_once_with(notification)
    trigger.assert_awaited_once_with(notification, channels)


@pytest.mark.asyncio
async def test_external_channels_skip_disabled_and_record_dispatch_results():
    from app.tasks import notification as notification_tasks

    notification = SimpleNamespace(id=uuid4())
    successful = SimpleNamespace(
        task_id=None, status=None, error_message=None, save=AsyncMock()
    )
    failed = SimpleNamespace(
        task_id=None, status=None, error_message=None, save=AsyncMock()
    )
    delivery_create = AsyncMock(side_effect=[successful, failed])
    email_task = MagicMock()
    email_task.delay.return_value = SimpleNamespace(id="task-1")
    slack_task = MagicMock()
    slack_task.delay.side_effect = RuntimeError("broker unavailable")

    with (
        patch.object(
            AutoNotificationService,
            "_is_channel_enabled",
            new=AsyncMock(side_effect=[False, True, True]),
        ),
        patch(
            "app.services.auto_notification.NotificationDelivery.create",
            new=delivery_create,
        ),
        patch.object(notification_tasks, "send_notification_email_task", email_task),
        patch.object(notification_tasks, "send_notification_slack_task", slack_task),
    ):
        await AutoNotificationService._trigger_external_channels(
            notification,
            [
                NotificationChannel.WEBHOOK,
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
            ],
        )

    assert (
        delivery_create.await_args_list[0].kwargs["channel"]
        == NotificationChannel.EMAIL
    )
    assert (
        delivery_create.await_args_list[0].kwargs["status"]
        == NotificationDeliveryStatus.PENDING
    )
    email_task.delay.assert_called_once_with(str(notification.id))
    assert successful.task_id == "task-1"
    successful.save.assert_awaited_once()
    assert failed.status == NotificationDeliveryStatus.FAILED
    assert failed.error_message == "task_dispatch_failed"
    failed.save.assert_awaited_once()
