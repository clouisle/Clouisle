from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.notification import (
    AutoNotificationType,
    NotificationChannel,
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
async def test_external_channels_dispatch_through_integration_factory():
    notification = SimpleNamespace(id=uuid4())
    delivery = SimpleNamespace(task_id=None, save=AsyncMock())
    task_result = SimpleNamespace(id="factory-task")
    dispatch = MagicMock(return_value=task_result)

    with (
        patch.object(
            AutoNotificationService,
            "_is_channel_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.auto_notification.NotificationDelivery.create",
            new=AsyncMock(return_value=delivery),
        ) as create_delivery,
        patch(
            "app.services.auto_notification.dispatch_notification_task",
            dispatch,
        ),
    ):
        await AutoNotificationService._trigger_external_channels(
            notification, [NotificationChannel.EMAIL]
        )

    create_delivery.assert_awaited_once()
    dispatch.assert_called_once_with(NotificationChannel.EMAIL, str(notification.id))
    assert delivery.task_id == "factory-task"
    delivery.save.assert_awaited_once()
