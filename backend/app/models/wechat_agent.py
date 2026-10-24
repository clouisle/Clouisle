"""Single-Agent configuration, private session mappings and durable receipts."""

from uuid import UUID, uuid4

from tortoise import fields, models


class WeChatAgentConfig(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    binding = fields.OneToOneField(
        "models.WeChatKnowledgeBinding",
        related_name="agent_config",
        on_delete=fields.CASCADE,
    )
    binding_id: UUID
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="wechat_configs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: UUID | None
    variables: dict = fields.JSONField(default=dict)
    stt_model_id = fields.UUIDField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "wechat_agent_configs"


class WeChatAgentSession(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    binding = fields.ForeignKeyField(
        "models.WeChatKnowledgeBinding",
        related_name="agent_sessions",
        on_delete=fields.CASCADE,
    )
    binding_id: UUID
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="wechat_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: UUID | None
    conversation = fields.ForeignKeyField(
        "models.Conversation",
        related_name="wechat_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    conversation_id: UUID | None
    active_run = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="wechat_sessions",
        null=True,
        on_delete=fields.SET_NULL,
    )
    active_run_id: UUID | None
    pending_answers: dict = fields.JSONField(default=dict)
    pending_tool_call_id = fields.CharField(max_length=200, null=True)
    context_token = fields.TextField(default="")
    last_context_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "wechat_agent_sessions"
        unique_together = (("binding", "agent"),)


class WeChatAgentReceipt(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    binding = fields.ForeignKeyField(
        "models.WeChatKnowledgeBinding",
        related_name="agent_receipts",
        on_delete=fields.CASCADE,
    )
    binding_id: UUID
    user = fields.ForeignKeyField(
        "models.User", related_name="wechat_agent_receipts", on_delete=fields.CASCADE
    )
    user_id: UUID
    agent = fields.ForeignKeyField(
        "models.Agent",
        related_name="wechat_receipts",
        null=True,
        on_delete=fields.SET_NULL,
    )
    agent_id: UUID | None
    variables: dict = fields.JSONField(default=dict)
    stt_model_id = fields.UUIDField(null=True)
    message_id = fields.CharField(max_length=128)
    payload = fields.TextField()
    status = fields.CharField(max_length=20, default="pending")
    run = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="wechat_receipts",
        null=True,
        on_delete=fields.SET_NULL,
    )
    run_id: UUID | None
    error = fields.TextField(null=True)
    prepared: dict | None = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "wechat_agent_receipts"
        unique_together = (("binding", "message_id"),)
        indexes = (("status", "created_at"),)
        ordering = ["created_at", "id"]
