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

# 历史通知回填的幂等键前缀：client_msg_id = legacy-notif-<notification_id>
LEGACY_NOTIF_CLIENT_MSG_PREFIX = "legacy-notif-"
# 历史回填单批处理条数，避免一次性加载全部历史通知
LEGACY_NOTIF_BATCH_SIZE = 200


def _bridge_client_msg_id(notification_id: UUID, user_id: UUID) -> str:
    """实时桥接使用的幂等键。"""
    return f"notif-bridge-{notification_id}-{user_id}"


def _legacy_client_msg_id(notification_id: UUID) -> str:
    """历史通知回填使用的幂等键，同一条通知重复回填只会产生一条消息。"""
    return f"{LEGACY_NOTIF_CLIENT_MSG_PREFIX}{notification_id}"


def _build_notification_message(
    notification: Notification,
) -> tuple[str, ImMessageType, dict[str, Any]]:
    """把通知渲染成 IM 消息的内容、类型与 payload（实时桥接与历史回填共用）。"""
    content = notification.content or ""
    if notification.title and notification.title not in content:
        content = f"**{notification.title}**\n\n{content}"

    is_card = "pause" in notification.type or "approval" in notification.type
    msg_type = ImMessageType.CARD if is_card else ImMessageType.SYSTEM_NOTICE
    payload: dict[str, Any] = {
        "notification_id": str(notification.id),
        "type": notification.type,
        "level": notification.level.value
        if hasattr(notification.level, "value")
        else str(notification.level),
        "link_url": notification.link_url,
        "data": notification.data or {},
    }
    return content, msg_type, payload


async def _resolve_notification_team_id(notification: Notification) -> UUID | None:
    """为未携带 team_id 的 USER 通知确定一个确定的投递团队。

    选择规则（保证同一用户每次得到相同结果，不依赖数据库返回顺序）：
    1. 优先用户在 `Team.is_default=True` 团队上的成员关系；
    2. 否则回退到用户最早加入的成员关系（`joined_at` 升序，`id` 兜底）。
    """
    if not notification.user_id:
        return None

    membership = (
        await TeamMember.filter(
            user_id=notification.user_id,
            team__is_default=True,
        )
        .order_by("joined_at", "id")
        .first()
    )
    if membership:
        return membership.team_id

    membership = (
        await TeamMember.filter(user_id=notification.user_id)
        .order_by("joined_at", "id")
        .first()
    )
    return membership.team_id if membership else None


