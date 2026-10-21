"""Scheduled Feishu Agent channel processing and recovery."""

from celery import shared_task

from app.tasks.knowledge_base import _run_async


@shared_task(
    name="app.tasks.feishu_agent.process_message_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_message_task(receipt_id: str) -> dict:
    """Advance one accepted inbound message on the ``agent`` queue.

    Authenticated transport intake persists the receipt and queues this task,
    so the provider is acknowledged without waiting for Agent execution.
    Session, run, and outbound reply state stay durable in PostgreSQL.
    """
    from app.services.feishu_agent_runtime import process_message

    return _run_async(process_message(receipt_id))


@shared_task(
    name="app.tasks.feishu_agent.process_pending_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_pending_task() -> dict:
    """Advance every ready receipt; one Beat tick, one bounded batch."""
    from app.services.feishu_agent_runtime import process_pending

    return _run_async(process_pending())


@shared_task(name="app.tasks.feishu_agent.recover_pending_task")
def recover_pending_task() -> dict:
    """Re-drive work that survived a crash or a cold start.

    This is a safety net, not the normal progress loop: ``process_message``
    re-dispatches its own queued runs and drains its own outbox rows.
    """
    return _run_async(_recover())


async def _recover() -> dict:
    from app.services.feishu_agent_runtime import process_pending, recover_pending

    summary = await recover_pending()
    summary["processed"] = (await process_pending()).get("processed", 0)
    return summary
