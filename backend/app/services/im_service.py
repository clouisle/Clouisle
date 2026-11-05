from __future__ import annotations

import re
import logging
from typing import Any
from uuid import UUID

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.schemas.response import BusinessError, ResponseCode
from app.core.timezone import now_utc
from app.models.im import (
    ImConversation,
    ImConversationParticipant,
    ImConversationType,
    ImMessage,
    ImMessageStatus,
    ImMessageType,
)
from app.models.user import TeamMember, User
from app.services import im_redis

logger = logging.getLogger(__name__)


def _sort_user_pair(u1: UUID, u2: UUID) -> tuple[UUID, UUID]:
    """固定两个用户 UUID 的字典序，防止单聊并发时产生两条交叉的会话记录。"""
    return (u1, u2) if str(u1) < str(u2) else (u2, u1)


def _strip_markdown_summary(text: str, max_length: int = 200) -> str:
    """去除 Markdown 标记符号，返回纯文本摘要。"""
    if not text:
        return ""
    clean = re.sub(r"```[\s\S]*?```", " ", text)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"(\*\*|__)(.*?)\1", r"\2", clean)
    clean = re.sub(r"(\*|_)(.*?)\1", r"\2", clean)
    clean = re.sub(r"~~(.*?)~~", r"\1", clean)
    clean = re.sub(r"^#{1,6}\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\s*>\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_length]


def _ensure_same_asset(existing: ImMessage, asset_id: UUID | None) -> None:
    """幂等重试必须携带同一个附件，避免静默替换。"""
    if existing.asset_id != asset_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="im_attachment_mismatch",
            status_code=400,
        )


async def _resolve_im_attachment(
    conv: ImConversation, asset_id: UUID, msg_type: ImMessageType
) -> Any:
    """校验附件资产属于本会话与团队，且已绑定 IM 会话作用域。"""
    from app.models.asset import Asset, AssetScopeRef, AssetScopeType, AssetStatus

    asset = await Asset.filter(
        id=asset_id, team_id=conv.team_id, status=AssetStatus.AVAILABLE
    ).first()
    if asset is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="file_not_found",
            status_code=404,
        )
    if msg_type == ImMessageType.IMAGE and not (asset.content_type or "").startswith(
        "image/"
    ):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="file_not_found",
            status_code=400,
        )
    bound = await AssetScopeRef.filter(
        asset_id=asset_id,
        scope_type=AssetScopeType.IM_CONVERSATION,
        scope_id=conv.id,
    ).exists()
    if not bound:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="file_not_found",
            status_code=404,
        )
    return asset


async def check_users_in_same_team(team_id: UUID, user_a: UUID, user_b: UUID) -> None:
    """校验两个用户是否同时隶属于指定团队且处于激活状态。"""
    members = await TeamMember.filter(
        team_id=team_id,
        user_id__in=[user_a, user_b],
    ).values_list("user_id", flat=True)

    member_set = set(members)
    if user_a not in member_set or user_b not in member_set:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="team_access_denied",
            status_code=403,
        )


async def get_or_create_direct_conversation(
    team_id: UUID, current_user_id: UUID, target_user_id: UUID
) -> ImConversation:
    """获取或创建同一团队内的单聊会话（带分布式锁与数据库唯一键冲突容灾）。"""
    if current_user_id == target_user_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="cannot_chat_with_self",
            status_code=400,
        )

    await check_users_in_same_team(team_id, current_user_id, target_user_id)
    u1, u2 = _sort_user_pair(current_user_id, target_user_id)

    # 1. 快速读取已有会话
    conv = await ImConversation.filter(
        team_id=team_id,
        type=ImConversationType.DIRECT,
        user1_id=u1,
        user2_id=u2,
    ).first()

    if conv:
        await _ensure_participants(conv.id, [u1, u2])
        return conv

    # 2. 分布式并发创建保护
    lock = im_redis.get_create_conversation_lock(team_id, u1, u2)
    async with lock:
        # 双重校验
        conv = await ImConversation.filter(
            team_id=team_id,
            type=ImConversationType.DIRECT,
            user1_id=u1,
            user2_id=u2,
        ).first()
        if conv:
            await _ensure_participants(conv.id, [u1, u2])
            return conv

        try:
            async with in_transaction():
                conv = await ImConversation.create(
                    team_id=team_id,
                    type=ImConversationType.DIRECT,
                    user1_id=u1,
                    user2_id=u2,
                )
                await ImConversationParticipant.create(
                    conversation_id=conv.id, user_id=u1, is_pinned=False
                )
                await ImConversationParticipant.create(
                    conversation_id=conv.id, user_id=u2, is_pinned=False
                )
            return conv
        except IntegrityError:
            # 并发竞态已由其他节点落库，重新查询返回
            conv = await ImConversation.filter(
                team_id=team_id,
                type=ImConversationType.DIRECT,
                user1_id=u1,
                user2_id=u2,
            ).first()
            if conv:
                await _ensure_participants(conv.id, [u1, u2])
                return conv
            raise


