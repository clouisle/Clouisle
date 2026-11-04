from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.im import ImMessageType
from app.models.notification import Notification, NotificationLevel, NotificationScope
from app.services import im_system_bridge


@pytest.mark.asyncio
async def test_bridge_user_notification_to_im() -> None:
    user_id = uuid4()
    team_id = uuid4()
    notif = Notification(
        id=uuid4(),
        scope=NotificationScope.USER,
        type="workflow.pause_pending",
        title="Workflow Paused",
        content="Waiting for approval",
        level=NotificationLevel.HIGH,
        data={"run_id": "run-123"},
    )
    notif.user_id = user_id
    notif.team_id = team_id

    with patch(
        "app.services.im_service.send_system_message", new_callable=AsyncMock
    ) as mock_send:
        await im_system_bridge.bridge_notification_to_im(notif)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["team_id"] == team_id
        assert call_kwargs["recipient_user_id"] == user_id
        assert call_kwargs["msg_type"] == ImMessageType.CARD
        assert "Workflow Paused" in call_kwargs["content"]
        assert call_kwargs["payload"]["data"] == {"run_id": "run-123"}


@pytest.mark.asyncio
async def test_sync_legacy_notifications_for_user_skips_when_existing() -> None:
    user_id = uuid4()
    team_id = uuid4()
    fake_conv = AsyncMock(id=uuid4())

    with (
        patch(
            "app.models.im.ImConversation.filter",
            return_value=AsyncMock(first=AsyncMock(return_value=fake_conv)),
        ),
        patch(
            "app.models.im.ImMessage.filter",
            return_value=AsyncMock(exists=AsyncMock(return_value=True)),
        ),
    ):
        # 已经存在消息，不执行同步
        await im_system_bridge.sync_legacy_notifications_for_user(team_id, user_id)
