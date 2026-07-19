from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import uuid4

import pytest

from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationScope,
)
from app.tasks import notification as tasks


DELIVERY_TASKS = [
    (
        tasks.send_notification_email_task,
        "_send_notification_email",
        NotificationChannel.EMAIL,
    ),
    (
        tasks.send_notification_dingtalk_task,
        "_send_notification_dingtalk",
        NotificationChannel.DINGTALK,
    ),
    (
        tasks.send_notification_wechat_task,
        "_send_notification_wechat",
        NotificationChannel.WECHAT,
    ),
    (
        tasks.send_notification_feishu_task,
        "_send_notification_feishu",
        NotificationChannel.FEISHU,
    ),
    (
        tasks.send_notification_webhook_task,
        "_send_notification_webhook",
        NotificationChannel.WEBHOOK,
    ),
    (
        tasks.send_notification_slack_task,
        "_send_notification_slack",
        NotificationChannel.SLACK,
    ),
]

CHANNEL_SENDERS = [
    (
        tasks._send_notification_dingtalk,
        "send_dingtalk_notification",
        NotificationChannel.DINGTALK,
        "zh",
    ),
    (
        tasks._send_notification_wechat,
        "send_wechat_notification",
        NotificationChannel.WECHAT,
        "zh",
    ),
    (
        tasks._send_notification_feishu,
        "send_feishu_notification",
        NotificationChannel.FEISHU,
        "zh",
    ),
    (
        tasks._send_notification_webhook,
        "send_webhook_notification",
        NotificationChannel.WEBHOOK,
        "en",
    ),
    (
        tasks._send_notification_slack,
        "send_slack_notification",
        NotificationChannel.SLACK,
        "en",
    ),
]


@pytest.mark.parametrize(("task", "worker_name", "channel"), DELIVERY_TASKS)
def test_delivery_task_runs_worker(task, worker_name, channel):
    notification_id = uuid4()

    with patch.object(tasks, worker_name, new=AsyncMock()) as worker:
        task.run(str(notification_id))

    worker.assert_awaited_once_with(notification_id)


@pytest.mark.parametrize(("task", "worker_name", "channel"), DELIVERY_TASKS)
def test_delivery_task_marks_failed_and_retries(task, worker_name, channel):
    notification_id = uuid4()
    error = RuntimeError("delivery failed")

    with (
        patch.object(tasks, worker_name, new=AsyncMock(side_effect=error)),
        patch.object(
            tasks, "_update_delivery_status", new=AsyncMock()
        ) as update_status,
        patch.object(task, "retry", side_effect=error) as retry,
        patch.object(task.request, "retries", 1),
        pytest.raises(RuntimeError, match="delivery failed"),
    ):
        task.run(str(notification_id))

    update_status.assert_awaited_once_with(
        notification_id,
        channel,
        NotificationDeliveryStatus.FAILED,
        "notification_delivery_failed",
    )
    retry.assert_called_once_with(exc=error, countdown=120)


@pytest.mark.asyncio
async def test_send_email_skips_delivery_when_there_are_no_recipients():
    notification_id = uuid4()
    ctx = SimpleNamespace(notification=SimpleNamespace())

    with (
        patch.object(
            tasks, "_update_delivery_status", new=AsyncMock()
        ) as update_status,
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=ctx)
        ),
        patch.object(
            tasks, "_get_notification_recipients", new=AsyncMock(return_value=[])
        ),
        patch.object(tasks, "send_email", new=AsyncMock()) as send_email,
    ):
        await tasks._send_notification_email(notification_id)

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
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_email_records_partial_success():
    notification_id = uuid4()
    ctx = SimpleNamespace(
        notification=SimpleNamespace(
            scope=NotificationScope.GLOBAL,
            title="Title",
            content="Body",
            link_url=None,
        ),
        site_name="Clouisle",
        team=None,
        user=None,
    )

    with (
        patch.object(
            tasks, "_update_delivery_status", new=AsyncMock()
        ) as update_status,
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=ctx)
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(
                return_value=[("ok@example.com", "en"), ("bad@example.com", "en")]
            ),
        ),
        patch.object(
            tasks, "send_email", new=AsyncMock(side_effect=[True, False])
        ) as send_email,
        patch.object(tasks, "t", return_value="1 of 2 delivered") as translate,
    ):
        await tasks._send_notification_email(notification_id)

    assert send_email.await_count == 2
    update_status.assert_awaited_with(
        notification_id,
        NotificationChannel.EMAIL,
        NotificationDeliveryStatus.SUCCESS,
        "1 of 2 delivered",
    )
    translate.assert_any_call(
        "notification_delivery_partial_success", success_count=1, total_count=2
    )


