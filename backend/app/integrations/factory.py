"""Notification behavior handlers resolved through the unified capability catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.notification import NotificationChannel
from app.integrations.registry import IntegrationCapability, integration_registry


@dataclass(frozen=True)
class NotificationMessage:
    """Provider-neutral message with optional email-specific fields."""

    title: str
    content: str
    link_url: str | None = None
    recipient: str | None = None
    html_content: str | None = None
    link_label: str | None = None


class NotificationIntegration(Protocol):
    """Contract implemented by active notification delivery integrations."""

    id: NotificationChannel
    not_enabled_message_key: str
    not_configured_message_key: str

    async def is_enabled(self) -> bool: ...

    async def validate_configuration(self) -> str | None: ...

    async def send(self, message: NotificationMessage) -> bool: ...

    def dispatch_task(self, notification_id: str) -> object: ...


class EmailNotificationIntegration:
    id = NotificationChannel.EMAIL
    not_enabled_message_key = "smtp_not_enabled"
    not_configured_message_key = "smtp_not_configured"

    async def is_enabled(self) -> bool:
        from app.core.email import get_smtp_config

        return bool((await get_smtp_config()).get("enabled"))

    async def validate_configuration(self) -> str | None:
        from app.core.email import get_smtp_config

        config = await get_smtp_config()
        if not config.get("enabled"):
            return self.not_enabled_message_key
        if not config.get("host") or not config.get("from_address"):
            return self.not_configured_message_key
        return None

    async def send(self, message: NotificationMessage) -> bool:
        from app.core.email import send_email

        if message.recipient is None:
            raise ValueError("Email integration requires a recipient")
        return await send_email(
            message.recipient,
            message.title,
            message.content,
            message.html_content,
        )

    def dispatch_task(self, notification_id: str):
        from app.tasks.notification import send_notification_email_task

        return send_notification_email_task.delay(notification_id)


class WebhookNotificationIntegration:
    id = NotificationChannel.WEBHOOK
    not_enabled_message_key = "webhook_not_enabled"
    not_configured_message_key = "webhook_not_configured"

    async def is_enabled(self) -> bool:
        from app.core.webhook import get_webhook_config

        return bool((await get_webhook_config()).get("enabled"))

    async def validate_configuration(self) -> str | None:
        from app.core.webhook import get_webhook_config

        config = await get_webhook_config()
        if not config.get("enabled"):
            return self.not_enabled_message_key
        if not config.get("url"):
            return self.not_configured_message_key
        return None

    async def send(self, message: NotificationMessage) -> bool:
        from app.core.webhook import send_webhook_notification

        return await send_webhook_notification(
            message.title, message.content, message.link_url
        )

    def dispatch_task(self, notification_id: str):
        from app.tasks.notification import send_notification_webhook_task

        return send_notification_webhook_task.delay(notification_id)


class FeishuNotificationIntegration:
    id = NotificationChannel.FEISHU
    not_enabled_message_key = "feishu_notification_not_enabled"
    not_configured_message_key = "feishu_notification_not_configured"

    async def is_enabled(self) -> bool:
        from app.services.integration_config import get_builtin_integration

        integration = await get_builtin_integration("feishu")
        return (
            integration.is_enabled
            and IntegrationCapability.NOTIFICATION in integration.enabled_capabilities
        )

    async def validate_configuration(self) -> str | None:
        from app.services.integration_config import get_builtin_integration

        try:
            integration = await get_builtin_integration("feishu")
        except ValueError:
            return self.not_configured_message_key
        if (
            not integration.is_enabled
            or IntegrationCapability.NOTIFICATION
            not in integration.enabled_capabilities
        ):
            return self.not_enabled_message_key
        if not integration.config.get("app_id") or not integration.credentials.get(
            "app_secret"
        ):
            return self.not_configured_message_key
        return None

    async def send(self, message: NotificationMessage) -> bool:
        if message.recipient is None:
            raise ValueError("Feishu integration requires a recipient")
        return await _send_feishu_message(
            message.recipient,
            message.title,
            message.content,
            message.link_url,
            message.link_label,
        )

    def dispatch_task(self, notification_id: str):
        from app.tasks.notification import send_notification_feishu_task

        return send_notification_feishu_task.delay(notification_id)


async def _send_feishu_message(
    recipient: str,
    title: str,
    content: str,
    link_url: str | None = None,
    link_label: str | None = None,
) -> bool:
    from app.integrations.feishu import FeishuClient
    from app.services.integration_config import get_builtin_integration

    integration = await get_builtin_integration("feishu")
    client = FeishuClient(
        integration.config["app_id"], integration.credentials["app_secret"]
    )
    await client.send_user_message(recipient, title, content, link_url, link_label)
    return True


_email_handler = EmailNotificationIntegration()
_webhook_handler = WebhookNotificationIntegration()
_feishu_handler = FeishuNotificationIntegration()


def get_notification_integration(
    provider_type: NotificationChannel | str,
) -> NotificationIntegration:
    definition = integration_registry.get(provider_type)
    if IntegrationCapability.NOTIFICATION not in definition.capabilities:
        raise ValueError(f"Integration does not support notifications: {provider_type}")
    if definition.provider_type == "email":
        return _email_handler
    if definition.provider_type == "webhook":
        return _webhook_handler
    if definition.provider_type == "feishu":
        return _feishu_handler
    raise ValueError(f"No notification handler for integration: {provider_type}")


def dispatch_notification_task(
    provider_type: NotificationChannel | str, notification_id: str
):
    return get_notification_integration(provider_type).dispatch_task(notification_id)
