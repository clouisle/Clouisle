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
from app.tasks import notification as tasks


def notification(**overrides):
    values = {
        "id": uuid4(),
        "scope": NotificationScope.GLOBAL,
        "team_id": None,
        "user_id": None,
        "title": "Deployment complete",
        "content": "The deployment succeeded.",
        "link_url": "https://example.test/deployments/1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def query(**methods):
    value = MagicMock()
    for name, result in methods.items():
        setattr(value, name, AsyncMock(return_value=result))
    value.prefetch_related.return_value = value
    return value


@pytest.mark.anyio
async def test_update_delivery_status_transitions_and_counts_retries():
    delivery = SimpleNamespace(
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=1,
        sent_at=None,
        save=AsyncMock(),
    )
    orm = query(first=delivery)
    notification_id = uuid4()

    with patch.object(tasks.NotificationDelivery, "filter", return_value=orm):
        await tasks._update_delivery_status(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.FAILED,
            "notification_delivery_failed",
        )
        await tasks._update_delivery_status(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SUCCESS,
        )

    assert delivery.status == NotificationDeliveryStatus.SUCCESS
    assert delivery.error_message == "notification_delivery_failed"
    assert delivery.retry_count == 2
    assert delivery.sent_at is not None
    assert delivery.save.await_count == 2


@pytest.mark.anyio
async def test_update_delivery_status_ignores_missing_delivery():
    orm = query(first=None)
    with patch.object(tasks.NotificationDelivery, "filter", return_value=orm):
        await tasks._update_delivery_status(
            uuid4(), NotificationChannel.SLACK, NotificationDeliveryStatus.FAILED
        )

    orm.first.assert_awaited_once()


@pytest.mark.anyio
async def test_recipients_filter_inactive_and_missing_email_addresses():
    active = SimpleNamespace(email="active@example.test", locale="zh")
    missing_email = SimpleNamespace(email="", locale="en")
    global_orm = query(all=[active, missing_email])
    team_member = SimpleNamespace(
        user=SimpleNamespace(email="team@example.test", locale="en", is_active=True)
    )
    inactive_member = SimpleNamespace(
        user=SimpleNamespace(
            email="inactive@example.test", locale="en", is_active=False
        )
    )
    team_orm = MagicMock()
    team_orm.prefetch_related = AsyncMock(return_value=[team_member, inactive_member])

    with patch.object(tasks.User, "filter", return_value=global_orm) as user_filter:
        assert await tasks._get_notification_recipients(notification()) == [
            ("active@example.test", "zh")
        ]
    user_filter.assert_called_once_with(is_active=True, email__not="")

    with patch.object(tasks.TeamMember, "filter", return_value=team_orm):
        result = await tasks._get_notification_recipients(
            notification(scope=NotificationScope.TEAM, team_id=uuid4())
        )
    assert result == [("team@example.test", "en")]


@pytest.mark.anyio
async def test_recipients_handle_incomplete_scope_configuration_safely():
    with (
        patch.object(tasks.User, "filter") as user_filter,
        patch.object(tasks.TeamMember, "filter") as member_filter,
    ):
        assert (
            await tasks._get_notification_recipients(
                notification(scope=NotificationScope.USER)
            )
            == []
        )
        assert (
            await tasks._get_notification_recipients(
                notification(scope=NotificationScope.TEAM)
            )
            == []
        )

    user_filter.assert_not_called()
    member_filter.assert_not_called()


@pytest.mark.anyio
async def test_email_delivery_marks_sending_then_success_for_all_recipients():
    item = notification()
    context = tasks.NotificationContext(notification=item, site_name="Clouisle")
    updates = AsyncMock()
    send_email = AsyncMock(side_effect=[True, True])

    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(
                return_value=[("en@example.test", "en"), ("zh@example.test", "zh")]
            ),
        ),
        patch.object(tasks, "send_email", new=send_email),
    ):
        await tasks._send_notification_email(item.id)

    assert [email.args[0] for email in send_email.await_args_list] == [
        "en@example.test",
        "zh@example.test",
    ]
    assert updates.await_args_list == [
        call(item.id, NotificationChannel.EMAIL, NotificationDeliveryStatus.SENDING),
        call(item.id, NotificationChannel.EMAIL, NotificationDeliveryStatus.SUCCESS),
    ]


