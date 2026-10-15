from unittest.mock import AsyncMock, Mock

import pytest

from app.integrations.factory import (
    EmailNotificationIntegration,
    FeishuNotificationIntegration,
    NotificationMessage,
    WebhookNotificationIntegration,
    get_notification_integration,
    dispatch_notification_task,
)
from app.models.notification import NotificationChannel


def test_notification_resolution_requires_catalog_capability():
    assert get_notification_integration("email").id == NotificationChannel.EMAIL
    assert get_notification_integration("webhook").id == NotificationChannel.WEBHOOK
    assert get_notification_integration("feishu").id == NotificationChannel.FEISHU
    for integration_id in ("unknown", "dingtalk", "wechat", "slack", "oidc"):
        with pytest.raises(ValueError):
            get_notification_integration(integration_id)


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
        dispatch_notification_task(NotificationChannel.EMAIL, "notification-email").id
        == "email-id"
    )
    assert (
        dispatch_notification_task(
            NotificationChannel.WEBHOOK, "notification-webhook"
        ).id
        == "webhook-id"
    )
    email_delay.assert_called_once_with("notification-email")
    webhook_delay.assert_called_once_with("notification-webhook")


@pytest.mark.asyncio
async def test_feishu_notification_requires_enabled_capability_and_credentials(
    monkeypatch,
):
    from types import SimpleNamespace

    from app.integrations.registry import IntegrationCapability
    from app.services import integration_config

    integration = SimpleNamespace(
        is_enabled=True,
        enabled_capabilities=[IntegrationCapability.NOTIFICATION],
        config={"app_id": "cli_test"},
        credentials={"app_secret": "encrypted"},
    )
    monkeypatch.setattr(
        integration_config,
        "get_builtin_integration",
        AsyncMock(return_value=integration),
    )
    handler = FeishuNotificationIntegration()
    assert await handler.is_enabled()
    assert await handler.validate_configuration() is None

    integration.enabled_capabilities = []
    assert await handler.validate_configuration() == "feishu_notification_not_enabled"
    integration.enabled_capabilities = [IntegrationCapability.NOTIFICATION]
    integration.credentials = {}
    assert (
        await handler.validate_configuration() == "feishu_notification_not_configured"
    )


def test_factory_dispatches_feishu_notification_task(monkeypatch):
    from app.tasks import notification as tasks

    delay = Mock(return_value=type("TaskResult", (), {"id": "feishu-id"})())
    monkeypatch.setattr(tasks.send_notification_feishu_task, "delay", delay)
    assert (
        dispatch_notification_task(NotificationChannel.FEISHU, "notification-feishu").id
        == "feishu-id"
    )
    delay.assert_called_once_with("notification-feishu")
