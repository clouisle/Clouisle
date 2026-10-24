from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch
from uuid import uuid4

import pytest

from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationScope,
)
from app.tasks import notification


def notification_context():
    return notification.NotificationContext(
        notification=SimpleNamespace(
            scope=NotificationScope.GLOBAL,
            title="Maintenance",
            content="Tonight",
            link_url=None,
        ),
        site_name="Clouisle",
    )


@pytest.mark.asyncio
async def test_email_marks_delivery_success_when_no_recipients():
    notification_id = uuid4()
    update_status = AsyncMock()

    with (
        patch("app.tasks.notification._update_delivery_status", update_status),
        patch(
            "app.tasks.notification._load_notification_context",
            new=AsyncMock(return_value=notification_context()),
        ),
        patch(
            "app.tasks.notification._get_notification_recipients",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await notification._send_notification_email(notification_id)

    assert update_status.await_args_list == [
        call(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SENDING,
        ),
        call(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SUCCESS,
        ),
    ]
