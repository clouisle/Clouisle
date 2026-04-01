from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.notification import (
    NotificationScope,
    NotificationSource,
    NotificationLevel,
    NotificationStatus,
    NotificationChannel,
    NotificationDeliveryStatus,
)


class NotificationDeliveryOut(BaseModel):
    """通知发送状态"""

    channel: NotificationChannel
    status: NotificationDeliveryStatus
    error_message: Optional[str] = None
    retry_count: int = 0
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationOut(BaseModel):
    id: UUID
    scope: NotificationScope
    team_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    type: str
    source: NotificationSource
    title: str
    content: str
    level: NotificationLevel
    data: Optional[dict] = None
    link_url: Optional[str] = None
    status: NotificationStatus
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    is_read: bool = False
    read_at: Optional[datetime] = None
    deliveries: list[NotificationDeliveryOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class NotificationAdminCreate(BaseModel):
    scope: NotificationScope
    team_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    user_ids: Optional[list[UUID]] = None  # 批量发送给多个用户
    type: str = Field(..., min_length=1, max_length=100)
    source: NotificationSource = NotificationSource.SYSTEM
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    level: NotificationLevel = NotificationLevel.MEDIUM
    data: Optional[dict] = None
    link_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    notify_channels: list[NotificationChannel] = Field(default_factory=list)


class NotificationReadRequest(BaseModel):
    notification_ids: Optional[list[UUID]] = None
    mark_all: bool = False


class NotificationUnreadCount(BaseModel):
    total: int
