"""Stable tenant-scoped Feishu department to Clouisle team mapping."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team


class FeishuDepartment(models.Model):
    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    department_id = fields.CharField(max_length=255, unique=True)
    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="feishu_department_mapping",
        on_delete=fields.CASCADE,
        unique=True,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "feishu_departments"
