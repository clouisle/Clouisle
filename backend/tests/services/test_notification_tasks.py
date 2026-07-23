from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_message", "retry_count", "sets_sent_at"),
    [
        (NotificationDeliveryStatus.SENDING, None, 2, False),
        (NotificationDeliveryStatus.FAILED, "provider failed", 3, False),
        (NotificationDeliveryStatus.SUCCESS, None, 2, True),
    ],
)
async def test_update_delivery_status_applies_transition_fields(
    status, error_message, retry_count, sets_sent_at
):
    delivery = SimpleNamespace(
        status=None,
        error_message=None,
        retry_count=2,
        sent_at=None,
        save=AsyncMock(),
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=delivery)
    sent_at = object()

    with (
        patch.object(tasks.NotificationDelivery, "filter", return_value=query),
        patch.object(tasks, "now_utc", return_value=sent_at),
    ):
        await tasks._update_delivery_status(
            uuid4(), NotificationChannel.EMAIL, status, error_message
        )

    assert delivery.status == status
    assert delivery.error_message == error_message
    assert delivery.retry_count == retry_count
    assert delivery.sent_at is (sent_at if sets_sent_at else None)
    delivery.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_delivery_status_ignores_missing_delivery():
    query = MagicMock()
    query.first = AsyncMock(return_value=None)

    with patch.object(tasks.NotificationDelivery, "filter", return_value=query):
        await tasks._update_delivery_status(
            uuid4(), NotificationChannel.EMAIL, NotificationDeliveryStatus.SUCCESS
        )


@pytest.mark.asyncio
async def test_get_notification_recipients_filters_global_and_team_users():
    global_query = MagicMock()
    global_query.all = AsyncMock(
        return_value=[
            SimpleNamespace(email="active@example.test", locale="zh"),
            SimpleNamespace(email="", locale="en"),
        ]
    )
    members = [
        SimpleNamespace(
            user=SimpleNamespace(
                email="member@example.test", locale="en", is_active=True
            )
        ),
        SimpleNamespace(
            user=SimpleNamespace(
                email="inactive@example.test", locale="en", is_active=False
            )
        ),
        SimpleNamespace(user=SimpleNamespace(email="", locale="zh", is_active=True)),
    ]
    team_query = MagicMock()
    team_query.prefetch_related = AsyncMock(return_value=members)
    team_id = uuid4()

    with (
        patch.object(tasks.User, "filter", return_value=global_query) as user_filter,
        patch.object(
            tasks.TeamMember, "filter", return_value=team_query
        ) as member_filter,
    ):
        assert await tasks._get_notification_recipients(notification()) == [
            ("active@example.test", "zh")
        ]
        assert await tasks._get_notification_recipients(
            notification(scope=NotificationScope.TEAM, team_id=team_id)
        ) == [("member@example.test", "en")]

    user_filter.assert_called_once_with(is_active=True, email__not="")
    member_filter.assert_called_once_with(team_id=team_id)
    team_query.prefetch_related.assert_awaited_once_with("user")


@pytest.mark.asyncio
async def test_send_notification_email_marks_no_recipient_as_success():
    item = notification()
    context = tasks.NotificationContext(item, "Clouisle")
    updates = AsyncMock()

    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(
            tasks, "_get_notification_recipients", new=AsyncMock(return_value=[])
        ),
        patch.object(tasks, "send_email", new=AsyncMock()) as send_email,
    ):
        assert await tasks._send_notification_email(item.id) is None

    assert updates.await_args_list == [
        call(item.id, NotificationChannel.EMAIL, NotificationDeliveryStatus.SENDING),
        call(item.id, NotificationChannel.EMAIL, NotificationDeliveryStatus.SUCCESS),
    ]
    send_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_notification_email_groups_locales_and_records_partial_success():
    item = notification()
    context = tasks.NotificationContext(item, "Clouisle")
    recipients = [
        ("one@example.test", "en"),
        ("two@example.test", "en"),
        ("three@example.test", "zh"),
    ]
    updates = AsyncMock()
    send_email = AsyncMock(side_effect=[True, False, True])

    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(return_value=recipients),
        ),
        patch.object(
            tasks, "_build_notification_message", return_value=("title", "content")
        ) as build_message,
        patch.object(tasks, "_build_email_text", return_value="text"),
        patch.object(tasks, "_build_email_html", return_value="html"),
        patch.object(tasks, "send_email", new=send_email),
        patch.object(tasks, "t", return_value="2 of 3 delivered") as translate,
    ):
        await tasks._send_notification_email(item.id)

    assert build_message.call_args_list == [call(context, "en"), call(context, "zh")]
    assert send_email.await_args_list == [
        call("one@example.test", "【Clouisle】Deployment complete", "text", "html"),
        call("two@example.test", "【Clouisle】Deployment complete", "text", "html"),
        call("three@example.test", "【Clouisle】Deployment complete", "text", "html"),
    ]
    translate.assert_called_once_with(
        "notification_delivery_partial_success", success_count=2, total_count=3
    )
    assert updates.await_args_list[-1] == call(
        item.id,
        NotificationChannel.EMAIL,
        NotificationDeliveryStatus.SUCCESS,
        "2 of 3 delivered",
    )


@pytest.mark.asyncio
async def test_send_notification_email_raises_when_every_send_fails():
    item = notification()
    context = tasks.NotificationContext(item, "Clouisle")

    with (
        patch.object(tasks, "_update_delivery_status", new=AsyncMock()),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(
            tasks,
            "_get_notification_recipients",
            new=AsyncMock(return_value=[("one@example.test", "en")]),
        ),
        patch.object(
            tasks, "_build_notification_message", return_value=("title", "content")
        ),
        patch.object(tasks, "_build_email_text", return_value="text"),
        patch.object(tasks, "_build_email_html", return_value="html"),
        patch.object(tasks, "send_email", new=AsyncMock(return_value=False)),
    ):
        with pytest.raises(RuntimeError, match="email_send_failed"):
            await tasks._send_notification_email(item.id)
