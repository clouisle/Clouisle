from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.models.notification import (
    AutoNotificationType,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
)
from app.models.site_setting import SiteSetting
from app.services.auto_notification import AutoNotificationService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (None, {}),
        ({"enabled_types": [AutoNotificationType.USER_ACTIVATED.value]}, True),
        ({"enabled_types": []}, False),
    ],
)
async def test_config_and_enabled_rules(config, expected):
    with patch.object(SiteSetting, "get_value", new=AsyncMock(return_value=config)):
        if config is None:
            assert await AutoNotificationService.get_config() == expected
        else:
            assert (
                await AutoNotificationService.is_enabled(
                    AutoNotificationType.USER_ACTIVATED
                )
                is expected
            )


@pytest.mark.asyncio
async def test_get_channels_ignores_unknown_values(caplog):
    config = {"channels": ["email", "unknown", "slack"]}
    with patch.object(
        AutoNotificationService, "get_config", new=AsyncMock(return_value=config)
    ):
        channels = await AutoNotificationService.get_channels()

    assert channels == [NotificationChannel.EMAIL, NotificationChannel.SLACK]
    assert "Unknown notification channel: unknown" in caplog.text


@pytest.mark.asyncio
async def test_send_skips_disabled_type_without_creating():
    with (
        patch.object(
            AutoNotificationService, "is_enabled", new=AsyncMock(return_value=False)
        ),
        patch.object(Notification, "create", new=AsyncMock()) as create,
    ):
        result = await AutoNotificationService.send(
            AutoNotificationType.USER_ACTIVATED,
            NotificationScope.USER,
            "Title",
            "Content",
            user_id=uuid4(),
        )

    assert result is None
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_creates_audit_and_dispatches_configured_channels():
    user_id = uuid4()
    notification = SimpleNamespace(id=uuid4())
    with (
        patch.object(
            AutoNotificationService, "is_enabled", new=AsyncMock(return_value=True)
        ),
        patch.object(
            Notification, "create", new=AsyncMock(return_value=notification)
        ) as create,
        patch(
            "app.services.auto_notification.create_notification", new=AsyncMock()
        ) as audit,
        patch.object(
            AutoNotificationService,
            "get_channels",
            new=AsyncMock(return_value=[NotificationChannel.EMAIL]),
        ),
        patch.object(
            AutoNotificationService, "_trigger_external_channels", new=AsyncMock()
        ) as dispatch,
    ):
        result = await AutoNotificationService.send_to_user(
            AutoNotificationType.USER_ACTIVATED,
            user_id,
            "Title",
            "Content",
            data={"key": "value"},
            link_url="/users/me",
            level=NotificationLevel.HIGH,
        )

    assert result is notification
    kwargs = create.await_args.kwargs
    assert {
        "scope": NotificationScope.USER,
        "user_id": user_id,
        "team_id": None,
        "type": AutoNotificationType.USER_ACTIVATED.value,
        "source": NotificationSource.SYSTEM,
        "title": "Title",
        "content": "Content",
        "level": NotificationLevel.HIGH,
        "data": {"key": "value"},
        "link_url": "/users/me",
    }.items() <= kwargs.items()
    audit.assert_awaited_once_with(notification)
    dispatch.assert_awaited_once_with(notification, [NotificationChannel.EMAIL])


@pytest.mark.asyncio
async def test_send_propagates_creation_error_without_audit():
    with (
        patch.object(
            AutoNotificationService, "is_enabled", new=AsyncMock(return_value=True)
        ),
        patch.object(
            Notification,
            "create",
            new=AsyncMock(side_effect=RuntimeError("database down")),
        ),
        patch(
            "app.services.auto_notification.create_notification", new=AsyncMock()
        ) as audit,
    ):
        with pytest.raises(RuntimeError, match="database down"):
            await AutoNotificationService.send_global(
                AutoNotificationType.SECURITY_ACCOUNT_LOCKED, "Title", "Content"
            )

    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_external_channels_handles_disabled_success_and_error():
    notification = SimpleNamespace(id=uuid4())
    successful_delivery = SimpleNamespace(save=AsyncMock())
    failed_delivery = SimpleNamespace(save=AsyncMock())
    task = Mock()
    task.delay.side_effect = [
        SimpleNamespace(id="task-id"),
        RuntimeError("broker down"),
    ]

    with (
        patch.object(
            AutoNotificationService,
            "_is_channel_enabled",
            new=AsyncMock(side_effect=[False, True, True]),
        ),
        patch.object(
            NotificationDelivery,
            "create",
            new=AsyncMock(side_effect=[successful_delivery, failed_delivery]),
        ) as create_delivery,
        patch("app.tasks.notification.send_notification_email_task", task),
        patch("app.tasks.notification.send_notification_slack_task", task),
    ):
        await AutoNotificationService._trigger_external_channels(
            notification,
            [
                NotificationChannel.WEBHOOK,
                NotificationChannel.EMAIL,
                NotificationChannel.SLACK,
            ],
        )

    assert create_delivery.await_count == 2
    assert successful_delivery.task_id == "task-id"
    successful_delivery.save.assert_awaited_once()
    assert failed_delivery.status is NotificationDeliveryStatus.FAILED
    assert failed_delivery.error_message == "task_dispatch_failed"
    failed_delivery.save.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "setting", "value", "expected"),
    [
        (NotificationChannel.EMAIL, "smtp_enabled", True, True),
        (NotificationChannel.SLACK, "slack_enabled", False, False),
    ],
)
async def test_channel_enabled_uses_channel_setting(channel, setting, value, expected):
    with patch.object(
        SiteSetting, "get_value", new=AsyncMock(return_value=value)
    ) as get:
        assert await AutoNotificationService._is_channel_enabled(channel) is expected
    get.assert_awaited_once_with(setting, False)


@pytest.mark.asyncio
async def test_unknown_channel_is_disabled_without_setting_lookup():
    with patch.object(SiteSetting, "get_value", new=AsyncMock()) as get:
        assert await AutoNotificationService._is_channel_enabled("unknown") is False  # type: ignore[arg-type]
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_to_team_sets_team_scope():
    team_id = uuid4()
    with patch.object(AutoNotificationService, "send", new=AsyncMock()) as send:
        await AutoNotificationService.send_to_team(
            AutoNotificationType.TEAM_MEMBER_ADDED, team_id, "Title", "Content"
        )

    assert send.await_args.kwargs["scope"] is NotificationScope.TEAM
    assert send.await_args.kwargs["team_id"] == team_id
