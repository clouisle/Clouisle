"""Bounds how many aggregation queries a request may hold open at once.

Several statistics endpoints fan independent aggregates out with
``asyncio.gather``. Without a bound, one request can hold every slot of the
shared Tortoise pool (default ``maxsize`` 5) while its own remaining queries
queue behind it. Raising the pool is not an option: PostgreSQL
``max_connections`` is 100 and the default deployment already runs roughly 17
processes x pool.

The limiter is a single process-wide semaphore, shared by every fan-out, so the
configured number bounds the whole process rather than each endpoint
separately. It is applied per query — acquiring once around a ``gather`` of N
coroutines would let N queries run under a single permit and defeat the bound.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.core.config import settings

T = TypeVar("T")

_AGGREGATE_SEMAPHORE = asyncio.Semaphore(settings.DB_AGGREGATE_CONCURRENCY)


async def run_bounded(coro: Coroutine[Any, Any, T]) -> T:
    """Await ``coro`` holding one aggregation permit.

    Wrap each coroutine handed to an ``asyncio.gather`` so concurrent
    aggregates are limited rather than merely cooperative.
    """
    async with _AGGREGATE_SEMAPHORE:
        return await coro
