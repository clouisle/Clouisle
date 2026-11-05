from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import deps
from app.api.team_access import check_team_access
from app.api.v1.endpoints.upload import (
    _upload_storage,
    _validate_upload_size,
    save_generated_upload,
)
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.models.im import ImConversation, ImConversationType, ImMessage
from app.models.asset import Asset, AssetScopeType, AssetSource
from app.models.user import TeamMember, User
from app.services.asset import asset_service
from app.schemas.im import (
    DirectConversationCreate,
    ImAttachmentOut,
    ImConversationOut,
    ImMessageListOut,
    ImMessageOut,
    ImPeerOut,
    ImUnreadCountOut,
    MarkReadRequest,
    SendMessageRequest,
    ImSearchResultOut,
)
from app.services import im_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _build_attachment_map(msgs: list[ImMessage]) -> dict[UUID, ImAttachmentOut]:
    """按 asset_id 批量取回附件元信息，避免 N+1 查询。"""
    ids = {m.asset_id for m in msgs if m.asset_id}
    if not ids:
        return {}
    assets = await Asset.filter(id__in=ids).all()
    return {
        a.id: ImAttachmentOut(
            asset_id=str(a.id),
            filename=a.display_filename or a.original_filename,
            size=a.size,
            content_type=a.content_type,
            url=f"/api/v1/upload/files/{a.storage_key}",
        )
        for a in assets
    }


