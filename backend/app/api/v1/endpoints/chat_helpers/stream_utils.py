"""
Streaming utilities for chat.
"""

import time
from fastapi import Request


async def send_heartbeat_if_needed(
    last_event_time: float, heartbeat_interval: float, request: Request
) -> tuple[bool, float]:
    """
    Check if heartbeat should be sent and if client is still connected.

    Returns:
        tuple[bool, float]: (should_send_heartbeat, new_last_event_time)
    """
    current_time = time.time()
    time_since_last_event = current_time - last_event_time

    if time_since_last_event >= heartbeat_interval:
        # Check if client is still connected
        if await request.is_disconnected():
            return False, last_event_time
        return True, current_time

    return False, last_event_time
