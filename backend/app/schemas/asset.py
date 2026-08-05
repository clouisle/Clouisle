"""Schemas shared by Asset-aware chat, Sandbox, and workflow boundaries."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.asset import AssetSource, AssetStatus

AssetCapability = Literal["inspect", "read", "parse", "vision", "generate", "sandbox"]


class AssetRef(BaseModel):
    asset_id: UUID
    ref: str | None = Field(default=None, pattern=r"^[0-9a-f]{4}$")


class AssetCapabilities(BaseModel):
    inspect: bool = True
    read: bool = False
    parse: bool = False
    vision: bool = False
    generate: bool = False
    sandbox: bool = False


class AssetInfo(BaseModel):
    id: UUID
    original_filename: str
    display_filename: str
    content_type: str
    size: int
    checksum: str
    source: AssetSource
    status: AssetStatus
    parent_id: UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
