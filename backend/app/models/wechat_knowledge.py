"""Personal WeChat connections, optional collection settings and durable receipts."""

from uuid import UUID, uuid4

from tortoise import fields, models
from tortoise.timezone import now


class WeChatKnowledgeBinding(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    user = fields.ForeignKeyField(
        "models.User", related_name="wechat_bindings", on_delete=fields.CASCADE
    )
    user_id: UUID
    wechat_user_id = fields.CharField(max_length=255, unique=True)
    bot_id = fields.CharField(max_length=255, unique=True)
    token = fields.TextField()
    base_url = fields.CharField(max_length=512)
    cursor = fields.TextField(default="")
    generation = fields.UUIDField(default=uuid4)
    status = fields.CharField(max_length=20, default="connected")
    purpose = fields.CharField(max_length=24, default="none")
    last_error = fields.TextField(null=True)
    last_received_at = fields.DatetimeField(null=True)
    disconnected_at = fields.DatetimeField(null=True)
    poll_next_at = fields.DatetimeField(default=now)
    poll_claim = fields.UUIDField(null=True)
    poll_claim_expires_at = fields.DatetimeField(null=True)
    agent_recovery_at = fields.DatetimeField(default=now)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "wechat_knowledge_bindings"


class WeChatPollBatch(models.Model):
    """Fixed reusable slots bound queued/running polling batches globally."""

    id = fields.IntField(primary_key=True)
    claim = fields.UUIDField(null=True)
    expires_at = fields.DatetimeField(null=True)
    started = fields.BooleanField(default=False)
    bindings: list[dict] = fields.JSONField(default=list)

    class Meta:
        table = "wechat_poll_batches"


class WeChatKnowledgeCollection(models.Model):
    """Optional knowledge collection configuration for an authorized connection."""

    id = fields.UUIDField(primary_key=True, default=uuid4)
    binding = fields.OneToOneField(
        "models.WeChatKnowledgeBinding",
        related_name="collection",
        on_delete=fields.CASCADE,
    )
    binding_id: UUID
    knowledge_base = fields.ForeignKeyField(
        "models.KnowledgeBase",
        related_name="wechat_collections",
        null=True,
        on_delete=fields.SET_NULL,
    )
    knowledge_base_id: UUID | None
    vision_model_id = fields.UUIDField(null=True)
    stt_model_id = fields.UUIDField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "wechat_knowledge_collections"


class WeChatKnowledgeLogin(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    user = fields.ForeignKeyField(
        "models.User", related_name="wechat_logins", on_delete=fields.CASCADE
    )
    user_id: UUID
    qrcode = fields.TextField()
    qrcode_content = fields.TextField()
    base_url = fields.CharField(max_length=512, default="https://ilinkai.weixin.qq.com")
    status = fields.CharField(max_length=32, default="wait")
    expires_at = fields.DatetimeField()
    binding_id = fields.UUIDField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "wechat_knowledge_logins"


class WeChatKnowledgeReceipt(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    binding = fields.ForeignKeyField(
        "models.WeChatKnowledgeBinding",
        related_name="receipts",
        on_delete=fields.CASCADE,
    )
    binding_id: UUID
    user = fields.ForeignKeyField(
        "models.User", related_name="wechat_receipts", on_delete=fields.CASCADE
    )
    user_id: UUID
    knowledge_base = fields.ForeignKeyField(
        "models.KnowledgeBase",
        related_name="wechat_receipts",
        null=True,
        on_delete=fields.SET_NULL,
    )
    knowledge_base_id: UUID | None
    message_id = fields.CharField(max_length=128)
    payload = fields.TextField()
    vision_model_id = fields.UUIDField(null=True)
    stt_model_id = fields.UUIDField(null=True)
    status = fields.CharField(max_length=20, default="pending")
    results: list = fields.JSONField(default=list)
    last_error = fields.TextField(null=True)
    # API acceptance is not proof of delivery to the phone. An ambiguous send is
    # never blindly retried: users can always read the canonical receipt in UI.
    reply_status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    lease_owner = fields.UUIDField(null=True)
    lease_expires_at = fields.DatetimeField(null=True)

    class Meta:
        table = "wechat_knowledge_receipts"
        unique_together = (("binding", "message_id"),)
        indexes = (("status", "updated_at"),)


class WeChatKnowledgeItem(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    receipt = fields.ForeignKeyField(
        "models.WeChatKnowledgeReceipt", related_name="items", on_delete=fields.CASCADE
    )
    receipt_id: UUID
    item_index = fields.IntField()
    document = fields.ForeignKeyField(
        "models.Document",
        related_name="wechat_items",
        null=True,
        on_delete=fields.SET_NULL,
    )
    document_id: UUID | None
    status = fields.CharField(max_length=20, default="pending")
    content_hash = fields.CharField(max_length=64, null=True)
    last_error = fields.TextField(null=True)
    name = fields.CharField(max_length=255, default="")
    original_path = fields.CharField(max_length=512, null=True)

    class Meta:
        table = "wechat_knowledge_items"
        unique_together = (("receipt", "item_index"),)


class WeChatKnowledgeContent(models.Model):
    """A KB-local content claim serializes duplicate submissions by contributors."""

    id = fields.UUIDField(primary_key=True, default=uuid4)
    knowledge_base = fields.ForeignKeyField(
        "models.KnowledgeBase", related_name="wechat_content", on_delete=fields.CASCADE
    )
    knowledge_base_id: UUID
    content_hash = fields.CharField(max_length=64)
    document = fields.ForeignKeyField(
        "models.Document",
        related_name="wechat_content",
        null=True,
        on_delete=fields.SET_NULL,
    )
    document_id: UUID | None
    owner_item_id = fields.UUIDField(null=True)
    lease_expires_at = fields.DatetimeField(null=True)

    class Meta:
        table = "wechat_knowledge_content"
        unique_together = (("knowledge_base", "content_hash"),)