async def get_or_create_system_conversation(
    team_id: UUID, user_id: UUID
) -> ImConversation:
    """获取或初始化用户的团队系统通知专属会话（默认置顶）。"""
    conv = await ImConversation.filter(
        team_id=team_id,
        type=ImConversationType.SYSTEM,
        user1_id=user_id,
    ).first()

    if conv:
        await _ensure_participants(conv.id, [user_id], is_pinned=True)
        return conv

    try:
        async with in_transaction():
            conv = await ImConversation.create(
                team_id=team_id,
                type=ImConversationType.SYSTEM,
                user1_id=user_id,
                user2_id=None,
            )
            await ImConversationParticipant.create(
                conversation_id=conv.id, user_id=user_id, is_pinned=True
            )
        return conv
    except IntegrityError:
        conv = await ImConversation.filter(
            team_id=team_id,
            type=ImConversationType.SYSTEM,
            user1_id=user_id,
        ).first()
        if conv:
            await _ensure_participants(conv.id, [user_id], is_pinned=True)
            return conv
        raise


async def _ensure_participants(
    conversation_id: UUID, user_ids: list[UUID], is_pinned: bool = False
) -> None:
    """防御性保证所有目标用户在参与者表中存在记录。"""
    existing_user_ids = await ImConversationParticipant.filter(
        conversation_id=conversation_id, user_id__in=user_ids
    ).values_list("user_id", flat=True)

    missing = set(user_ids) - set(existing_user_ids)
    for uid in missing:
        try:
            await ImConversationParticipant.create(
                conversation_id=conversation_id, user_id=uid, is_pinned=is_pinned
            )
        except Exception:
            pass


