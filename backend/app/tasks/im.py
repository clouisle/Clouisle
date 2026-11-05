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

from tortoise.expressions import Subquery

from app.core.celery import celery_app
from app.core.config import settings
from app.core.timezone import now_utc
from app.models.asset import Asset, AssetScopeRef, AssetScopeType
from app.models.im import ImMessage

logger = logging.getLogger(__name__)


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
    candidates = await (
        Asset.filter(
            created_at__lt=cutoff,
            id__in=Subquery(scoped_asset_ids),
        )
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