async def bridge_notification_to_im(notification: Notification) -> None:
    """将现有系统自动通知/审批流事件桥接投递到 IM 系统通知流中。"""
    from app.services import im_service

    try:
        content, msg_type, payload = _build_notification_message(notification)

        if notification.scope == NotificationScope.USER and notification.user_id:
            team_id = notification.team_id
            if not team_id:
                team_id = await _resolve_notification_team_id(notification)

            if team_id:
                await im_service.send_system_message(
                    team_id=team_id,
                    recipient_user_id=notification.user_id,
                    content=content,
                    msg_type=msg_type,
                    payload=payload,
                    client_msg_id=_bridge_client_msg_id(
                        notification.id, notification.user_id
                    ),
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

    回填以 ``client_msg_id = legacy-notif-<notification_id>`` 作为幂等键：
    分批扫描全部 GLOBAL/USER/TEAM 历史通知，已导入的通知直接跳过，
    seq 从会话当前 ``latest_seq`` 续写。因此该函数可安全重复执行，
    既不会重复导入，也能补齐首次回填之后新增的历史通知。
    """
    try:
        conv = await ImConversation.filter(
            team_id=team_id,
            type=ImConversationType.SYSTEM,
            user1_id=user_id,
        ).first()
        if not conv:
            return

        # 回填会分多批执行，锁租约需覆盖整个回填过程
        lock = im_redis.DistributedLock(
            f"im:lock:sync_legacy_notifs:{user_id}", lease_seconds=60
        )
        async with lock:
            await _backfill_legacy_notifications(conv, team_id, user_id)

    except Exception as exc:
        logger.warning(
            "sync_legacy_notifications_for_user failed for user %s team %s: %s",
            user_id,
            team_id,
            exc,
        )


async def _backfill_legacy_notifications(
    conv: ImConversation, team_id: UUID, user_id: UUID
) -> None:
    """分页扫描历史通知（按 created_at、id 递增游标），只导入尚未导入的部分。"""
    imported_client_ids = set(
        await ImMessage.filter(
            Q(conversation_id=conv.id),
            Q(client_msg_id__startswith=LEGACY_NOTIF_CLIENT_MSG_PREFIX)
            | Q(client_msg_id__startswith="notif-bridge-"),
        ).values_list("client_msg_id", flat=True)
    )

    read_ids = set(
        await NotificationRead.filter(user_id=user_id).values_list(
            "notification_id", flat=True
        )
    )

    # 实时桥接把无团队的 USER 通知投递到默认/最早团队；回填必须使用同一规则，
    # 否则同一条通知会被导入用户打开的每个团队会话。
    from types import SimpleNamespace

    resolved_team = await _resolve_notification_team_id(
        SimpleNamespace(user_id=user_id, team_id=None, scope=NotificationScope.USER)
    )
    user_scope_query = Q(scope=NotificationScope.USER, user_id=user_id, team_id=team_id)
    if resolved_team == team_id:
        user_scope_query |= Q(
            scope=NotificationScope.USER, user_id=user_id, team_id__isnull=True
        )

    base_query = (
        Q(scope=NotificationScope.GLOBAL)
        | user_scope_query
        | Q(scope=NotificationScope.TEAM, team_id=team_id)
    )

    cursor_created_at = None
    cursor_id = None

    while True:
        page_query = base_query
        if cursor_created_at is not None and cursor_id is not None:
            page_query = page_query & (
                Q(created_at__gt=cursor_created_at)
                | Q(created_at=cursor_created_at, id__gt=cursor_id)
            )

        batch = (
            await Notification.filter(page_query)
            .order_by("created_at", "id")
            .limit(LEGACY_NOTIF_BATCH_SIZE)
            .all()
        )
        if not batch:
            break

        cursor_created_at = batch[-1].created_at
        cursor_id = batch[-1].id

        pending = [
            n
            for n in batch
            if _legacy_client_msg_id(n.id) not in imported_client_ids
            and _bridge_client_msg_id(n.id, user_id) not in imported_client_ids
        ]
        if pending:
            batch_unread = await _import_legacy_notifications(
                conv, user_id, pending, read_ids
            )
            imported_client_ids.update(_legacy_client_msg_id(n.id) for n in pending)
            if batch_unread:
                await im_redis.increment_user_unread(user_id, conv.id, batch_unread)

        if len(batch) < LEGACY_NOTIF_BATCH_SIZE:
            break


async def _import_legacy_notifications(
    conv: ImConversation,
    user_id: UUID,
    notifications: list[Notification],
    read_ids: set[UUID],
) -> int:
    """在会话锁内写入一批历史通知，返回这批新增的未读消息数。"""
    from app.services.im_service import _strip_markdown_summary

    conv_lock = im_redis.get_conversation_lock(conv.id)
    async with conv_lock:
        # 重新读取会话：seq 必须基于最新值续写，避免与并发实时消息冲突
        fresh = await ImConversation.filter(id=conv.id).first() or conv
        next_seq = fresh.latest_seq or 0
        unread_created = 0
        last_content = fresh.last_message_content
        last_time = fresh.last_message_at

        participant = await ImConversationParticipant.filter(
            conversation_id=conv.id, user_id=user_id
        ).first()
        # A single cursor cannot express gaps: only advance across a contiguous
        # run of read messages, and only when the existing history is already
        # fully read up to latest_seq.
        cursor_can_advance = participant is not None and (
            (participant.last_read_seq or 0) >= next_seq
        )
        max_read_seq = participant.last_read_seq if participant else 0

        async with in_transaction():
            for notification in notifications:
                next_seq += 1
                content, msg_type, payload = _build_notification_message(notification)

                await ImMessage.create(
                    conversation_id=conv.id,
                    sender_id=None,
                    client_msg_id=_legacy_client_msg_id(notification.id),
                    seq=next_seq,
                    msg_type=msg_type,
                    content=content,
                    payload=payload,
                    status=ImMessageStatus.NORMAL,
                )

                if cursor_can_advance and notification.id in read_ids:
                    max_read_seq = next_seq
                else:
                    cursor_can_advance = False
                    unread_created += 1

                last_content = _strip_markdown_summary(content, 200)
                last_time = notification.created_at

            conv.latest_seq = next_seq
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

            if participant and max_read_seq > (participant.last_read_seq or 0):
                participant.last_read_seq = max_read_seq
                await participant.save(update_fields=["last_read_seq", "updated_at"])

        await _raise_conversation_seq_counter(conv.id, next_seq)

    return unread_created


async def _raise_conversation_seq_counter(
    conversation_id: UUID, latest_seq: int
) -> None:
    """把 Redis 中的会话 seq 计数器抬到 latest_seq。

    历史回填直接写库、不经过 ``im_redis.generate_next_seq``；若不抬高计数器，
    后续实时消息会从旧计数器继续自增，可能复用已存在的 seq 而违反唯一约束。
    """
    try:
        redis = await im_redis.get_redis()
        key = im_redis.CONV_SEQ_KEY_PREFIX.format(conversation_id)
        current = await redis.get(key)
        if current is None or int(current) < latest_seq:
            await redis.set(key, latest_seq)
    except Exception as exc:
        logger.warning(
            "Failed to bump seq counter for conversation %s: %s", conversation_id, exc
        )
