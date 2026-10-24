"""Coalesced wakeups for durable WeChat Agent receipt processing."""

import asyncio
import logging
from uuid import UUID, uuid4

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_DISPATCH_LEASE_SECONDS = 120
_DISPATCH_KEY = "wechat:agent:dispatch:{}"
_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _binding_key(binding_id: UUID | str) -> str:
    return _DISPATCH_KEY.format(binding_id)


async def owns_binding_dispatch(binding_id: UUID | str, ownership_token: str) -> bool:
    """Return whether a queued task still owns this binding's active lease."""
    redis = await get_redis()
    return await redis.get(_binding_key(binding_id)) == ownership_token


async def release_binding_dispatch(
    binding_id: UUID | str, ownership_token: str
) -> None:
    """Release a queued/running wakeup only while this task owns its lease."""
    redis = await get_redis()
    await redis.eval(
        _RELEASE_IF_OWNER,
        1,
        _binding_key(binding_id),
        ownership_token,
    )


async def enqueue_binding(binding_id: UUID | str) -> bool:
    """Publish one process task unless a queued/running wakeup already owns it.

    Redis stores only a short-lived coalescing lease, never work state. Pending
    receipts and deliveries remain the durable source of truth and are scanned
    by recovery after a worker crash or an unavailable Redis/broker.
    """
    redis = await get_redis()
    ownership_token = str(uuid4())
    key = _binding_key(binding_id)
    acquired = await redis.set(
        key,
        ownership_token,
        ex=_DISPATCH_LEASE_SECONDS,
        nx=True,
    )
    if not acquired:
        return False

    try:
        from app.tasks.wechat_agent import process_binding_task

        await asyncio.to_thread(
            process_binding_task.apply_async,
            args=[str(binding_id), ownership_token],
        )
    except Exception:
        try:
            await redis.eval(_RELEASE_IF_OWNER, 1, key, ownership_token)
        except Exception:
            logger.warning(
                "Failed to release WeChat Agent dispatch lease for %s after publish failure",
                binding_id,
                exc_info=True,
            )
        raise
    return True