@pytest.mark.anyio
async def test_email_delivery_without_recipients_is_safe_success():
    item = notification()
    updates = AsyncMock()
    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks,
            "_load_notification_context",
            new=AsyncMock(
                return_value=tasks.NotificationContext(
                    notification=item, site_name="Clouisle"
                )
            ),
        ),
        patch.object(
            tasks, "_get_notification_recipients", new=AsyncMock(return_value=[])
        ),
        patch.object(tasks, "send_email", new=AsyncMock()) as send_email,
    ):
        await tasks._send_notification_email(item.id)

    send_email.assert_not_awaited()
    assert updates.await_args_list[-1] == call(
        item.id, NotificationChannel.EMAIL, NotificationDeliveryStatus.SUCCESS
    )


@pytest.mark.anyio
async def test_email_delivery_records_partial_success_without_raising():
    item = notification()
    updates = AsyncMock()
    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks,
            "_load_notification_context",
            new=AsyncMock(
                return_value=tasks.NotificationContext(
                    notification=item, site_name="Clouisle"
                )
            ),
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(
                return_value=[
                    ("sent@example.test", "en"),
                    ("failed@example.test", "en"),
                ]
            ),
        ),
        patch.object(tasks, "send_email", new=AsyncMock(side_effect=[True, False])),
        patch.object(tasks, "t", return_value="1/2 delivered"),
    ):
        await tasks._send_notification_email(item.id)

    assert updates.await_args_list[-1] == call(
        item.id,
        NotificationChannel.EMAIL,
        NotificationDeliveryStatus.SUCCESS,
        "1/2 delivered",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function_name", "sender_name", "channel", "locale"),
    [
        (
            "_send_notification_dingtalk",
            "send_dingtalk_notification",
            NotificationChannel.DINGTALK,
            "zh",
        ),
        (
            "_send_notification_webhook",
            "send_webhook_notification",
            NotificationChannel.WEBHOOK,
            "en",
        ),
        (
            "_send_notification_slack",
            "send_slack_notification",
            NotificationChannel.SLACK,
            "en",
        ),
    ],
)
async def test_external_delivery_marks_success_with_mocked_channel(
    function_name, sender_name, channel, locale
):
    item = notification()
    context = tasks.NotificationContext(notification=item, site_name="Clouisle")
    updates = AsyncMock()
    sender = AsyncMock(return_value=True)
    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(tasks, sender_name, new=sender),
        patch.object(
            tasks, "_build_notification_message", return_value=("title", "content")
        ) as message,
    ):
        assert await getattr(tasks, function_name)(item.id) is True

    message.assert_called_once_with(context, locale)
    sender.assert_awaited_once_with(
        title="title", content="content", link_url=item.link_url
    )
    assert updates.await_args_list[-1] == call(
        item.id, channel, NotificationDeliveryStatus.SUCCESS
    )


@pytest.mark.anyio
async def test_external_delivery_failure_raises_after_sending_transition():
    item = notification()
    updates = AsyncMock()
    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=None)
        ),
    ):
        with pytest.raises(ValueError, match="notification_not_found"):
            await tasks._send_notification_slack(item.id)

    assert updates.await_args_list == [
        call(item.id, NotificationChannel.SLACK, NotificationDeliveryStatus.SENDING)
    ]


def test_email_task_marks_failed_and_retries_after_channel_exception():
    notification_id = str(uuid4())
    retry = MagicMock(side_effect=RuntimeError("retry scheduled"))

    class Loop:
        def run_until_complete(self, coroutine):
            return asyncio.run(coroutine)

    with (
        patch.object(tasks, "_get_event_loop", return_value=Loop()),
        patch.object(
            tasks,
            "_send_notification_email",
            new=AsyncMock(side_effect=RuntimeError("channel down")),
        ),
        patch.object(tasks, "_update_delivery_status", new=AsyncMock()) as update,
    ):
        tasks.send_notification_email_task.request.retries = 2
        tasks.send_notification_email_task.retry = retry
        with pytest.raises(RuntimeError, match="retry scheduled"):
            tasks.send_notification_email_task.run(notification_id)

    assert update.await_args_list == [
        call(
            UUID(notification_id),
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.FAILED,
            "notification_delivery_failed",
        )
    ]
    retry.assert_called_once()
    assert retry.call_args.kwargs["countdown"] == 180
