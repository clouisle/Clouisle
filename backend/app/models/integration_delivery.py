"""Provider-neutral durable outbound queue for messaging integrations.

One table serves every messaging integration instead of a delivery table per
provider. ``provider_type`` selects the sender and owns the meaning of
``receipt_id`` (each provider keeps its own inbound receipt table);
``payload`` carries provider-specific send data while the generic columns make
the outcome inspectable in the administrator delivery log.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from tortoise import fields, models


class IntegrationDelivery(models.Model):
    """One outbound provider reply, durable until the provider accepted it.

    ``status`` values: ``pending``, ``sending`` (claimed by one worker),
    ``sent``, ``error``, ``unavailable`` (the run finished but the reply must
    not be sent) and ``unknown`` (a timeout after transmission; never blind
    resent). ``provider_uuid`` is a deterministic provider dedup id where the
    provider supports one; an uploaded asset key is stored before the reply so
    a retry never uploads or attaches a different resource.
    """

    id = fields.UUIDField(primary_key=True, default=uuid4)

    integration = fields.ForeignKeyField(
        "models.Integration",
        related_name="deliveries",
        null=True,
        on_delete=fields.CASCADE,
    )
    integration_id: UUID | None  # type: ignore[assignment]
    provider_type = fields.CharField(max_length=32)

    # The provider's durable inbound receipt. Receipt tables stay
    # provider-specific, so this is an explicit cross-table reference.
    receipt_id = fields.UUIDField()

    user = fields.ForeignKeyField(
        "models.User",
        related_name="integration_deliveries",
        null=True,
        on_delete=fields.CASCADE,
    )
    user_id: UUID | None  # type: ignore[assignment]
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="integration_deliveries",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: UUID | None  # type: ignore[assignment]
    run = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="integration_deliveries",
        null=True,
        on_delete=fields.SET_NULL,
    )
    run_id: UUID | None  # type: ignore[assignment]
    chat_id = fields.CharField(max_length=128, null=True)
    message_id = fields.CharField(max_length=128, null=True)

    event_key = fields.CharField(max_length=255)
    sequence = fields.IntField()
    provider_uuid = fields.CharField(max_length=50, null=True, unique=True)

    kind = fields.CharField(max_length=20, default="text")
    text = fields.TextField(default="")
    payload: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    asset_id = fields.UUIDField(null=True)
    filename = fields.CharField(max_length=500, null=True)
    content_type = fields.CharField(max_length=255, null=True)
    size = fields.BigIntField(null=True)
    media_type = fields.CharField(max_length=20, null=True)
    media_key = fields.CharField(max_length=255, null=True)

    status = fields.CharField(max_length=20, default="pending")
    error = fields.TextField(null=True)
    # The provider's own failure text/code, kept next to the stable key.
    error_detail = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "integration_deliveries"
        unique_together = (("provider_type", "receipt_id", "event_key", "sequence"),)
        indexes = (
            ("status", "created_at"),
            ("provider_type", "created_at"),
            ("run", "created_at"),
        )
        ordering = ["created_at", "sequence"]


__all__ = ["IntegrationDelivery"]
