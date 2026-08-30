"""
Celery tasks for durable AgentRun execution.

Runs on the dedicated ``agent`` queue (no retries: model/tool side effects are
not idempotent). The task reloads the ORM context from the serialized payload
and drives the shared AgentLoop, publishing to the per-run event stream.
"""

import asyncio
import logging
from uuid import UUID

from celery import shared_task

from app.models.agent_run import AgentRunStatus

logger = logging.getLogger(__name__)


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():  # pragma: no cover - worker-thread safety
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return loop.run_until_complete(coro)


@shared_task(bind=True, max_retries=0, acks_late=False)
def run_agent_task(self, payload: dict) -> dict:
    """Execute one AgentRun to terminal, publishing replayable events."""
    from app.services.agent_run_worker import run_agent_round
    from app.services.agent_run_store import get_run, transition_run

    run_id = UUID(payload["run_id"])

    async def _execute() -> dict:
        run = await get_run(run_id)
        if not run:
            return {"status": "error", "error": "run_not_found"}
        return await run_agent_round(payload)

    try:
        return _run_async(_execute())
    except Exception as exc:  # pragma: no cover - final safety net
        logger.exception("Agent run task %s crashed", run_id)
        error_text = str(exc)

        async def _mark_failed():
            run = await get_run(run_id)
            if run:
                await transition_run(
                    run,
                    AgentRunStatus.FAILED,
                    error_code="task_crash",
                    error_message=error_text,
                )
            return {"status": "failed", "error": error_text}

        return _run_async(_mark_failed())
