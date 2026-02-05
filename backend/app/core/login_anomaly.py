"""
Login anomaly detection service.

Detects unusual login patterns such as:
- Login from a new IP address
- Login from a new user agent (device/browser)
"""

import logging
from typing import Optional
from uuid import UUID

from app.core.redis import get_redis
from app.core.timezone import now_utc

logger = logging.getLogger(__name__)

# Redis key prefixes
LOGIN_IPS_KEY = "login:ips:{user_id}"
LOGIN_UAS_KEY = "login:uas:{user_id}"

# How many recent IPs/UAs to track per user
MAX_TRACKED_IPS = 10
MAX_TRACKED_UAS = 10

# How long to keep login history (30 days)
LOGIN_HISTORY_TTL = 30 * 24 * 60 * 60


async def check_login_anomaly(
    user_id: UUID,
    ip_address: str,
    user_agent: Optional[str] = None,
) -> tuple[bool, dict]:
    """
    Check if the current login is anomalous.

    Args:
        user_id: The user's ID
        ip_address: The IP address of the login request
        user_agent: The user agent string (optional)

    Returns:
        tuple[bool, dict]: (is_anomaly, details)
            - is_anomaly: True if this login appears unusual
            - details: Dictionary with anomaly details
    """
    try:
        redis = await get_redis()
    except Exception as e:
        logger.warning(f"Redis not available, skipping login anomaly check: {e}")
        return False, {}

    is_anomaly = False
    details: dict = {
        "new_ip": False,
        "new_user_agent": False,
        "ip_address": ip_address,
        "user_agent": user_agent or "Unknown",
        "login_time": now_utc().isoformat(),
    }

    try:
        # Check IP address
        ip_key = LOGIN_IPS_KEY.format(user_id=str(user_id))
        known_ips: set[str] = await redis.smembers(ip_key)  # type: ignore[misc]

        if known_ips and ip_address not in known_ips:
            # New IP detected
            is_anomaly = True
            details["new_ip"] = True
            details["known_ips_count"] = len(known_ips)

        # Check user agent if provided
        if user_agent:
            ua_key = LOGIN_UAS_KEY.format(user_id=str(user_id))
            known_uas: set[str] = await redis.smembers(ua_key)  # type: ignore[misc]

            # Normalize user agent for comparison (take first 200 chars)
            ua_normalized = user_agent[:200]

            if known_uas and ua_normalized not in known_uas:
                # New user agent detected
                is_anomaly = True
                details["new_user_agent"] = True
                details["known_uas_count"] = len(known_uas)

    except Exception as e:
        logger.error(f"Error checking login anomaly: {e}")
        return False, {}

    return is_anomaly, details


async def record_login(
    user_id: UUID,
    ip_address: str,
    user_agent: Optional[str] = None,
) -> None:
    """
    Record a successful login for anomaly detection.

    Args:
        user_id: The user's ID
        ip_address: The IP address of the login request
        user_agent: The user agent string (optional)
    """
    try:
        redis = await get_redis()
    except Exception:
        return

    try:
        # Record IP address
        ip_key = LOGIN_IPS_KEY.format(user_id=str(user_id))
        await redis.sadd(ip_key, ip_address)  # type: ignore[misc]
        await redis.expire(ip_key, LOGIN_HISTORY_TTL)

        # Trim to max tracked IPs if needed
        ip_count: int = await redis.scard(ip_key)  # type: ignore[misc]
        if ip_count > MAX_TRACKED_IPS:
            # Remove random old IPs (Redis SPOP)
            to_remove = ip_count - MAX_TRACKED_IPS
            for _ in range(to_remove):
                await redis.spop(ip_key)  # type: ignore[misc]

        # Record user agent if provided
        if user_agent:
            ua_key = LOGIN_UAS_KEY.format(user_id=str(user_id))
            ua_normalized = user_agent[:200]
            await redis.sadd(ua_key, ua_normalized)  # type: ignore[misc]
            await redis.expire(ua_key, LOGIN_HISTORY_TTL)

            # Trim to max tracked UAs if needed
            ua_count: int = await redis.scard(ua_key)  # type: ignore[misc]
            if ua_count > MAX_TRACKED_UAS:
                to_remove = ua_count - MAX_TRACKED_UAS
                for _ in range(to_remove):
                    await redis.spop(ua_key)  # type: ignore[misc]

    except Exception as e:
        logger.error(f"Error recording login: {e}")


async def clear_login_history(user_id: UUID) -> None:
    """
    Clear login history for a user (e.g., when password is changed).

    Args:
        user_id: The user's ID
    """
    try:
        redis = await get_redis()
    except Exception:
        return

    try:
        ip_key = LOGIN_IPS_KEY.format(user_id=str(user_id))
        ua_key = LOGIN_UAS_KEY.format(user_id=str(user_id))
        await redis.delete(ip_key, ua_key)
    except Exception as e:
        logger.error(f"Error clearing login history: {e}")
