"""Durable, administrator-managed Feishu Wiki imports (local KB ACLs apply)."""

from __future__ import annotations

from uuid import UUID, uuid4

from tortoise import fields, models


class FeishuKnowledgeSource(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    knowledge_base = fields.ForeignKeyField(
        "models.KnowledgeBase", related_name="feishu_sources", on_delete=fields.RESTRICT
    )
    knowledge_base_id: UUID
    space_id = fields.CharField(max_length=255)
    name = fields.CharField(max_length=100)
    interval_minutes = fields.IntField(default=60)
    is_enabled = fields.BooleanField(default=True)
    status = fields.CharField(max_length=20, default="idle")
    last_synced_at = fields.DatetimeField(null=True)
    last_error = fields.TextField(null=True)
    last_result: dict = fields.JSONField(default=dict)
    dispatch_token = fields.UUIDField(null=True)
    lease_expires_at = fields.DatetimeField(null=True)
    next_sync_at = fields.DatetimeField(null=True)
    created_by = fields.ForeignKeyField(
        "models.User",
        related_name="feishu_knowledge_sources",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_by_id: UUID | None
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_knowledge_sources"
        unique_together = (("knowledge_base", "space_id"),)
        indexes = (("is_enabled", "next_sync_at"),)
        ordering = ["-created_at"]


class FeishuKnowledgeDocument(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid4)
    source = fields.ForeignKeyField(
        "models.FeishuKnowledgeSource", related_name="imports", on_delete=fields.CASCADE
    )
    source_id: UUID
    obj_type = fields.CharField(max_length=32)
    obj_token = fields.CharField(max_length=255)
    node_token = fields.CharField(max_length=255)
    document = fields.OneToOneField(
        "models.Document",
        related_name="feishu_import",
        null=True,
        on_delete=fields.SET_NULL,
    )
    document_id: UUID | None
    staging_document_id: UUID | None = fields.UUIDField(null=True)
    cleanup_chunk_ids: list = fields.JSONField(default=list)
    content_hash = fields.CharField(max_length=64, null=True)
    pending_file_path = fields.CharField(max_length=512, null=True)
    obsolete_file_path = fields.CharField(max_length=512, null=True)
    last_error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_knowledge_documents"
        unique_together = (("source", "obj_type", "obj_token"),)
