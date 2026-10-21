"""Durable per-chat Agent sessions, inbound receipts and outbound deliveries.

Each linked user selects their own Agent. Durable chat state remains keyed by
``(integration, chat, user, agent)`` so switching never rebinds existing runs:

* ``FeishuAgentSession`` owns the conversation, the active run and the
  accumulated answers for a waiting ``ask_user`` call,
* ``FeishuAgentReceipt`` is the immutable inbound record: one accepted Feishu
  message maps to at most one ``AgentRun``, enforced by a unique constraint on
  ``(integration, message_id)`` so a replayed provider event never submits a
  second run,
* ``FeishuAgentDelivery`` is the durable outbound queue.  Each row carries a
  deterministic provider dedup ``uuid`` derived from its own identity, so a
  crashed send is retried by recovery without the user seeing a duplicate
  message.
"""

from __future__ import annotations

import uuid

from tortoise import fields, models


class FeishuAgentPreference(models.Model):
    """One user's explicit routing choice; null means no Agent selected."""

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    integration = fields.ForeignKeyField("models.Integration", on_delete=fields.CASCADE)
    integration_id: uuid.UUID
    user = fields.ForeignKeyField("models.User", on_delete=fields.CASCADE)
    user_id: uuid.UUID
    agent = fields.ForeignKeyField("models.Agent", null=True, on_delete=fields.SET_NULL)
    agent_id: uuid.UUID | None
    is_enabled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_agent_preferences"
        unique_together = (("integration", "user"),)


class FeishuAgentSession(models.Model):
    """One user's Agent session inside one Feishu chat.

    Switching the Agent creates a different session row; the previous row
    keeps its conversation and run history so an in-flight run is never
    orphaned by a configuration or selection change.
    """

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    integration = fields.ForeignKeyField(
        "models.Integration",
        related_name="feishu_agent_sessions",
        on_delete=fields.CASCADE,
    )
    integration_id: uuid.UUID
    user = fields.ForeignKeyField(
        "models.User",
        related_name="feishu_agent_sessions",
        on_delete=fields.CASCADE,
    )
    user_id: uuid.UUID
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="feishu_agent_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: uuid.UUID | None
    chat_id = fields.CharField(max_length=128)
    conversation = fields.ForeignKeyField(
        "models.Conversation",
        related_name="feishu_agent_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    conversation_id: uuid.UUID | None
    active_run = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="feishu_agent_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    active_run_id: uuid.UUID | None
    pending_answers: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    pending_tool_call_id = fields.CharField(max_length=200, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_agent_sessions"
        unique_together = (("integration", "chat_id", "user", "agent"),)
        indexes = (("integration", "chat_id", "user"),)


class FeishuAgentReceipt(models.Model):
    """One accepted inbound Feishu message and its durable outcome.

    ``status`` is a small state machine: ``pending`` (accepted, not yet
    processed), ``submitted`` (run created, not terminal), ``completed``
    (consumed: answered, command applied or finalized) and ``error``
    (consumed with an explanation the user already received).  A receipt is
    never mutated back to ``pending``, so recovery can never replay it.
    """

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    integration = fields.ForeignKeyField(
        "models.Integration",
        related_name="feishu_agent_receipts",
        on_delete=fields.CASCADE,
    )
    integration_id: uuid.UUID
    user = fields.ForeignKeyField(
        "models.User",
        related_name="feishu_agent_receipts",
        on_delete=fields.CASCADE,
    )
    user_id: uuid.UUID
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="feishu_agent_receipts",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: uuid.UUID | None
    chat_id = fields.CharField(max_length=128)
    chat_type = fields.CharField(max_length=20, null=True)
    message_id = fields.CharField(max_length=128)
    sender_id = fields.CharField(max_length=128, null=True)
    text = fields.TextField(default="")
    run = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="feishu_agent_receipts",
        null=True,
        on_delete=fields.SET_NULL,
    )
    run_id: uuid.UUID | None
    status = fields.CharField(max_length=20, default="pending")
    error = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_agent_receipts"
        # The provider's message id is the only replay key that survives a
        # crash between envelope validation and receipt creation.
        unique_together = (("integration", "message_id"),)
        indexes = (
            ("status", "created_at"),
            ("integration", "chat_id", "created_at"),
        )
        ordering = ["created_at", "id"]


class FeishuAgentDelivery(models.Model):
    """One outbound Feishu reply, durable until the provider accepted it.

    ``uuid`` is deterministic per row so a retry after a crash is deduplicated
    by Feishu itself instead of reaching the chat twice.  ``status`` values:
    ``pending``, ``sending`` (claimed by one worker), ``sent``, ``error`` and
    ``unavailable`` (the run finished but the reply must not be sent).
    """

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    receipt = fields.ForeignKeyField(
        "models.FeishuAgentReceipt",
        related_name="deliveries",
        on_delete=fields.CASCADE,
    )
    receipt_id: uuid.UUID
    event_key = fields.CharField(max_length=255)
    sequence = fields.IntField()
    uuid = fields.CharField(max_length=50, unique=True)
    text = fields.TextField()
    status = fields.CharField(max_length=20, default="pending")
    error = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_agent_deliveries"
        unique_together = (("receipt", "event_key", "sequence"),)
        indexes = (("status", "created_at"),)
        ordering = ["created_at", "sequence"]


__all__ = [
    "FeishuAgentPreference",
    "FeishuAgentSession",
    "FeishuAgentReceipt",
    "FeishuAgentDelivery",
]
