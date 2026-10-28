"""Scheduled expiry for durable tool execution approvals.

``expire_due_executions`` is the only terminal producer for overdue approval
requests. Without a periodic caller, a parked AgentRun/workflow could wait
forever and never receive the tool-error result that resumes it. This task is
that caller; it is safe to run concurrently because each execution expiry is
row-locked and idempotent.
"""

import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():  # pragma: no cover - worker-thread safety
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return loop.run_until_complete(coro)


async def _expire_tool_approvals(limit: int = 200) -> dict:
    """Expire overdue tool approvals and resume their owning durable run."""
    from app.services.tool_approvals import (
        expire_due_executions,
        mark_stale_executing_outcome_unknown,
    )

    try:
        expired = await expire_due_executions(limit=limit)
    except Exception:
        logger.exception("Tool approval expiry sweep failed")
        raise
    if expired:
        logger.info("Expired %s overdue tool approval execution(s)", expired)

    # A worker can die after claiming an execution. Only mark it unknown once
    # its owning run is terminal/lost and the claim is stale; never replay.
    try:
        outcome_unknown = await mark_stale_executing_outcome_unknown(limit=limit)
    except Exception:
        logger.exception("Tool execution stale-claim sweep failed")
        raise
    return {"expired": expired, "outcome_unknown": outcome_unknown}


@shared_task(name="tasks.expire_tool_approvals", ignore_result=False)
def expire_tool_approvals_task(limit: int = 200) -> dict:
    return _run_async(_expire_tool_approvals(limit))
