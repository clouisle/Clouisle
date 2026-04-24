"""Celery tasks for sandbox runtime execution."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from celery import shared_task

from app.core.i18n import t
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxExecutionMetadata, SandboxJob, SandboxTaskStatus
from app.services.sandbox.result_store import sandbox_result_store

logger = logging.getLogger(__name__)


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def run_sandbox_job_task(self, job_payload: dict) -> dict:
    async def _run() -> dict:
        job = SandboxJob.model_validate(job_payload)
        manager = SandboxManager()
        result = await manager.execute(job)
        return {
            "job_id": result.job_id,
            "status": result.status,
            "success": result.success,
        }

    loop = _get_worker_loop()

    try:
        return loop.run_until_complete(_run())
    except Exception as e:
        logger.exception("Sandbox job execution failed: %s", e)
        existing = loop.run_until_complete(sandbox_result_store.get_result(job_payload["job_id"]))
        metadata = existing.metadata if existing is not None else SandboxExecutionMetadata()
        metadata.mark_completed(datetime.now(UTC))
        loop.run_until_complete(
            sandbox_result_store.update_status(
                job_payload["job_id"],
                SandboxTaskStatus.FAILED,
                metadata=metadata,
                error=t("tool_execution_failed"),
            )
        )
        raise
