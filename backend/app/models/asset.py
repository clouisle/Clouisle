"""Durable uploaded and generated file assets."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.agent import Message
    from app.models.user import Team, User


class AssetSource(str, Enum):
    UPLOAD = "upload"
    GENERATED_MEDIA = "generated_media"
    SANDBOX_ARTIFACT = "sandbox_artifact"
    WORKFLOW_OUTPUT = "workflow_output"


class AssetStatus(str, Enum):
    AVAILABLE = "available"
    DELETED = "deleted"
    EXPIRED = "expired"
    FAILED = "failed"


class AssetScopeType(str, Enum):
    CONVERSATION = "conversation"
    WORKFLOW_RUN = "workflow_run"


class Asset(models.Model):
    """Raw stored content and its durable metadata."""

    id = fields.UUIDField(primary_key=True)
    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="assets",
        on_delete=fields.CASCADE,
        null=True,
    )
    team_id: UUID | None  # type: ignore[assignment]
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_assets",
        on_delete=fields.SET_NULL,
        null=True,
    )
    created_by_id: UUID | None  # type: ignore[assignment]
    parent: fields.ForeignKeyRelation["Asset"] | None = fields.ForeignKeyField(
        "models.Asset",
        related_name="derived_assets",
        on_delete=fields.SET_NULL,
        null=True,
    )
    parent_id: UUID | None  # type: ignore[assignment]

    storage_key = fields.CharField(max_length=1000, unique=True)
    original_filename = fields.CharField(max_length=500)
    display_filename = fields.CharField(max_length=500)
    content_type = fields.CharField(max_length=255)
    size = fields.BigIntField()
    checksum = fields.CharField(max_length=64)
    source = fields.CharEnumField(AssetSource)
    status = fields.CharEnumField(AssetStatus, default=AssetStatus.AVAILABLE)
    provenance: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    expires_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    message_links: fields.ReverseRelation["MessageAsset"]
    scope_refs: fields.ReverseRelation["AssetScopeRef"]

    class Meta:
        table = "assets"
        indexes = (("team", "status", "created_at"), ("checksum",))


class MessageAsset(models.Model):
    """An Asset attached to or produced by a chat message."""

    id = fields.UUIDField(primary_key=True)
    message: fields.ForeignKeyRelation["Message"] = fields.ForeignKeyField(
        "models.Message",
        related_name="asset_links",
        on_delete=fields.CASCADE,
    )
    message_id: UUID  # type: ignore[assignment]
    asset: fields.ForeignKeyRelation[Asset] = fields.ForeignKeyField(
        "models.Asset",
        related_name="message_links",
        on_delete=fields.CASCADE,
    )
    asset_id: UUID  # type: ignore[assignment]
    role = fields.CharField(
        max_length=30,
        default="attachment",
        description="attachment, generated, sandbox_output, or selected_reference",
    )
    position = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "message_assets"
        unique_together = (("message", "asset", "role"),)
        ordering = ["position", "created_at"]


class AssetScopeRef(models.Model):
    """Compact model-facing reference unique inside one execution scope."""

    id = fields.UUIDField(primary_key=True)
    scope_type = fields.CharEnumField(AssetScopeType)
    scope_id = fields.UUIDField()
    asset: fields.ForeignKeyRelation[Asset] = fields.ForeignKeyField(
        "models.Asset",
        related_name="scope_refs",
        on_delete=fields.CASCADE,
    )
    asset_id: UUID  # type: ignore[assignment]
    ref = fields.CharField(max_length=4)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "asset_scope_refs"
        unique_together = (
            ("scope_type", "scope_id", "asset"),
            ("scope_type", "scope_id", "ref"),
        )
        indexes = (("scope_type", "scope_id"),)
