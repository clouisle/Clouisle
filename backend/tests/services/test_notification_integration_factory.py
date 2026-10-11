from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations.factory import (
    EmailNotificationIntegration,
    NotificationIntegrationFactory,
    NotificationMessage,
    WebhookNotificationIntegration,
    notification_integration_factory,
)
from app.models.notification import NotificationChannel


def test_factory_registers_only_active_delivery_channels():
    assert [item.id for item in notification_integration_factory.all()] == [
        NotificationChannel.EMAIL,
        NotificationChannel.WEBHOOK,
    ]


def test_factory_fails_closed_for_unregistered_integrations():
    for integration_id in ("unknown", "dingtalk", "wechat", "feishu", "slack"):
        with pytest.raises(ValueError, match="Unknown notification integration"):
            notification_integration_factory.get(integration_id)


def test_factory_rejects_duplicate_ids():
    integration = EmailNotificationIntegration()
    with pytest.raises(ValueError, match="Duplicate integration"):
        NotificationIntegrationFactory((integration, integration))


@pytest.mark.asyncio
async def test_email_integration_checks_enabled_and_required_configuration(monkeypatch):
    from app.core import email

    get_config = AsyncMock(return_value={"enabled": False})
    monkeypatch.setattr(email, "get_smtp_config", get_config)
    integration = EmailNotificationIntegration()

    assert not await integration.is_enabled()
    assert await integration.validate_configuration() == "smtp_not_enabled"

    get_config.return_value = {
        "enabled": True,
        "host": "smtp.example.test",
        "from_address": "notifications@example.test",
    }
    assert await integration.is_enabled()
    assert await integration.validate_configuration() is None


@pytest.mark.asyncio
async def test_webhook_integration_checks_enabled_and_required_configuration(
    monkeypatch,
):
    from app.core import webhook

    get_config = AsyncMock(return_value={"enabled": False})
    monkeypatch.setattr(webhook, "get_webhook_config", get_config)
    integration = WebhookNotificationIntegration()

    assert not await integration.is_enabled()
    assert await integration.validate_configuration() == "webhook_not_enabled"

    get_config.return_value = {"enabled": True, "url": ""}
    assert await integration.validate_configuration() == "webhook_not_configured"
    get_config.return_value = {"enabled": True, "url": "https://example.test/hook"}
    assert await integration.validate_configuration() is None


@pytest.mark.asyncio
async def test_integrations_keep_provider_specific_wire_senders(monkeypatch):
    from app.core import email, webhook

    send_email = AsyncMock(return_value=True)
    send_webhook = AsyncMock(return_value=True)
    monkeypatch.setattr(email, "send_email", send_email)
    monkeypatch.setattr(webhook, "send_webhook_notification", send_webhook)
    message = NotificationMessage(
        title="Title",
        content="Body",
        link_url="https://example.test/item",
        recipient="user@example.test",
        html_content="<p>Body</p>",
    )

    assert await EmailNotificationIntegration().send(message)
    send_email.assert_awaited_once_with(
        "user@example.test", "Title", "Body", "<p>Body</p>"
    )
    assert await WebhookNotificationIntegration().send(message)
    send_webhook.assert_awaited_once_with("Title", "Body", "https://example.test/item")


def test_factory_dispatches_email_and_webhook_tasks_independently(monkeypatch):
    from app.tasks import notification as tasks

    email_delay = Mock(return_value=type("TaskResult", (), {"id": "email-id"})())
    webhook_delay = Mock(return_value=type("TaskResult", (), {"id": "webhook-id"})())
    monkeypatch.setattr(tasks.send_notification_email_task, "delay", email_delay)
    monkeypatch.setattr(tasks.send_notification_webhook_task, "delay", webhook_delay)

    assert (
        notification_integration_factory.dispatch_task(
            NotificationChannel.EMAIL, "notification-email"
        ).id
        == "email-id"
    )
    assert (
        notification_integration_factory.dispatch_task(
            NotificationChannel.WEBHOOK, "notification-webhook"
        ).id
        == "webhook-id"
    )
    email_delay.assert_called_once_with("notification-email")
    webhook_delay.assert_called_once_with("notification-webhook")