@pytest.mark.asyncio
async def test_send_email_raises_when_every_delivery_fails():
    notification_id = uuid4()
    ctx = SimpleNamespace(
        notification=SimpleNamespace(
            scope=NotificationScope.GLOBAL,
            title="Title",
            content="Body",
            link_url=None,
        ),
        site_name="Clouisle",
        team=None,
        user=None,
    )

    with (
        patch.object(
            tasks, "_update_delivery_status", new=AsyncMock()
        ) as update_status,
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=ctx)
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(return_value=[("bad@example.com", "en")]),
        ),
        patch.object(
            tasks, "send_email", new=AsyncMock(side_effect=OSError("smtp down"))
        ),
        pytest.raises(RuntimeError, match="email_send_failed"),
    ):
        await tasks._send_notification_email(notification_id)

    update_status.assert_awaited_once_with(
        notification_id,
        NotificationChannel.EMAIL,
        NotificationDeliveryStatus.SENDING,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("worker", "sender_name", "channel", "locale"), CHANNEL_SENDERS
)
async def test_channel_delivery_success(worker, sender_name, channel, locale):
    notification_id = uuid4()
    ctx = SimpleNamespace(
        notification=SimpleNamespace(link_url="https://example.com"),
    )

    with (
        patch.object(
            tasks, "_update_delivery_status", new=AsyncMock()
        ) as update_status,
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=ctx)
        ),
        patch.object(
            tasks, "_build_notification_message", return_value=("Title", "Body")
        ) as build,
        patch.object(tasks, sender_name, new=AsyncMock(return_value=True)) as sender,
    ):
        assert await worker(notification_id) is True

    build.assert_called_once_with(ctx, locale)
    sender.assert_awaited_once_with(
        title="Title", content="Body", link_url="https://example.com"
    )
    assert update_status.await_args_list == [
        call(notification_id, channel, NotificationDeliveryStatus.SENDING),
        call(notification_id, channel, NotificationDeliveryStatus.SUCCESS),
    ]


@pytest.mark.asyncio
async def test_channel_delivery_raises_when_sender_returns_false():
    notification_id = uuid4()
    ctx = SimpleNamespace(notification=SimpleNamespace(link_url=None))

    with (
        patch.object(tasks, "_update_delivery_status", new=AsyncMock()),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=ctx)
        ),
        patch.object(
            tasks, "_build_notification_message", return_value=("Title", "Body")
        ),
        patch.object(
            tasks, "send_slack_notification", new=AsyncMock(return_value=False)
        ),
        pytest.raises(RuntimeError, match="slack_send_failed"),
    ):
        await tasks._send_notification_slack(notification_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_retry_count"),
    [
        (NotificationDeliveryStatus.FAILED, 3),
        (NotificationDeliveryStatus.SUCCESS, 2),
    ],
)
async def test_update_delivery_status_persists_branch_fields(
    status, expected_retry_count
):
    notification_id = uuid4()
    delivery = SimpleNamespace(
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=2,
        sent_at=None,
        save=AsyncMock(),
    )
    query = Mock()
    query.first = AsyncMock(return_value=delivery)

    with (
        patch.object(
            tasks.NotificationDelivery, "filter", return_value=query
        ) as filter_delivery,
        patch.object(tasks, "now_utc", return_value="sent-at"),
    ):
        await tasks._update_delivery_status(
            notification_id, NotificationChannel.EMAIL, status, "error"
        )

    filter_delivery.assert_called_once_with(
        notification_id=notification_id, channel=NotificationChannel.EMAIL
    )
    assert delivery.status == status
    assert delivery.error_message == "error"
    assert delivery.retry_count == expected_retry_count
    assert delivery.sent_at == (
        "sent-at" if status == NotificationDeliveryStatus.SUCCESS else None
    )
    delivery.save.assert_awaited_once()
