"""Configured external connection with independently enabled capabilities."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import User


class Integration(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    name = fields.CharField(max_length=100, unique=True)
    provider_type = fields.CharField(max_length=20)
    display_name = fields.CharField(max_length=100)
    icon_url = fields.CharField(max_length=512, null=True)
    button_text = fields.CharField(max_length=50, null=True)
    is_enabled = fields.BooleanField(default=True)
    enabled_capabilities: list[str] = fields.JSONField(default=list)
    config: dict = fields.JSONField(default=dict)
    credentials: dict = fields.JSONField(default=dict)
    login_config: dict = fields.JSONField(default=dict)
    attribute_mapping: dict = fields.JSONField(default=dict)
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_integrations",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "integrations"

    def __str__(self):
        return self.name