@router.get("/conversations", response_model=Response[list[ImConversationOut]])
async def list_conversations(
    team_id: UUID = Query(..., description="团队 ID"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """获取当前用户在指定团队下的所有 IM 会话列表（系统通知置顶）。"""
    await check_team_access(team_id, current_user)
    items = await im_service.list_conversations(team_id, current_user.id)
    return success(data=items)


@router.post("/conversations/direct", response_model=Response[ImConversationOut])
async def create_or_get_direct_conversation(
    payload: DirectConversationCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """创建或获取与指定同团队成员的单聊会话。"""
    await check_team_access(payload.team_id, current_user)
    conv = await im_service.get_or_create_direct_conversation(
        team_id=payload.team_id,
        current_user_id=current_user.id,
        target_user_id=payload.target_user_id,
    )

    # 查阅对方信息组装返回
    peer_id = conv.user2_id if conv.user1_id == current_user.id else conv.user1_id
    peer_out = None
    if peer_id:
        peer_user = await User.filter(id=peer_id).first()
        if peer_user:
            peer_out = ImPeerOut(
                id=str(peer_user.id),
                username=peer_user.username,
                full_name=getattr(peer_user, "full_name", None) or peer_user.username,
                avatar_url=peer_user.avatar_url,
            )

    return success(
        data=ImConversationOut(
            id=str(conv.id),
            type=conv.type.value,
            team_id=str(conv.team_id),
            is_pinned=False,
            is_muted=False,
            last_read_seq=0,
            latest_seq=conv.latest_seq,
            unread_count=0,
            last_message_content=conv.last_message_content,
            last_message_at=conv.last_message_at.isoformat()
            if conv.last_message_at
            else None,
            peer=peer_out,
            created_at=conv.created_at.isoformat(),
            updated_at=conv.updated_at.isoformat(),
        )
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Response[ImMessageListOut],
)
async def get_messages(
    conversation_id: UUID,
    before_seq: int | None = Query(None, description="拉取小于该序号的历史消息"),
    after_seq: int | None = Query(None, description="拉取大于该序号的增量消息"),
    around_seq: int | None = Query(None, description="围绕该序号拉取上下文切片"),
    limit: int = Query(50, ge=1, le=100, description="拉取条数"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """基于游标 (Cursor) 分页拉取指定会话的消息流。"""
    msgs, has_more = await im_service.get_messages(
        conversation_id=conversation_id,
        user_id=current_user.id,
        before_seq=before_seq,
        after_seq=after_seq,
        limit=limit,
        around_seq=around_seq,
    )

    attachment_map = await _build_attachment_map(msgs)
    formatted = [
        ImMessageOut(
            id=str(m.id),
            conversation_id=str(m.conversation_id),
            sender_id=str(m.sender_id) if m.sender_id else None,
            client_msg_id=m.client_msg_id,
            seq=m.seq,
            msg_type=m.msg_type.value,
            content=m.content,
            payload=m.payload,
            status=m.status.value,
            created_at=m.created_at.isoformat(),
            attachment=attachment_map.get(m.asset_id),
        )
        for m in msgs
    ]
    return success(data=ImMessageListOut(messages=formatted, has_more=has_more))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=Response[ImMessageOut],
)
async def send_message(
    conversation_id: UUID,
    payload: SendMessageRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """向指定会话发送消息（支持分布式幂等去重与原子自增序号）。"""
    msg = await im_service.send_direct_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        content=payload.content,
        client_msg_id=payload.client_msg_id,
        msg_type=payload.msg_type,
        payload=payload.payload,
        asset_id=payload.asset_id,
    )
    attachment_map = await _build_attachment_map([msg])

    return success(
        data=ImMessageOut(
            id=str(msg.id),
            conversation_id=str(msg.conversation_id),
            sender_id=str(msg.sender_id) if msg.sender_id else None,
            client_msg_id=msg.client_msg_id,
            seq=msg.seq,
            msg_type=msg.msg_type.value,
            content=msg.content,
            payload=msg.payload,
            status=msg.status.value,
            created_at=msg.created_at.isoformat(),
            attachment=attachment_map.get(msg.asset_id),
        )
    )


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=Response[ImAttachmentOut],
)
async def upload_im_attachment(
    conversation_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """上传单个 IM 附件并绑定到会话与团队作用域（字节 IO 在会话锁外完成）。"""
    conv = await ImConversation.filter(id=conversation_id).first()
    if conv is None or conv.type != ImConversationType.DIRECT:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="invalid_conversation_type",
            status_code=400,
        )
    if conv.user1_id != current_user.id and conv.user2_id != current_user.id:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="conversation_access_denied",
            status_code=403,
        )
    await im_service.check_users_in_same_team(
        conv.team_id, conv.user1_id, conv.user2_id
    )

    content = await file.read()
    _validate_upload_size(content)
    content_type = file.content_type or "application/octet-stream"
    upload_info = await save_generated_upload(
        content=content,
        category="im",
        content_type=content_type,
        filename=file.filename,
    )
    asset = None
    try:
        asset = await asset_service.register_bytes(
            storage_key=upload_info["storage_key"],
            original_filename=file.filename or upload_info["filename"],
            content_type=content_type,
            content=content,
            source=AssetSource.UPLOAD,
            team_id=conv.team_id,
            created_by_id=current_user.id,
            provenance={"im_conversation_id": str(conversation_id)},
        )
        await asset_service.get_or_create_ref(
            scope_type=AssetScopeType.IM_CONVERSATION,
            scope_id=conversation_id,
            asset=asset,
        )
    except Exception:
        # Registration and scoping are two statements: a crash between them
        # would otherwise leave bytes (and possibly an Asset row) that no
        # message can reference and that the orphan task cannot see.
        if asset is not None:
            try:
                await Asset.filter(id=asset.id).delete()
            except Exception:
                logger.exception("Failed to clean up IM asset %s", asset.id)
        try:
            await (await _upload_storage()).delete(upload_info["storage_key"])
        except Exception:
            logger.exception(
                "Failed to clean up IM upload %s", upload_info["storage_key"]
            )
        raise

    return success(
        data=ImAttachmentOut(
            asset_id=str(asset.id),
            filename=asset.display_filename or asset.original_filename,
            size=asset.size,
            content_type=asset.content_type,
            url=upload_info["url"],
        )
    )


@router.post(
    "/conversations/{conversation_id}/read", response_model=Response[dict[str, int]]
)
async def mark_read(
    conversation_id: UUID,
    payload: MarkReadRequest = Body(default_factory=MarkReadRequest),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """标记会话已读（原子扣减总未读数）。"""
    cleared = await im_service.mark_conversation_read(
        conversation_id=conversation_id,
        user_id=current_user.id,
        up_to_seq=payload.up_to_seq,
    )
    return success(data={"cleared": cleared})


@router.get("/unread-count", response_model=Response[ImUnreadCountOut])
async def get_unread_count(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """获取当前用户的全局消息总未读数（O(1) 极速缓存响应）。"""
    total = await im_service.get_global_unread_count(current_user.id)
    return success(data=ImUnreadCountOut(total=total))


@router.get("/team-members", response_model=Response[list[dict[str, Any]]])
async def list_team_chat_candidates(
    team_id: UUID = Query(..., description="团队 ID"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """获取当前团队内可发起聊天的其他成员列表。"""
    await check_team_access(team_id, current_user)
    members = (
        await TeamMember.filter(team_id=team_id)
        .exclude(user_id=current_user.id)
        .prefetch_related("user")
        .all()
    )

    candidates = [
        {
            "id": str(m.user.id),
            "username": m.user.username,
            "full_name": getattr(m.user, "full_name", None) or m.user.username,
            "avatar_url": m.user.avatar_url,
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
        }
        for m in members
        if m.user and m.user.is_active
    ]
    return success(data=candidates)


@router.get("/search", response_model=Response[list[ImSearchResultOut]])
async def search_messages(
    team_id: UUID = Query(..., description="团队 ID"),
    q: str = Query(..., min_length=1, max_length=100, description="搜索关键词"),
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """全局搜索当前用户在指定团队下的历史聊天消息记录。"""
    await check_team_access(team_id, current_user)
    results = await im_service.search_messages(
        team_id=team_id,
        user_id=current_user.id,
        query=q,
        limit=limit,
    )
    return success(data=results)


@router.get("/events")
async def stream_im_events(
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """订阅当前用户的 IM 实时事件流 (Server-Sent Events)。

    多节点分布式环境下，通过 Redis Pub/Sub 订阅该用户的专属通道，
    支持新消息实时下发 (new_message)、多端已读同步 (conversation_read) 及心跳保活。
    """
    from app.services import im_redis

    async def event_generator():
        from app.core.redis import get_redis

        user_id_str = str(current_user.id)
        channel_name = im_redis.USER_EVENT_CHANNEL_PREFIX.format(user_id_str)

        r = await get_redis()
        pubsub = r.pubsub()
        if hasattr(pubsub, "__await__"):
            pubsub = await pubsub
        await pubsub.subscribe(channel_name)

        yield "event: connected\ndata: {}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    msg = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True), timeout=15.0
                    )
                    if msg and msg.get("type") == "message":
                        raw_data = msg["data"]
                        payload_str = (
                            raw_data.decode()
                            if isinstance(raw_data, bytes)
                            else str(raw_data)
                        )
                        try:
                            parsed = json.loads(payload_str)
                            event_type = parsed.get("type", "message")
                            event_data = json.dumps(parsed.get("data", {}), default=str)
                            yield f"event: {event_type}\ndata: {event_data}\n\n"
                        except json.JSONDecodeError:
                            yield f"event: message\ndata: {payload_str}\n\n"
                except asyncio.TimeoutError:
                    yield ":ping\n\n"
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
