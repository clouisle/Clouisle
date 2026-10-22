"""Default-queue polling: bounded dispatch and finite asynchronous batches."""

from celery import shared_task

from app.tasks.knowledge_base import _run_async


@shared_task(name="app.tasks.wechat_poll.dispatch_bindings_task", expires=3)
def dispatch_bindings_task() -> dict:
    from app.services.wechat_polling import dispatch_bindings

    return _run_async(dispatch_bindings())


@shared_task(
    name="app.tasks.wechat_poll.poll_batch_task",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=40,
    time_limit=45,
)
def poll_batch_task(slot_id: int, claim: str) -> dict:
    from app.services.wechat_polling import poll_batch

    return _run_async(poll_batch(slot_id, claim))
