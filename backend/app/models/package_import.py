"""Clouisle package import session model."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User


class ClouisleImportSessionStatus(str, Enum):
    PREVIEWED = "previewed"
    INSTALLED = "installed"
    EXPIRED = "expired"
    FAILED = "failed"


class ClouisleImportSource(str, Enum):
    PLATFORM = "platform"
    ADMIN = "admin"


class ClouisleImportSession(models.Model):
    id = fields.UUIDField(pk=True)

    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="clouisle_import_sessions",
        on_delete=fields.CASCADE,
        description="Team that owns this import session",
    )
    team_id: UUID  # type: ignore[assignment]

    resource_type = fields.CharField(max_length=50, description="Package resource type")
    resource_name = fields.CharField(max_length=255, description="Source resource name")
    package_id = fields.UUIDField(description="Package UUID from manifest")
    source = fields.CharEnumField(
        ClouisleImportSource,
        default=ClouisleImportSource.PLATFORM,
        description="Import endpoint context that created this session",
    )
    status = fields.CharEnumField(
        ClouisleImportSessionStatus,
        default=ClouisleImportSessionStatus.PREVIEWED,
        description="Import session status",
    )

    manifest: dict = fields.JSONField(default=dict, description="Parsed manifest")  # type: ignore[assignment]
    resource_payload: dict = fields.JSONField(
        default=dict,
        description="Parsed resource payload",
    )  # type: ignore[assignment]
    preview: dict = fields.JSONField(default=dict, description="Preview result")  # type: ignore[assignment]
    temp_storage_path = fields.CharField(
        max_length=1000,
        null=True,
        description="Temporary staged package path",
    )
    package_checksum = fields.CharField(
        max_length=128,
        null=True,
        description="SHA-256 checksum of uploaded package bytes",
    )
    expires_at = fields.DatetimeField(description="Import session expiry time")

    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_clouisle_import_sessions",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "clouisle_import_sessions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Clouisle import {self.id} ({self.resource_type})"
