from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.models.im import (
    ImConversation,
    ImConversationParticipant,
    ImConversationType,
    ImMessage,
    ImMessageStatus,
    ImMessageType,
)
from app.models.notification import Notification, NotificationRead, NotificationScope
from app.models.user import TeamMember
from app.services import im_redis

logger = logging.getLogger(__name__)


async def bridge_notification_to_im(notification: Notification) -> None:
    """将现有系统自动通知/审批流事件桥接投递到 IM 系统通知流中。"""
    from app.services import im_service

    try:
        content = notification.content or ""
        if notification.title and notification.title not in content:
            content = f"**{notification.title}**\n\n{content}"

        msg_type = (
            ImMessageType.CARD
            if "pause" in notification.type or "approval" in notification.type
            else ImMessageType.SYSTEM_NOTICE
        )

        payload: dict[str, Any] = {
            "notification_id": str(notification.id),
            "type": notification.type,
            "level": notification.level.value
            if hasattr(notification.level, "value")
            else str(notification.level),
            "link_url": notification.link_url,
            "data": notification.data or {},
        }

        if notification.scope == NotificationScope.USER and notification.user_id:
            team_id = notification.team_id
            if not team_id:
                tm = await TeamMember.filter(user_id=notification.user_id).first()
                if tm:
                    team_id = tm.team_id

            if team_id:
                await im_service.send_system_message(
                    team_id=team_id,
                    recipient_user_id=notification.user_id,
                    content=content,
                    msg_type=msg_type,
                    payload=payload,
                    client_msg_id=f"notif-bridge-{notification.id}-{notification.user_id}",
                )

        elif notification.scope == NotificationScope.TEAM and notification.team_id:
            members = await TeamMember.filter(team_id=notification.team_id).values_list(
                "user_id", flat=True
            )

            for uid in members:
                try:
                    await im_service.send_system_message(
                        team_id=notification.team_id,
                        recipient_user_id=uid,
                        content=content,
                        msg_type=msg_type,
                        payload=payload,
                        client_msg_id=f"notif-bridge-{notification.id}-{uid}",
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to bridge notification to user %s: %s", uid, exc
                    )

    except Exception as exc:
        logger.warning(
            "bridge_notification_to_im failed for notification %s: %s",
            getattr(notification, "id", None),
            exc,
        )


async def sync_legacy_notifications_for_user(team_id: UUID, user_id: UUID) -> None:
    """按需平滑将历史 Notification 数据无感同步回填到该用户的系统通知 IM 会话中。

    用户初次打开消息中心时，旧系统的历史公告与待办审批完整平滑呈现，
    且其历史已读状态完整保留。
    """
    try:
        conv = await ImConversation.filter(
            team_id=team_id,
            type=ImConversationType.SYSTEM,
            user1_id=user_id,
        ).first()
        if not conv:
            return

        has_existing = await ImMessage.filter(conversation_id=conv.id).exists()
        if has_existing:
            return

        lock = im_redis.DistributedLock(
            f"im:lock:sync_legacy_notifs:{user_id}", lease_seconds=15
        )
        async with lock:
            if await ImMessage.filter(conversation_id=conv.id).exists():
                return

            base_query = (
                Q(scope=NotificationScope.GLOBAL)
                | Q(scope=NotificationScope.USER, user_id=user_id)
                | Q(scope=NotificationScope.TEAM, team_id=team_id)
            )
            notifs = (
                await Notification.filter(base_query)
                .order_by("created_at")
                .limit(100)
                .all()
            )
            if not notifs:
                return

            read_ids = set(
                await NotificationRead.filter(user_id=user_id).values_list(
                    "notification_id", flat=True
                )
            )

            max_read_seq = 0
            latest_seq = 0
            last_content = ""
            last_time = None

            async with in_transaction():
                for idx, n in enumerate(notifs, start=1):
                    seq = idx
                    latest_seq = seq
                    content = n.content or ""
                    if n.title and n.title not in content:
                        content = f"**{n.title}**\n\n{content}"

                    is_card = "pause" in n.type or "approval" in n.type
                    msg_type = (
                        ImMessageType.CARD if is_card else ImMessageType.SYSTEM_NOTICE
                    )

                    payload = {
                        "notification_id": str(n.id),
                        "type": n.type,
                        "level": n.level.value
                        if hasattr(n.level, "value")
                        else str(n.level),
                        "link_url": n.link_url,
                        "data": n.data or {},
                    }

                    await ImMessage.create(
                        conversation_id=conv.id,
                        sender_id=None,
                        client_msg_id=f"legacy-notif-{n.id}",
                        seq=seq,
                        msg_type=msg_type,
                        content=content,
                        payload=payload,
                        status=ImMessageStatus.NORMAL,
                    )

                    if n.id in read_ids:
                        max_read_seq = seq

                    from app.services.im_service import _strip_markdown_summary

                    last_content = _strip_markdown_summary(content, 200)
                    last_time = n.created_at

                conv.latest_seq = latest_seq
                conv.last_message_content = last_content
                conv.last_message_at = last_time
                await conv.save(
                    update_fields=[
                        "latest_seq",
                        "last_message_content",
                        "last_message_at",
                        "updated_at",
                    ]
                )

                participant = await ImConversationParticipant.filter(
                    conversation_id=conv.id, user_id=user_id
                ).first()
                if participant:
                    participant.last_read_seq = max_read_seq
                    await participant.save(
                        update_fields=["last_read_seq", "updated_at"]
                    )

                unread_count = max(latest_seq - max_read_seq, 0)
                if unread_count > 0:
                    await im_redis.increment_user_unread(user_id, conv.id, unread_count)

    except Exception as exc:
        logger.warning(
            "sync_legacy_notifications_for_user failed for user %s team %s: %s",
            user_id,
            team_id,
            exc,
        )
