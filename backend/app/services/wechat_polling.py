"""Bounded, fairly scheduled WeChat polling with durable batch ownership.

PostgreSQL owns queued/running claims; Redis's per-binding lease remains the
last execution fence. Fixed reusable slots bound broker backlog even when no
poll worker is available. Claims contain only identifiers, never credentials.
"""

import asyncio
import logging
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core.config import settings
from app.models.wechat_knowledge import WeChatKnowledgeBinding, WeChatPollBatch
from app.services.integration_features import enabled_features
from app.services.wechat_connection import utcnow

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 3
BATCH_TIMEOUT_SECONDS = 30
CLAIM_SECONDS = 90


async def _purposes() -> list[str]:
    features = await enabled_features("wechat")
    return [
        purpose
        for purpose, capability in (
            ("agent", "agent_chat"),
            ("knowledge_collection", "knowledge_collection"),
        )
        if capability in features
    ]


async def _claim_batch() -> tuple[int, UUID] | None:
    purposes = await _purposes()
    if not purposes:
        return None
    now = utcnow()
    async with in_transaction() as db:
        slot = await (
            WeChatPollBatch.filter(id__lte=settings.WECHAT_POLL_MAX_BATCHES)
            .filter(Q(claim__isnull=True) | Q(expires_at__lte=now))
            .using_db(db)
            .select_for_update(skip_locked=True)
            .order_by("id")
            .first()
        )
        if slot is None:
            return None
        # Old queued tasks are fenced by their token before this slot is reused.
        if slot.claim:
            await (
                WeChatKnowledgeBinding.filter(poll_claim=slot.claim)
                .using_db(db)
                .update(poll_claim=None, poll_claim_expires_at=None)
            )
        rows = await (
            WeChatKnowledgeBinding.filter(
                status="connected", purpose__in=purposes, poll_next_at__lte=now
            )
            .exclude(token="")
            .filter(Q(poll_claim__isnull=True) | Q(poll_claim_expires_at__lte=now))
            .using_db(db)
            .select_for_update(skip_locked=True)
            .order_by("poll_next_at", "id")
            .limit(settings.WECHAT_POLL_BATCH_SIZE)
        )
        if not rows:
            slot.claim, slot.expires_at, slot.bindings, slot.started = (
                None,
                None,
                [],
                False,
            )
            await slot.save(using_db=db)
            return None
        claim = uuid4()
        expires = now + timedelta(seconds=CLAIM_SECONDS)
        identifiers = [row.id for row in rows]
        await (
            WeChatKnowledgeBinding.filter(id__in=identifiers)
            .using_db(db)
            .update(
                poll_claim=claim,
                poll_claim_expires_at=expires,
                poll_next_at=now + timedelta(seconds=POLL_INTERVAL_SECONDS),
            )
        )
        slot.claim, slot.expires_at, slot.started = claim, expires, False
        slot.bindings = [
            {"id": str(row.id), "generation": str(row.generation)} for row in rows
        ]
        await slot.save(using_db=db)
        return slot.id, claim


async def _release_batch(
    slot_id: int, claim: UUID, *, unpublished: bool = False
) -> None:
    async with in_transaction() as db:
        query = WeChatPollBatch.filter(id=slot_id, claim=claim)
        if unpublished:
            # A publish error may be ambiguous: do not revoke an executing batch.
            query = query.filter(started=False)
        changed = await query.using_db(db).update(
            claim=None, expires_at=None, started=False, bindings=[]
        )
        if changed:
            await (
                WeChatKnowledgeBinding.filter(poll_claim=claim)
                .using_db(db)
                .update(poll_claim=None, poll_claim_expires_at=None)
            )


async def dispatch_bindings() -> dict:
    from app.tasks.wechat_poll import poll_batch_task

    if not await _purposes():
        return {"batches": 0}
    # Bounded slot inventory; increasing max batches is safe while workers run.
    for slot_id in range(1, settings.WECHAT_POLL_MAX_BATCHES + 1):
        await WeChatPollBatch.get_or_create(id=slot_id)
    dispatched = 0
    for _ in range(settings.WECHAT_POLL_MAX_BATCHES):
        batch = await _claim_batch()
        if batch is None:
            break
        slot_id, claim = batch
        try:
            await asyncio.to_thread(
                poll_batch_task.apply_async,
                args=[slot_id, str(claim)],
                task_id=str(claim),
                expires=CLAIM_SECONDS,
            )
        except Exception:
            await _release_batch(slot_id, claim, unpublished=True)
            raise
        dispatched += 1
    return {"batches": dispatched}


async def _start_batch(slot_id: int, claim: UUID) -> list[dict]:
    now = utcnow()
    async with in_transaction() as db:
        slot = await (
            WeChatPollBatch.filter(
                id=slot_id, claim=claim, started=False, expires_at__gt=now
            )
            .using_db(db)
            .select_for_update()
            .first()
        )
        if slot is None:
            return []
        slot.started = True
        slot.expires_at = now + timedelta(seconds=CLAIM_SECONDS)
        await slot.save(using_db=db, update_fields=["started", "expires_at"])
        await (
            WeChatKnowledgeBinding.filter(poll_claim=claim)
            .using_db(db)
            .update(poll_claim_expires_at=slot.expires_at)
        )
        return slot.bindings


async def poll_batch(slot_id: int, claim_text: str) -> dict:
    from app.services.wechat_receiver import poll_binding

    claim = UUID(claim_text)
    snapshots = await _start_batch(slot_id, claim)
    if not snapshots:
        return {"bindings": 0, "polled": 0}
    polled = 0
    try:
        purposes = await _purposes()
        if not purposes:
            return {"bindings": 0, "polled": 0}
        # Database snapshots are bounded at publication. Stale generations are
        # checked again for each request, not loaded as a batch-wide ORM cache.
        work = iter(snapshots)
        concurrency = min(settings.WECHAT_POLL_CONCURRENCY, len(snapshots))
        limits = httpx.Limits(
            max_connections=concurrency, max_keepalive_connections=concurrency
        )
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=40.0, limits=limits
        ) as http:

            async def consume():
                nonlocal polled
                for snapshot in work:
                    binding = (
                        await WeChatKnowledgeBinding.filter(
                            id=snapshot["id"],
                            generation=snapshot["generation"],
                            poll_claim=claim,
                            status="connected",
                            purpose__in=purposes,
                        )
                        .exclude(token="")
                        .first()
                    )
                    if binding is None:
                        continue
                    started = utcnow()
                    try:
                        result = await poll_binding(binding, http=http)
                        polled += int(bool(result.get("polled")))
                    except Exception:
                        logger.exception(
                            "WeChat poll failed for binding %s", binding.id
                        )
                    finally:
                        # A slow poll does not add an extra interval afterwards;
                        # fast polls still wait the normal three-second cadence.
                        await WeChatKnowledgeBinding.filter(
                            id=binding.id, poll_claim=claim
                        ).update(
                            poll_next_at=max(
                                utcnow(),
                                started + timedelta(seconds=POLL_INTERVAL_SECONDS),
                            )
                        )

            async with asyncio.timeout(BATCH_TIMEOUT_SECONDS):
                async with asyncio.TaskGroup() as group:
                    for _ in range(concurrency):
                        group.create_task(consume())
        return {"bindings": len(snapshots), "polled": polled}
    finally:
        await _release_batch(slot_id, claim)
