"""
Streaming utilities for chat.
"""

import asyncio
import time
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import TypeVar

from fastapi import Request

T = TypeVar("T")


class StreamIdleTimeoutError(RuntimeError):
    pass


async def send_heartbeat_if_needed(
    last_event_time: float, heartbeat_interval: float, request: Request
) -> tuple[bool, float]:
    """
    Check if heartbeat should be sent and if client is still connected.

    Returns:
        tuple[bool, float]: (should_continue, new_last_event_time)
    """
    current_time = time.time()
    time_since_last_event = current_time - last_event_time

    if time_since_last_event >= heartbeat_interval:
        if await request.is_disconnected():
            return False, last_event_time
        return True, current_time

    return True, last_event_time


async def iter_with_idle_timeout(
    iterable: AsyncIterable[T],
    timeout_seconds: float,
    activity_predicate: Callable[[T], bool] | None = None,
) -> AsyncIterator[T]:
    iterator = iterable.__aiter__()
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StreamIdleTimeoutError
        try:
            item = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            return
        except TimeoutError as e:
            raise StreamIdleTimeoutError from e
        if activity_predicate is None or activity_predicate(item):
            deadline = time.monotonic() + timeout_seconds
        yield item
