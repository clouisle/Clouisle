import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID, uuid4

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


@pytest.mark.asyncio
@pytest.mark.parametrize("send_result", [True, False])
async def test_dingtalk_delivery_marks_success_or_raises(send_result):
    notification_id = uuid4()
    update_status = AsyncMock()

    with (
        patch("app.tasks.notification._update_delivery_status", update_status),
        patch(
            "app.tasks.notification._load_notification_context",
            new=AsyncMock(return_value=notification_context()),
        ),
        patch(
            "app.tasks.notification._build_notification_message",
            return_value=("title", "content"),
        ),
        patch(
            "app.tasks.notification.send_dingtalk_notification",
            new=AsyncMock(return_value=send_result),
        ) as send_dingtalk,
    ):
        if send_result:
            assert (
                await notification._send_notification_dingtalk(notification_id) is True
            )
        else:
            with pytest.raises(RuntimeError, match="dingtalk_send_failed"):
                await notification._send_notification_dingtalk(notification_id)

    send_dingtalk.assert_awaited_once_with(
        title="title", content="content", link_url=None
    )
    expected_statuses = [
        call(
            notification_id,
            NotificationChannel.DINGTALK,
            NotificationDeliveryStatus.SENDING,
        )
    ]
    if send_result:
        expected_statuses.append(
            call(
                notification_id,
                NotificationChannel.DINGTALK,
                NotificationDeliveryStatus.SUCCESS,
            )
        )
    assert update_status.await_args_list == expected_statuses


def test_slack_task_marks_failed_delivery_and_retries():
    notification_id = str(uuid4())
    error = RuntimeError("unavailable")
    update_status = AsyncMock()
    task = notification.send_notification_slack_task
    loop = MagicMock()
    loop.run_until_complete.side_effect = lambda coroutine: asyncio.run(coroutine)

    with (
        patch("app.tasks.notification._get_event_loop", return_value=loop),
        patch(
            "app.tasks.notification._send_notification_slack",
            new=AsyncMock(side_effect=error),
        ),
        patch("app.tasks.notification._update_delivery_status", update_status),
        patch.object(task, "retry", side_effect=RuntimeError("retrying")) as retry,
    ):
        with pytest.raises(RuntimeError, match="retrying"):
            task.run(notification_id)

    update_status.assert_awaited_once_with(
        UUID(notification_id),
        NotificationChannel.SLACK,
        NotificationDeliveryStatus.FAILED,
        "notification_delivery_failed",
    )
    retry.assert_called_once_with(exc=error, countdown=60)
