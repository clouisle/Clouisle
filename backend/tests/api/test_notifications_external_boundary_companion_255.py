from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import notifications as endpoint
from app.models.notification import NotificationChannel, NotificationScope
from app.schemas.notification import NotificationAdminCreate
from app.schemas.response import BusinessError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "module", "getter", "config", "message"),
    [
        (
            NotificationChannel.EMAIL,
            "app.core.email",
            "get_smtp_config",
            {"enabled": False, "host": None, "from_address": None},
            "smtp_not_enabled",
        ),
        (
            NotificationChannel.EMAIL,
            "app.core.email",
            "get_smtp_config",
            {"enabled": True, "host": None, "from_address": "from@example.com"},
            "smtp_not_configured",
        ),
        (
            NotificationChannel.WEBHOOK,
            "app.core.webhook",
            "get_webhook_config",
            {"enabled": False, "url": None},
            "webhook_not_enabled",
        ),
    ],
)
async def test_issue255_notification_channel_configuration_failures(
    monkeypatch, channel, module, getter, config, message
):
    boundary = AsyncMock(return_value=config)
    monkeypatch.setattr(f"{module}.{getter}", boundary)
    payload = NotificationAdminCreate(
        scope=NotificationScope.GLOBAL,
        type="test",
        title="Test",
        content="Body",
        notify_channels=[channel],
    )

    with pytest.raises(BusinessError) as caught:
        await endpoint.admin_create_notification(
            payload, SimpleNamespace(is_superuser=True)
        )

    assert caught.value.msg_key == message
    boundary.assert_awaited_once_with()
