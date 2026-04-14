"""Redis-backed compression state helpers for circuit breakers."""

import logging
from typing import Literal

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

BreakerType = Literal["session_memory_extractor", "legacy_compact"]


async def is_breaker_open(
    *,
    breaker_type: BreakerType,
    conversation_id: str,
    failure_threshold: int,
    cooldown_seconds: int,
) -> bool:
    """
    Check if a circuit breaker is open for a given conversation.

    Returns True if the breaker is open (too many recent failures),
    False if closed (safe to proceed).
    """
    try:
        redis = await get_redis()
        if redis is None:
            return False

        key = f"compression_breaker:{breaker_type}:{conversation_id}"
        failure_count_str = await redis.get(key)
        if not failure_count_str:
            return False

        failure_count = int(failure_count_str)
        return failure_count >= failure_threshold
    except Exception as e:
        logger.warning(
            "Failed to check breaker state for %s conversation %s: %s",
            breaker_type,
            conversation_id,
            e,
        )
        return False


async def record_breaker_failure(
    *,
    breaker_type: BreakerType,
    conversation_id: str,
    cooldown_seconds: int,
) -> None:
    """
    Record a failure for a circuit breaker.

    Increments the failure count and sets TTL to the cooldown window.
    """
    try:
        redis = await get_redis()
        if redis is None:
            return

        key = f"compression_breaker:{breaker_type}:{conversation_id}"
        await redis.incr(key)
        await redis.expire(key, cooldown_seconds)
    except Exception as e:
        logger.warning(
            "Failed to record breaker failure for %s conversation %s: %s",
            breaker_type,
            conversation_id,
            e,
        )


async def reset_breaker(
    *,
    breaker_type: BreakerType,
    conversation_id: str,
) -> None:
    """
    Reset a circuit breaker after a successful operation.

    Clears the failure count.
    """
    try:
        redis = await get_redis()
        if redis is None:
            return

        key = f"compression_breaker:{breaker_type}:{conversation_id}"
        await redis.delete(key)
    except Exception as e:
        logger.warning(
            "Failed to reset breaker for %s conversation %s: %s",
            breaker_type,
            conversation_id,
            e,
        )
