"""One-to-one mapping from a local account to a tenant-scoped Feishu user."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import User


class FeishuUser(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="feishu_connection",
        on_delete=fields.CASCADE,
        unique=True,
    )
    feishu_user_id = fields.CharField(max_length=255, unique=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_users"