async def send_direct_message(
    conversation_id: UUID,
    sender_id: UUID,
    content: str,
    client_msg_id: str | None = None,
    msg_type: ImMessageType = ImMessageType.TEXT,
    payload: dict | None = None,
    asset_id: UUID | None = None,
) -> ImMessage:
    """发送单聊消息：
    - 分布式会话排他锁保证会话内绝对单调有序、无序号空洞。
    - 分布式幂等去重防重复提交。
    - 异步广播事件至 Redis Pub/Sub 实现跨多实例实时推送。
    """
    conv = await ImConversation.filter(id=conversation_id).first()
    if not conv:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    if conv.type != ImConversationType.DIRECT:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="invalid_conversation_type",
            status_code=400,
        )

    if conv.user1_id != sender_id and conv.user2_id != sender_id:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="conversation_access_denied",
            status_code=403,
        )

    # 1. 快速检查幂等缓存
    if client_msg_id:
        cached_result = await im_redis.get_cached_message_result(client_msg_id)
        if cached_result:
            existing = await ImMessage.filter(id=UUID(cached_result["id"])).first()
            if existing:
                _ensure_same_asset(existing, asset_id)
                return existing

        existing_msg = await ImMessage.filter(
            conversation_id=conversation_id, client_msg_id=client_msg_id
        ).first()
        if existing_msg:
            _ensure_same_asset(existing_msg, asset_id)
            return existing_msg

    # 2. 会话分布式排他锁（单会话多实例写入串行化，保证 seq 严格单调无空洞）
    conv_lock = im_redis.get_conversation_lock(conversation_id)
    async with conv_lock:
        # 二次检查幂等
        if client_msg_id:
            existing_msg = await ImMessage.filter(
                conversation_id=conversation_id, client_msg_id=client_msg_id
            ).first()
            if existing_msg:
                _ensure_same_asset(existing_msg, asset_id)
                return existing_msg

        # 附件资产校验（字节 IO 在锁外完成，此处只做元数据校验）
        asset = None
        if asset_id is not None:
            asset = await _resolve_im_attachment(conv, asset_id, msg_type)

        # 3. 原子生成单调自增序号
        seq = await im_redis.generate_next_seq(conversation_id)

        # 4. 落库单条消息
        msg = await ImMessage.create(
            conversation_id=conversation_id,
            sender_id=sender_id,
            client_msg_id=client_msg_id,
            seq=seq,
            msg_type=msg_type,
            content=content,
            payload=payload,
            asset_id=asset_id,
            status=ImMessageStatus.NORMAL,
        )

        # 5. 更新会话摘要
        if msg_type == ImMessageType.IMAGE:
            summary = "[图片]"
        elif msg_type == ImMessageType.FILE:
            summary = "[文件]"
        else:
            summary = _strip_markdown_summary(content, 200)
        conv.last_message_content = summary
        conv.last_message_at = now_utc()
        conv.latest_seq = seq
        await conv.save(
            update_fields=[
                "last_message_content",
                "last_message_at",
                "latest_seq",
                "updated_at",
            ]
        )

        # 6. 原子增加接收方未读数
        receiver_id = conv.user2_id if conv.user1_id == sender_id else conv.user1_id
        if receiver_id:
            await im_redis.increment_user_unread(receiver_id, conversation_id, 1)

            # 7. 跨实例 Pub/Sub 广播
            msg_dict = {
                "id": str(msg.id),
                "conversation_id": str(conversation_id),
                "sender_id": str(sender_id),
                "client_msg_id": client_msg_id,
                "seq": seq,
                "msg_type": msg_type.value,
                "content": content,
                "payload": payload,
                "asset_id": str(asset_id) if asset_id else None,
                "attachment": (
                    {
                        "asset_id": str(asset.id),
                        "filename": asset.display_filename,
                        "size": asset.size,
                        "content_type": asset.content_type,
                        "url": f"/api/v1/upload/files/{asset.storage_key}",
                    }
                    if asset is not None
                    else None
                ),
                "created_at": msg.created_at.isoformat(),
            }
            await im_redis.publish_im_event(receiver_id, "new_message", msg_dict)

        # 8. 写入幂等结果缓存
        if client_msg_id:
            await im_redis.cache_message_result(
                client_msg_id,
                {
                    "id": str(msg.id),
                    "seq": seq,
                    "created_at": msg.created_at.isoformat(),
                },
                ttl_seconds=60,
            )

        return msg


async def send_system_message(
    team_id: UUID,
    recipient_user_id: UUID,
    content: str,
    msg_type: ImMessageType = ImMessageType.SYSTEM_NOTICE,
    payload: dict | None = None,
    client_msg_id: str | None = None,
) -> ImMessage:
    """向用户的系统通知会话发送系统通知/审批卡片消息（带分布式排它锁与广播）。"""
    conv = await get_or_create_system_conversation(team_id, recipient_user_id)

    if client_msg_id:
        existing = await ImMessage.filter(
            conversation_id=conv.id, client_msg_id=client_msg_id
        ).first()
        if existing:
            return existing

    conv_lock = im_redis.get_conversation_lock(conv.id)
    async with conv_lock:
        if client_msg_id:
            existing = await ImMessage.filter(
                conversation_id=conv.id, client_msg_id=client_msg_id
            ).first()
            if existing:
                return existing

        seq = await im_redis.generate_next_seq(conv.id)

        msg = await ImMessage.create(
            conversation_id=conv.id,
            sender_id=None,
            client_msg_id=client_msg_id,
            seq=seq,
            msg_type=msg_type,
            content=content,
            payload=payload,
            status=ImMessageStatus.NORMAL,
        )

        summary = _strip_markdown_summary(content, 200)
        conv.last_message_content = summary
        conv.last_message_at = now_utc()
        conv.latest_seq = seq
        await conv.save(
            update_fields=[
                "last_message_content",
                "last_message_at",
                "latest_seq",
                "updated_at",
            ]
        )

        await im_redis.increment_user_unread(recipient_user_id, conv.id, 1)

        msg_dict = {
            "id": str(msg.id),
            "conversation_id": str(conv.id),
            "sender_id": None,
            "seq": seq,
            "msg_type": msg_type.value,
            "content": content,
            "payload": payload,
            "created_at": msg.created_at.isoformat(),
        }
        await im_redis.publish_im_event(recipient_user_id, "new_message", msg_dict)

        return msg


