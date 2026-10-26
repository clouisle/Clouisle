"""Periodic cleanup for expired/consumed tool OAuth flows.

Flows are already single-use and rejected after ten minutes; this sweep bounds
storage growth. It is idempotent and safe to run concurrently.
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


async def _cleanup_tool_oauth_flows(limit: int = 500) -> dict:
    from app.services.tool_oauth import ToolOAuthService

    deleted = await ToolOAuthService.cleanup_expired_flows(limit=limit)
    if deleted:
        logger.info("Deleted %s expired tool OAuth flow(s)", deleted)
    return {"deleted": deleted}


@shared_task(name="tasks.cleanup_expired_tool_oauth_flows", ignore_result=False)
def cleanup_expired_tool_oauth_flows_task(limit: int = 500) -> dict:
    return _run_async(_cleanup_tool_oauth_flows(limit))
