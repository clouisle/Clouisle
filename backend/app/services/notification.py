from typing import Optional
from uuid import UUID

from app.core.timezone import now_utc
from app.models.notification import (
    Notification,
    NotificationAudit,
    NotificationAuditAction,
)
from app.models.user import User


async def create_notification_audit(
    notification_id: UUID,
    action: NotificationAuditAction,
    user: Optional[User] = None,
    meta: Optional[dict] = None,
) -> NotificationAudit:
    return await NotificationAudit.create(
        notification_id=notification_id,
        user_id=user.id if user else None,
        action=action,
        meta=meta,
        created_at=now_utc(),
    )


async def create_notification(
    notification: Notification,
    actor: Optional[User] = None,
    meta: Optional[dict] = None,
) -> Notification:
    await create_notification_audit(
        notification_id=notification.id,
        action=NotificationAuditAction.CREATE,
        user=actor,
        meta=meta,
    )
    return notification
