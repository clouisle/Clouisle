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
        "link_url": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def query(result):
    value = MagicMock()
    value.first = AsyncMock(return_value=result)
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "id_field", "model_name", "subject"),
    [
        (NotificationScope.TEAM, "team_id", "Team", SimpleNamespace(name="Platform")),
        (NotificationScope.USER, "user_id", "User", SimpleNamespace(username="alice")),
    ],
)
async def test_loads_scoped_notification_context(scope, id_field, model_name, subject):
    subject_id = uuid4()
    item = notification(scope=scope, **{id_field: subject_id})

    with (
        patch.object(tasks.Notification, "filter", return_value=query(item)),
        patch.object(
            tasks.SiteSetting, "get_value", new=AsyncMock(return_value="Acme")
        ),
        patch.object(
            getattr(tasks, model_name), "filter", return_value=query(subject)
        ) as subject_filter,
    ):
        context = await tasks._load_notification_context(item.id)

    assert context == tasks.NotificationContext(
        item,
        "Acme",
        team=subject if scope == NotificationScope.TEAM else None,
        user=subject if scope == NotificationScope.USER else None,
    )
    subject_filter.assert_called_once_with(id=subject_id)


@pytest.mark.parametrize(
    ("scope", "subject", "expected_title", "expected_prefix"),
    [
        (
            NotificationScope.TEAM,
            SimpleNamespace(name="Platform"),
            "[Platform]",
            "Team",
        ),
        (NotificationScope.USER, SimpleNamespace(username="alice"), "[@alice]", "User"),
    ],
)
def test_builds_scoped_notification_messages(
    scope, subject, expected_title, expected_prefix
):
    item = notification(scope=scope)
    context = tasks.NotificationContext(
        item,
        "Acme",
        team=subject if scope == NotificationScope.TEAM else None,
        user=subject if scope == NotificationScope.USER else None,
    )

    with patch.object(tasks, "t", return_value=expected_prefix):
        title, content = tasks._build_notification_message(context)

    assert expected_title in title
    assert (
        content
        == f"**{expected_prefix}**: {subject.name if scope == NotificationScope.TEAM else subject.username}\n\n{item.content}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "user", "expected"),
    [
        (None, None, []),
        (uuid4(), None, []),
        (
            uuid4(),
            SimpleNamespace(email="alice@example.test", locale="zh"),
            [("alice@example.test", "zh")],
        ),
    ],
)
async def test_gets_user_notification_recipients(user_id, user, expected):
    item = notification(scope=NotificationScope.USER, user_id=user_id)

    with patch.object(tasks.User, "filter", return_value=query(user)) as user_filter:
        assert await tasks._get_notification_recipients(item) == expected

    if user_id:
        user_filter.assert_called_once_with(id=user_id, is_active=True)
    else:
        user_filter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "channel"),
    [
        ("_send_notification_email", NotificationChannel.EMAIL),
        ("_send_notification_dingtalk", NotificationChannel.DINGTALK),
        ("_send_notification_wechat", NotificationChannel.WECHAT),
        ("_send_notification_feishu", NotificationChannel.FEISHU),
        ("_send_notification_webhook", NotificationChannel.WEBHOOK),
    ],
)
async def test_delivery_fails_when_notification_context_is_missing(
    function_name, channel
):
    notification_id = uuid4()
    updates = AsyncMock()

    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=None)
        ),
    ):
        with pytest.raises(ValueError, match="notification_not_found"):
            await getattr(tasks, function_name)(notification_id)

    updates.assert_awaited_once_with(
        notification_id, channel, NotificationDeliveryStatus.SENDING
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "sender_name", "channel", "error"),
    [
        (
            "_send_notification_wechat",
            "send_wechat_notification",
            NotificationChannel.WECHAT,
            "wechat_send_failed",
        ),
        (
            "_send_notification_feishu",
            "send_feishu_notification",
            NotificationChannel.FEISHU,
            "feishu_send_failed",
        ),
    ],
)
async def test_delivery_fails_when_provider_returns_false(
    function_name, sender_name, channel, error
):
    item = notification()
    context = tasks.NotificationContext(item, "Acme")
    updates = AsyncMock()
    sender = AsyncMock(return_value=False)

    with (
        patch.object(tasks, "_update_delivery_status", new=updates),
        patch.object(
            tasks, "_load_notification_context", new=AsyncMock(return_value=context)
        ),
        patch.object(
            tasks, "_build_notification_message", return_value=("title", "body")
        ),
        patch.object(tasks, sender_name, new=sender),
    ):
        with pytest.raises(RuntimeError, match=error):
            await getattr(tasks, function_name)(item.id)

    sender.assert_awaited_once_with(title="title", content="body", link_url=None)
    assert updates.await_args_list == [
        call(item.id, channel, NotificationDeliveryStatus.SENDING)
    ]