async def list_conversations(team_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
    """获取当前用户在指定团队下的所有会话列表（置顶排前，包含未读数与对方信息）。"""
    await get_or_create_system_conversation(team_id, user_id)

    try:
        from app.services.im_system_bridge import sync_legacy_notifications_for_user

        await sync_legacy_notifications_for_user(team_id, user_id)
    except Exception as exc:
        logger.warning(
            "Failed to sync legacy notifications for user %s: %s", user_id, exc
        )

    participants = (
        await ImConversationParticipant.filter(user_id=user_id)
        .prefetch_related("conversation")
        .all()
    )

    team_participants = [p for p in participants if p.conversation.team_id == team_id]

    _, cached_conv_unread = await im_redis.get_user_unread_counts(user_id)

    peer_user_ids: set[UUID] = set()
    for p in team_participants:
        conv = p.conversation
        if conv.type == ImConversationType.DIRECT:
            peer_id = conv.user2_id if conv.user1_id == user_id else conv.user1_id
            if peer_id:
                peer_user_ids.add(peer_id)

    user_map: dict[UUID, User] = {}
    if peer_user_ids:
        users = await User.filter(id__in=list(peer_user_ids)).all()
        user_map = {u.id: u for u in users}

    results: list[dict[str, Any]] = []
    need_cache_rebuild = cached_conv_unread is None
    computed_unread_map: dict[str, int] = {}

    for p in team_participants:
        conv = p.conversation
        conv_id_str = str(conv.id)

        if cached_conv_unread is not None and conv_id_str in cached_conv_unread:
            unread_count = cached_conv_unread[conv_id_str]
        else:
            unread_count = max(conv.latest_seq - p.last_read_seq, 0)
            computed_unread_map[conv_id_str] = unread_count

        peer_info: dict[str, Any] | None = None
        if conv.type == ImConversationType.DIRECT:
            peer_id = conv.user2_id if conv.user1_id == user_id else conv.user1_id
            if peer_id and peer_id in user_map:
                u = user_map[peer_id]
                peer_info = {
                    "id": str(u.id),
                    "username": u.username,
                    "full_name": getattr(u, "full_name", None) or u.username,
                    "avatar_url": u.avatar_url,
                }

        results.append(
            {
                "id": conv_id_str,
                "type": conv.type.value,
                "team_id": str(conv.team_id),
                "is_pinned": p.is_pinned,
                "is_muted": p.is_muted,
                "last_read_seq": p.last_read_seq,
                "latest_seq": conv.latest_seq,
                "unread_count": unread_count,
                "last_message_content": conv.last_message_content,
                "last_message_at": conv.last_message_at.isoformat()
                if conv.last_message_at
                else None,
                "peer": peer_info,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
            }
        )

    if need_cache_rebuild:
        total_unreads = sum(computed_unread_map.values())
        await im_redis.rebuild_unread_cache(user_id, total_unreads, computed_unread_map)

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        pinned_flag = 1 if item["is_pinned"] else 0
        time_str = item["last_message_at"] or item["created_at"]
        return (pinned_flag, time_str)

    results.sort(key=sort_key, reverse=True)
    return results


async def get_messages(
    conversation_id: UUID,
    user_id: UUID,
    before_seq: int | None = None,
    after_seq: int | None = None,
    around_seq: int | None = None,
    limit: int = 50,
) -> tuple[list[ImMessage], bool]:
    """基于游标 (Cursor) 高性能分页查询消息流，避免深分页全表扫描。"""
    conv = await ImConversation.filter(id=conversation_id).first()
    if not conv:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    if conv.type == ImConversationType.DIRECT:
        if conv.user1_id != user_id and conv.user2_id != user_id:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="conversation_access_denied",
                status_code=403,
            )
    elif conv.type == ImConversationType.SYSTEM:
        if conv.user1_id != user_id:
            raise BusinessError(
                code=ResponseCode.FORBIDDEN,
                msg_key="conversation_access_denied",
                status_code=403,
            )

    safe_limit = max(1, min(limit, 100))
    query = ImMessage.filter(conversation_id=conversation_id)
    if around_seq is not None:
        half = safe_limit // 2
        start_seq = max(1, around_seq - half)
        msgs = (
            await query.filter(seq__gte=start_seq)
            .order_by("seq")
            .limit(safe_limit)
            .all()
        )
        return msgs, False

    if after_seq is not None:
        msgs = (
            await query.filter(seq__gt=after_seq)
            .order_by("seq")
            .limit(safe_limit + 1)
            .all()
        )
        has_more = len(msgs) > safe_limit
        return msgs[:safe_limit], has_more

    if before_seq is not None:
        msgs = (
            await query.filter(seq__lt=before_seq)
            .order_by("-seq")
            .limit(safe_limit + 1)
            .all()
        )
        has_more = len(msgs) > safe_limit
        selected = msgs[:safe_limit]
        selected.reverse()
        return selected, has_more

    msgs = await query.order_by("-seq").limit(safe_limit + 1).all()
    has_more = len(msgs) > safe_limit
    selected = msgs[:safe_limit]
    selected.reverse()
    return selected, has_more


