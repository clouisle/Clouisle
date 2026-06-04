from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import NotificationAuditAction
from app.services.notification import create_notification


@pytest.mark.asyncio
async def test_create_notification_saves_notification_before_audit():
    notification = SimpleNamespace(id="notification-id", save=AsyncMock())

    with patch(
        "app.services.notification.create_notification_audit",
        new=AsyncMock(),
    ) as create_audit:
        result = await create_notification(notification)  # type: ignore[arg-type]

    notification.save.assert_awaited_once()
    create_audit.assert_awaited_once_with(
        notification_id="notification-id",
        action=NotificationAuditAction.CREATE,
        user=None,
        meta=None,
    )
    assert result is notification
