"""Agent-queue orchestration and recovery of durable WeChat Agent sessions."""

from celery import shared_task
from tortoise.expressions import Q

from app.tasks.knowledge_base import _run_async


@shared_task(
    name="app.tasks.wechat_agent.process_binding_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_binding_task(binding_id: str) -> dict:
    from app.services.wechat_agent_runtime import process_binding
    from app.services.wechat_locks import CollectionBusy, collection_lock

    async def process():
        try:
            async with collection_lock(f"wechat-agent:{binding_id}"):
                return await process_binding(binding_id)
        except CollectionBusy:
            return {"pending": True}

    return _run_async(process())


@shared_task(name="app.tasks.wechat_agent.recover_bindings_task")
def recover_bindings_task() -> dict:
    """Re-drive bindings with unfinished work after a crash or a cold start.

    This is a safety net, not the normal progress loop: ``process_binding``
    re-dispatches its own queued runs and sends its own outbox rows. Queuing a
    binding only when it holds pending/submitted receipts or unsent deliveries
    keeps an idle binding from being reprocessed on every tick.
    """
    from app.models.wechat_agent import WeChatAgentDelivery, WeChatAgentReceipt

    async def recover():
        identifiers = set(
            await WeChatAgentReceipt.filter(status__in=["pending", "submitted"])
            .order_by("created_at")
            .limit(100)
            .values_list("binding_id", flat=True)
        )
        # An unsent delivery can outlive its receipt (the receipt completes as
        # soon as its answer is queued), so delivery work is resolved on its
        # own receipt ids instead of reusing the pending-receipt set.
        delivery_receipt_ids = (
            await WeChatAgentDelivery.filter(Q(status="pending") | Q(status="sending"))
            .order_by("created_at")
            .limit(100)
            .values_list("receipt_id", flat=True)
        )
        if delivery_receipt_ids:
            identifiers.update(
                await WeChatAgentReceipt.filter(
                    id__in=list(delivery_receipt_ids)
                ).values_list("binding_id", flat=True)
            )
        for identifier in identifiers:
            process_binding_task.delay(str(identifier))
        return {"queued": len(identifiers)}

    return _run_async(recover())
