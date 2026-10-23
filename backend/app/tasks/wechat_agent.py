"""Scheduled WeChat Agent receipt recovery."""

import logging

from celery import shared_task

from app.core.timezone import now_utc
from app.services.integration_features import enabled_features
from app.tasks.knowledge_base import _run_async

logger = logging.getLogger(__name__)
RECOVERY_BATCH_SIZE = 64


@shared_task(
    name="app.tasks.wechat_agent.process_claimed_binding_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_binding_task(binding_id: str, ownership_token: str) -> dict:
    from app.services.wechat_agent_runtime import process_binding
    from app.services.wechat_agent_dispatch import (
        owns_binding_dispatch,
        release_binding_dispatch,
    )
    from app.services.wechat_locks import CollectionBusy, collection_lock

    async def process():
        if not await owns_binding_dispatch(binding_id, ownership_token):
            return {"stale": True}

        acquired_lock = False
        try:
            async with collection_lock(f"wechat-agent:{binding_id}"):
                acquired_lock = True
                return await process_binding(binding_id)
        except CollectionBusy:
            return {"pending": True}
        finally:
            if acquired_lock:
                await release_binding_dispatch(binding_id, ownership_token)

    return _run_async(process())


@shared_task(name="app.tasks.wechat_agent.recover_bindings_task")
def recover_bindings_task() -> dict:
    """Fairly re-drive a bounded page of bindings that still have durable work."""
    from tortoise import Tortoise

    from app.models.wechat_knowledge import WeChatKnowledgeBinding
    from app.services.wechat_agent_dispatch import enqueue_binding

    async def recover():
        if "agent_chat" not in await enabled_features("wechat"):
            return {"queued": 0}

        # EXISTS keeps this a bounded binding scan even when a binding has many
        # receipts and deliveries (and their joins would multiply one another).
        conn = Tortoise.get_connection("default")
        placeholder = "?" if conn.capabilities.dialect == "sqlite" else "$1"
        identifiers = await conn.execute_query_dict(
            f"""
            SELECT b.id
            FROM wechat_knowledge_bindings b
            WHERE EXISTS (
                SELECT 1
                FROM wechat_agent_receipts r
                WHERE r.binding_id = b.id
                  AND r.status IN ('pending', 'submitted')
            ) OR EXISTS (
                SELECT 1
                FROM integration_deliveries d
                JOIN wechat_agent_receipts r ON r.id = d.receipt_id
                WHERE r.binding_id = b.id
                  AND d.provider_type = 'wechat'
                  AND d.status IN ('pending', 'sending')
            )
            ORDER BY b.agent_recovery_at, b.id
            LIMIT {placeholder}
            """,
            [RECOVERY_BATCH_SIZE],
        )
        if not identifiers:
            return {"queued": 0}

        await WeChatKnowledgeBinding.filter(
            id__in=[row["id"] for row in identifiers]
        ).update(agent_recovery_at=now_utc())

        queued = 0
        for row in identifiers:
            try:
                if await enqueue_binding(row["id"]):
                    queued += 1
            except Exception:
                logger.exception(
                    "Failed to dispatch WeChat Agent recovery for binding %s",
                    row["id"],
                )
        return {"queued": queued}

    return _run_async(recover())
