from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationScope,
)
from app.tasks import notification as tasks


def _notification(scope=NotificationScope.GLOBAL, **overrides):
    values = {
        "scope": scope,
        "team_id": None,
        "user_id": None,
        "title": "Maintenance",
        "content": "Service update",
        "link_url": "https://example.test/status",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _query(result):
    return SimpleNamespace(first=AsyncMock(return_value=result))


@pytest.mark.parametrize("closed", [True, False])
def test_get_event_loop_replaces_only_closed_loop(monkeypatch, closed):
    current = Mock(is_closed=Mock(return_value=closed))
    replacement = Mock()
    monkeypatch.setattr("asyncio.get_event_loop", Mock(return_value=current))
    new_event_loop = Mock(return_value=replacement)
    set_event_loop = Mock()
    monkeypatch.setattr("asyncio.new_event_loop", new_event_loop)
    monkeypatch.setattr("asyncio.set_event_loop", set_event_loop)

    assert tasks._get_event_loop() is (replacement if closed else current)
    assert new_event_loop.call_count == int(closed)
    assert set_event_loop.call_count == int(closed)


def test_get_event_loop_recovers_when_none_is_configured(monkeypatch):
    replacement = Mock()
    monkeypatch.setattr(
        "asyncio.get_event_loop", Mock(side_effect=RuntimeError("no current loop"))
    )
    monkeypatch.setattr("asyncio.new_event_loop", Mock(return_value=replacement))
    set_event_loop = Mock()
    monkeypatch.setattr("asyncio.set_event_loop", set_event_loop)

    assert tasks._get_event_loop() is replacement
    set_event_loop.assert_called_once_with(replacement)


@pytest.mark.asyncio
async def test_load_notification_context_handles_missing_and_scoped_lookups(
    monkeypatch,
):
    notification_id = uuid4()
    notification_filter = Mock(return_value=_query(None))
    monkeypatch.setattr(tasks.Notification, "filter", notification_filter)
    site_name = AsyncMock(return_value="Configured Site")
    monkeypatch.setattr(tasks.SiteSetting, "get_value", site_name)

    assert await tasks._load_notification_context(notification_id) is None
    site_name.assert_not_awaited()

    team = SimpleNamespace(name="Platform")
    team_notification = _notification(NotificationScope.TEAM, team_id=uuid4())
    notification_filter.return_value = _query(team_notification)
    team_filter = Mock(return_value=_query(team))
    user_filter = Mock()
    monkeypatch.setattr(tasks.Team, "filter", team_filter)
    monkeypatch.setattr(tasks.User, "filter", user_filter)

    context = await tasks._load_notification_context(notification_id)

    assert context == tasks.NotificationContext(
        notification=team_notification, site_name="Configured Site", team=team
    )
    site_name.assert_awaited_once_with("site_name", "Clouisle")
    team_filter.assert_called_once_with(id=team_notification.team_id)
    user_filter.assert_not_called()

    user = SimpleNamespace(username="alice")
    user_notification = _notification(NotificationScope.USER, user_id=uuid4())
    notification_filter.return_value = _query(user_notification)
    user_filter.return_value = _query(user)

    context = await tasks._load_notification_context(notification_id)

    assert context == tasks.NotificationContext(
        notification=user_notification, site_name="Configured Site", user=user
    )
    user_filter.assert_called_once_with(id=user_notification.user_id)


@pytest.mark.asyncio
async def test_update_delivery_status_applies_failure_and_success_fields(monkeypatch):
    delivery = SimpleNamespace(
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=1,
        sent_at=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        tasks.NotificationDelivery, "filter", Mock(return_value=_query(delivery))
    )
    sent_at = object()
    monkeypatch.setattr(tasks, "now_utc", Mock(return_value=sent_at))
    notification_id = uuid4()

    await tasks._update_delivery_status(
        notification_id,
        NotificationChannel.SLACK,
        NotificationDeliveryStatus.FAILED,
        "provider failed",
    )
    assert delivery.status == NotificationDeliveryStatus.FAILED
    assert delivery.error_message == "provider failed"
    assert delivery.retry_count == 2

    await tasks._update_delivery_status(
        notification_id,
        NotificationChannel.SLACK,
        NotificationDeliveryStatus.SUCCESS,
    )
    assert delivery.status == NotificationDeliveryStatus.SUCCESS
    assert delivery.sent_at is sent_at
    assert delivery.save.await_count == 2


_PROVIDER_CASES = [
    (
        "_send_notification_dingtalk",
        "send_dingtalk_notification",
        NotificationChannel.DINGTALK,
        "zh",
    ),
    (
        "_send_notification_wechat",
        "send_wechat_notification",
        NotificationChannel.WECHAT,
        "zh",
    ),
    (
        "_send_notification_feishu",
        "send_feishu_notification",
        NotificationChannel.FEISHU,
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
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sender_name", "provider_name", "channel", "locale"), _PROVIDER_CASES
)
async def test_external_channel_dispatches_and_marks_success(
    monkeypatch, sender_name, provider_name, channel, locale
):
    notification_id = uuid4()
    item = _notification()
    context = tasks.NotificationContext(item, "Configured Site")
    monkeypatch.setattr(
        tasks, "_load_notification_context", AsyncMock(return_value=context)
    )
    update_status = AsyncMock()
    monkeypatch.setattr(tasks, "_update_delivery_status", update_status)
    build_message = Mock(return_value=("Rendered title", "Rendered content"))
    monkeypatch.setattr(tasks, "_build_notification_message", build_message)
    provider = AsyncMock(return_value=True)
    monkeypatch.setattr(tasks, provider_name, provider)

    assert await getattr(tasks, sender_name)(notification_id) is True

    build_message.assert_called_once_with(context, locale)
    provider.assert_awaited_once_with(
        title="Rendered title",
        content="Rendered content",
        link_url=item.link_url,
    )
    assert update_status.await_args_list[0].args == (
        notification_id,
        channel,
        NotificationDeliveryStatus.SENDING,
    )
    assert update_status.await_args_list[1].args == (
        notification_id,
        channel,
        NotificationDeliveryStatus.SUCCESS,
    )


@pytest.mark.asyncio
async def test_external_channel_stops_before_provider_without_context(monkeypatch):
    notification_id = uuid4()
    monkeypatch.setattr(
        tasks, "_load_notification_context", AsyncMock(return_value=None)
    )
    update_status = AsyncMock()
    monkeypatch.setattr(tasks, "_update_delivery_status", update_status)
    provider = AsyncMock()
    monkeypatch.setattr(tasks, "send_slack_notification", provider)

    with pytest.raises(ValueError, match="notification_not_found"):
        await tasks._send_notification_slack(notification_id)

    provider.assert_not_awaited()
    update_status.assert_awaited_once_with(
        notification_id,
        NotificationChannel.SLACK,
        NotificationDeliveryStatus.SENDING,
    )


@pytest.mark.asyncio
async def test_external_channel_propagates_provider_failure(monkeypatch):
    notification_id = uuid4()
    item = _notification()
    monkeypatch.setattr(
        tasks,
        "_load_notification_context",
        AsyncMock(return_value=tasks.NotificationContext(item, "Configured Site")),
    )
    monkeypatch.setattr(tasks, "_update_delivery_status", AsyncMock())
    provider = AsyncMock(return_value=False)
    monkeypatch.setattr(tasks, "send_webhook_notification", provider)

    with pytest.raises(RuntimeError, match="webhook_send_failed"):
        await tasks._send_notification_webhook(notification_id)

    provider.assert_awaited_once()