async def mark_conversation_read(
    conversation_id: UUID, user_id: UUID, up_to_seq: int | None = None
) -> int:
    """标记会话已读：更新参与者 last_read_seq 游标，并原子扣减 Redis 未读数，多端广播。"""
    conv = await ImConversation.filter(id=conversation_id).first()
    if not conv:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="conversation_not_found",
            status_code=404,
        )

    participant = await ImConversationParticipant.filter(
        conversation_id=conversation_id, user_id=user_id
    ).first()
    if not participant:
        return 0

    target_seq = up_to_seq if up_to_seq is not None else conv.latest_seq
    if target_seq > participant.last_read_seq:
        participant.last_read_seq = target_seq
        await participant.save(update_fields=["last_read_seq", "updated_at"])

    cleared = await im_redis.mark_conversation_read_in_cache(user_id, conversation_id)

    # 广播给该用户其他端
    await im_redis.publish_im_event(
        user_id,
        "conversation_read",
        {
            "conversation_id": str(conversation_id),
            "last_read_seq": target_seq,
        },
    )
    return cleared


async def get_global_unread_count(user_id: UUID) -> int:
    """获取用户所有团队下的全局消息未读总数（O(1) 缓存读取）。"""
    cached_total, _ = await im_redis.get_user_unread_counts(user_id)
    if cached_total is not None:
        return cached_total

    participants = (
        await ImConversationParticipant.filter(user_id=user_id)
        .prefetch_related("conversation")
        .all()
    )

    conv_map: dict[str, int] = {}
    total = 0
    for p in participants:
        unread = max(p.conversation.latest_seq - p.last_read_seq, 0)
        conv_map[str(p.conversation.id)] = unread
        total += unread

    await im_redis.rebuild_unread_cache(user_id, total, conv_map)
    return total


async def search_messages(
    team_id: UUID, user_id: UUID, query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """全局搜索当前用户在指定团队下的历史聊天消息记录。"""
    cleaned = query.strip()
    if not cleaned:
        return []

    participants = (
        await ImConversationParticipant.filter(user_id=user_id)
        .prefetch_related("conversation")
        .all()
    )
    team_convs = [
        p.conversation for p in participants if p.conversation.team_id == team_id
    ]
    if not team_convs:
        return []

    conv_map = {c.id: c for c in team_convs}
    conv_ids = list(conv_map.keys())

    safe_limit = max(1, min(limit, 50))
    messages = (
        await ImMessage.filter(conversation_id__in=conv_ids, content__icontains=cleaned)
        .order_by("-created_at")
        .limit(safe_limit)
        .all()
    )
    if not messages:
        return []

    peer_user_ids: set[UUID] = set()
    for m in messages:
        c = conv_map.get(m.conversation_id)
        if c and c.type == ImConversationType.DIRECT:
            pid = c.user2_id if c.user1_id == user_id else c.user1_id
            if pid:
                peer_user_ids.add(pid)

    user_map: dict[UUID, User] = {}
    if peer_user_ids:
        users = await User.filter(id__in=list(peer_user_ids)).all()
        user_map = {u.id: u for u in users}

    results: list[dict[str, Any]] = []
    for m in messages:
        c = conv_map.get(m.conversation_id)
        if not c:
            continue
        peer_info: dict[str, Any] | None = None
        if c.type == ImConversationType.DIRECT:
            pid = c.user2_id if c.user1_id == user_id else c.user1_id
            if pid and pid in user_map:
                u = user_map[pid]
                peer_info = {
                    "id": str(u.id),
                    "username": u.username,
                    "full_name": getattr(u, "full_name", None) or u.username,
                    "avatar_url": u.avatar_url,
                }

        results.append(
            {
                "message_id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "seq": m.seq,
                "content": m.content,
                "msg_type": m.msg_type.value,
                "conversation_type": c.type.value,
                "created_at": m.created_at.isoformat(),
                "peer": peer_info,
            }
        )

    return results
