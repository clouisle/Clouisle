"""Celery tasks for sandbox runtime execution."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from celery import shared_task

from app.services.error_messages import resolve_user_visible_error
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.gateway import sandbox_gateway
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
        session_id = job_payload.pop("session_id", None)
        session_agent_id = job_payload.pop("session_agent_id", None)
        session_team_id = job_payload.pop("session_team_id", None)

        job = SandboxJob.model_validate(job_payload)
        manager = SandboxManager()
        result = await manager.execute(
            job,
            session_id=session_id,
            session_agent_id=session_agent_id,
            session_team_id=session_team_id,
        )
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
                error=resolve_user_visible_error(
                    str(e),
                    fallback_key="tool_execution_failed",
                ),
            )
        )
        raise


@shared_task(name="tasks.cleanup_expired_sandbox_sessions", ignore_result=True, queue="sandbox")
def cleanup_expired_sandbox_sessions_task() -> dict:
    async def _run() -> dict:
        cleaned = await sandbox_gateway.cleanup_expired_sessions()
        return {"cleaned": cleaned}

    loop = _get_worker_loop()
    try:
        return loop.run_until_complete(_run())
    except Exception as e:
        logger.exception("Sandbox session cleanup failed: %s", e)
        raise
