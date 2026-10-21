"""Knowledge-queue processing and durable receipt recovery."""

from celery import shared_task
from tortoise.expressions import Q

from app.tasks.knowledge_base import _run_async
from app.services.integration_features import enabled_features


@shared_task(
    name="app.tasks.wechat_knowledge.process_receipt_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_receipt_task(receipt_id: str) -> dict:
    from app.services.wechat_ingestion import process_receipt

    return _run_async(process_receipt(receipt_id))


@shared_task(name="app.tasks.wechat_knowledge.recover_receipts_task")
def recover_receipts_task() -> dict:
    from app.models.wechat_knowledge import WeChatKnowledgeReceipt, WeChatKnowledgeLogin
    from app.services.wechat_connection import utcnow

    async def recover():
        await WeChatKnowledgeLogin.filter(expires_at__lt=utcnow()).delete()
        if "knowledge_collection" not in await enabled_features("wechat"):
            return {"queued": 0}
        rows = (
            await WeChatKnowledgeReceipt.filter(
                Q(status__in=["pending", "processing"]) | Q(reply_status="pending"),
                binding__status="connected",
            )
            .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=utcnow()))
            .order_by("created_at")
            .limit(100)
        )
        for row in rows:
            process_receipt_task.delay(str(row.id))
        return {"queued": len(rows)}

    return _run_async(recover())
