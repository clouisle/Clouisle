"""Reclaim IM attachment assets that were uploaded but never referenced.

An attachment upload and the message that references it are two independent
requests. If the user abandons the draft (or sending fails and the draft is
discarded), the Asset, its IM_CONVERSATION scope ref and the stored bytes stay
behind. The reclaimer deletes only assets older than the TTL that no message
references, and leaves the row in place when byte deletion fails so the next
run can retry.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from tortoise.expressions import Subquery

from app.core.celery import celery_app
from app.core.config import settings
from app.core.timezone import now_utc
from app.models.asset import Asset, AssetScopeRef, AssetScopeType
from app.models.im import ImMessage

logger = logging.getLogger(__name__)

FANOUT_BATCH_SIZE = 200


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """获取或创建事件循环"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


async def _cleanup_orphan_im_assets(
    *, ttl_hours: int | None = None, batch_size: int | None = None
) -> dict:
    """Delete unreferenced IM attachment assets older than the TTL.

    A message insert can race with this task only for assets older than the
    TTL; the per-asset message re-check narrows that window to a single
    statement. Bytes are deleted first: if that fails the row survives and the
    next run retries instead of leaking an unrecoverable file.
    """
    ttl = settings.IM_ORPHAN_ASSET_TTL_HOURS if ttl_hours is None else ttl_hours
    limit = (
        settings.IM_ORPHAN_ASSET_CLEANUP_BATCH_SIZE
        if batch_size is None
        else batch_size
    )
    cutoff = now_utc() - timedelta(hours=ttl)

    scoped_asset_ids = AssetScopeRef.filter(
        scope_type=AssetScopeType.IM_CONVERSATION
    ).values_list("asset_id", flat=True)
    # Filter at SQL level: picking the oldest N and discarding referenced ones
    # in Python would let a pile of long-lived referenced assets starve the
    # batch forever. The subquery selects non-null ids only, so NOT IN cannot
    # become vacuously empty.
    message_asset_ids = ImMessage.filter(asset_id__isnull=False).values_list(
        "asset_id", flat=True
    )
    candidates = await (
        Asset.filter(
            created_at__lt=cutoff,
            id__in=Subquery(scoped_asset_ids),
        )
        .exclude(id__in=Subquery(message_asset_ids))
        .order_by("created_at")
        .limit(limit)
        .values_list("id", "storage_key")
    )

    if not candidates:
        logger.info("No orphan IM assets to clean up")
        return {
            "status": "success",
            "scanned": 0,
            "referenced": 0,
            "deleted": 0,
            "failed": 0,
            "ttl_hours": ttl,
            "cutoff": cutoff.isoformat(),
        }

    candidate_ids = [asset_id for asset_id, _ in candidates]
    referenced = set(
        await ImMessage.filter(asset_id__in=candidate_ids).values_list(
            "asset_id", flat=True
        )
    )

    # Imported lazily: the upload endpoint imports service modules that are
    # irrelevant to worker startup and would widen the import cycle.
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.upload_storage import get_upload_storage_backend

    storage = await get_upload_storage_backend(UPLOAD_ROOT)

    deleted = 0
    failed = 0
    for asset_id, storage_key in candidates:
        if asset_id in referenced:
            continue
        if await ImMessage.filter(asset_id=asset_id).exists():
            continue
        try:
            await storage.delete(storage_key)
            await Asset.filter(id=asset_id).delete()
        except Exception:
            failed += 1
            logger.exception("Failed to reclaim orphan IM asset %s", asset_id)
            continue
        deleted += 1

    result = {
        "status": "success",
        "scanned": len(candidates),
        "referenced": len(referenced),
        "deleted": deleted,
        "failed": failed,
        "ttl_hours": ttl,
        "cutoff": cutoff.isoformat(),
    }
    logger.info("IM orphan asset cleanup complete: %s", result)
    return result


@celery_app.task(
    name="tasks.cleanup_orphan_im_assets", ignore_result=True, queue="default"
)
def cleanup_orphan_im_assets_task() -> dict:
    """回收未被消息引用的 IM 附件资产（Celery 定时任务）。"""
    loop = _get_event_loop()
    try:
        return loop.run_until_complete(_cleanup_orphan_im_assets())
    except Exception as e:
        logger.error(f"Failed to clean up orphan IM assets: {e}", exc_info=True)
        raise


async def _fanout_global_notification(notification_id: UUID) -> dict:
    """把一条 GLOBAL 通知扇出到所有活跃用户的系统通知会话。

    走 Celery 而不是在创建通知的请求里同步执行，避免请求被 N 次写库拖住；
    逐用户幂等键与实时桥接一致，任务重试不会产生重复消息。
    """
    from types import SimpleNamespace

    from app.models.notification import Notification, NotificationScope
    from app.models.user import User
    from app.services import im_service
    from app.services.im_system_bridge import (
        _bridge_client_msg_id,
        _build_notification_message,
        _resolve_notification_team_id,
    )

    notification = await Notification.filter(
        id=notification_id, scope=NotificationScope.GLOBAL
    ).first()
    if notification is None:
        logger.info("Global notification %s no longer exists", notification_id)
        return {"sent": 0, "skipped": 0}

    content, msg_type, payload = _build_notification_message(notification)
    sent = 0
    skipped = 0
    cursor: UUID | None = None

    while True:
        query = User.filter(is_active=True)
        if cursor is not None:
            query = query.filter(id__gt=cursor)
        users = await query.order_by("id").limit(FANOUT_BATCH_SIZE).all()
        if not users:
            break
        cursor = users[-1].id

        for user in users:
            team_id = await _resolve_notification_team_id(
                SimpleNamespace(user_id=user.id, team_id=None)
            )
            if team_id is None:
                skipped += 1
                continue
            try:
                await im_service.send_system_message(
                    team_id=team_id,
                    recipient_user_id=user.id,
                    content=content,
                    msg_type=msg_type,
                    payload=payload,
                    client_msg_id=_bridge_client_msg_id(notification.id, user.id),
                )
            except Exception:
                skipped += 1
                logger.exception(
                    "Failed to fan out global notification %s to user %s",
                    notification.id,
                    user.id,
                )
            else:
                sent += 1

    result = {"sent": sent, "skipped": skipped}
    logger.info("Global notification %s fan-out complete: %s", notification_id, result)
    return result


@celery_app.task(
    name="tasks.fanout_global_notification", ignore_result=True, queue="default"
)
def fanout_global_notification_task(notification_id: str) -> dict:
    """把 GLOBAL 通知扇出到所有活跃用户（Celery 任务）。"""
    loop = _get_event_loop()
    try:
        return loop.run_until_complete(
            _fanout_global_notification(UUID(notification_id))
        )
    except Exception as e:
        logger.error("Failed to fan out global notification: %s", e, exc_info=True)
        raise
