"""Static registry for built-in notification integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models.notification import NotificationChannel


@dataclass(frozen=True)
class NotificationMessage:
    """Provider-neutral message with optional email-specific fields."""

    title: str
    content: str
    link_url: str | None = None
    recipient: str | None = None
    html_content: str | None = None


class NotificationIntegration(Protocol):
    """Contract implemented by active notification delivery integrations."""

    id: NotificationChannel
    not_enabled_message_key: str
    not_configured_message_key: str

    async def is_enabled(self) -> bool: ...

    async def validate_configuration(self) -> str | None: ...

    async def send(self, message: NotificationMessage) -> bool: ...

    def dispatch_task(self, notification_id: str) -> object: ...


class NotificationIntegrationFactory:
    """Explicit registry for notification integrations and their task dispatch."""

    def __init__(self, integrations: tuple[NotificationIntegration, ...]):
        registry: dict[NotificationChannel, NotificationIntegration] = {}
        for integration in integrations:
            if integration.id in registry:
                raise ValueError(f"Duplicate integration: {integration.id.value}")
            registry[integration.id] = integration
        self._integrations = registry

    def get(self, integration_id: NotificationChannel | str) -> NotificationIntegration:
        try:
            key = NotificationChannel(integration_id)
        except ValueError as exc:
            raise ValueError(
                f"Unknown notification integration: {integration_id}"
            ) from exc
        if key not in self._integrations:
            raise ValueError(f"Unknown notification integration: {key.value}")
        return self._integrations[key]

    def all(self) -> tuple[NotificationIntegration, ...]:
        return tuple(self._integrations.values())

    def dispatch_task(self, integration_id: NotificationChannel, notification_id: str):
        return self.get(integration_id).dispatch_task(notification_id)


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


notification_integration_factory = NotificationIntegrationFactory(
    (EmailNotificationIntegration(), WebhookNotificationIntegration())
)
