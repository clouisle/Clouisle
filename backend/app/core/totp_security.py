"""
TOTP Security Module
Handles TOTP verification rate limiting and lockout
"""

from typing import Optional, Tuple

from app.core.redis import get_redis

# Redis key prefix
TOTP_ATTEMPTS_PREFIX = "totp:attempts:"

# Rate limiting settings
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 300  # 5 minutes
LOCKOUT_DURATION = 900  # 15 minutes


async def check_totp_rate_limit(user_id: str) -> Tuple[bool, Optional[int]]:
    """
    Check if user is rate limited for TOTP verification

    Args:
        user_id: User ID

    Returns:
        Tuple[bool, Optional[int]]: (is_locked, remaining_seconds)
    """
    r = await get_redis()
    key = f"{TOTP_ATTEMPTS_PREFIX}{user_id}"

    # Check if locked
    lockout_key = f"{key}:locked"
    ttl = await r.ttl(lockout_key)
    if ttl > 0:
        return True, ttl

    return False, None


async def record_totp_failure(user_id: str) -> Tuple[bool, int, Optional[int]]:
    """
    Record failed TOTP verification attempt

    Args:
        user_id: User ID

    Returns:
        Tuple[bool, int, Optional[int]]: (is_locked, remaining_attempts, lockout_seconds)
    """
    r = await get_redis()
    key = f"{TOTP_ATTEMPTS_PREFIX}{user_id}"

    # Increment attempts
    attempts = await r.incr(key)

    # Set expiration on first attempt
    if attempts == 1:
        await r.expire(key, ATTEMPT_WINDOW)

    remaining = max(0, MAX_ATTEMPTS - attempts)

    # Check if should lock
    if attempts >= MAX_ATTEMPTS:
        lockout_key = f"{key}:locked"
        await r.setex(lockout_key, LOCKOUT_DURATION, "1")
        return True, 0, LOCKOUT_DURATION

    return False, remaining, None


async def reset_totp_attempts(user_id: str):
    """
    Reset TOTP verification attempts (on successful verification)

    Args:
        user_id: User ID
    """
    r = await get_redis()
    key = f"{TOTP_ATTEMPTS_PREFIX}{user_id}"
    lockout_key = f"{key}:locked"

    await r.delete(key)
    await r.delete(lockout_key)
