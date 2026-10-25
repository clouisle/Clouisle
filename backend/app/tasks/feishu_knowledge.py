"""Feishu sync dispatch; route these tasks to the existing knowledge queue."""

from celery import shared_task

from app.tasks.knowledge_base import _run_async


@shared_task(
    name="app.tasks.feishu_knowledge.sync_source_task",
    acks_late=True,
    reject_on_worker_lost=True,
)
def sync_source_task(source_id: str, dispatch_token: str) -> dict:
    from app.services.feishu_knowledge import sync_source

    return _run_async(sync_source(source_id, dispatch_token))


@shared_task(name="app.tasks.feishu_knowledge.dispatch_due_sources_task")
def dispatch_due_sources_task() -> dict:
    from app.services.feishu_knowledge import dispatch_due_sources

    return _run_async(dispatch_due_sources())
