"""
Celery tasks for durable AgentRun execution.

Runs on the default queue (no retries: model/tool side effects are not
idempotent). The task reloads the ORM context from the serialized payload
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
    from app.services.agent_run_store import get_run, transition_run_if_status

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
            if not run:
                return {"status": "failed", "error": error_text}
            active_statuses = (
                AgentRunStatus.QUEUED,
                AgentRunStatus.RUNNING,
                AgentRunStatus.STOPPING,
                AgentRunStatus.COMPLETING,
            )
            if run.status not in active_statuses:
                return {"status": run.status.value, "error": error_text}
            failed = await transition_run_if_status(
                run,
                run.status,
                AgentRunStatus.FAILED,
                error_code="task_crash",
                error_message=error_text,
            )
            if failed is None:
                current = await get_run(run_id)
                return {
                    "status": current.status.value if current else "failed",
                    "error": error_text,
                }
            try:
                from app.services.agent_run_stream import AgentRunStream

                stream = AgentRunStream(run_id)
                await stream.seed_sequence()
                await stream.publish("error", {"code": "task_crash", "msg": error_text})
                await stream.publish("run_end", {"status": "failed"})
            except Exception:
                logger.warning(
                    "Failed to publish crash state for AgentRun %s",
                    run_id,
                    exc_info=True,
                )
            return {"status": AgentRunStatus.FAILED.value, "error": error_text}

        return _run_async(_mark_failed())


@shared_task(name="tasks.sweep_lost_agent_runs", ignore_result=False)
def sweep_lost_agent_runs_task(max_age_seconds: int = 120) -> dict:
    """Mark runs whose worker died as INTERRUPTED.

    A run whose process is killed mid-flight never reaches a terminal state:
    its row stays ``running``/``stopping`` and its Redis lease expires. This
    sweep is what actually writes ``AgentRunStatus.INTERRUPTED`` — without it
    that status exists in the enum but is never produced, and a crashed run
    stays reported as in-flight forever.

    Safe to run on a schedule: ``mark_expired_runs_interrupted`` re-checks the
    lease per run and never replays side-effecting work.
    """

    async def _sweep() -> dict:
        from app.services.agent_run_store import mark_expired_runs_interrupted

        try:
            marked = await mark_expired_runs_interrupted(
                max_age_seconds=max_age_seconds
            )
        except Exception:
            logger.exception("Agent run worker-loss sweep failed")
            raise
        if marked:
            logger.warning("Marked %s lost AgentRun(s) as interrupted", marked)
        return {"marked": marked}

    return _run_async(_sweep())
