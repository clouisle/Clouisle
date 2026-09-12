"""Contracts for the bounded aggregation fan-out.

The limiter exists so one statistics request cannot hold every slot of the
shared Tortoise pool while its own queries queue behind it. Two properties
matter and neither is obvious from the call sites:

- the configured budget must be usable, so a zero or negative value is
  rejected at configuration time instead of deadlocking or raising later;
- the budget applies per query, not per batch, or N concurrent callers would
  reach ``N x batch_size`` queries and defeat it.
"""

import asyncio

import pytest
from pydantic import ValidationError

from app.core import db_limits
from app.core.config import Settings


@pytest.mark.parametrize("value", [0, -1, -10])
def test_aggregate_concurrency_rejects_non_positive_values(value):
    """Zero permits would deadlock every aggregate; a negative count raises."""
    with pytest.raises(ValidationError):
        Settings(DB_AGGREGATE_CONCURRENCY=value)


@pytest.mark.parametrize("value", [1, 4, 16])
def test_aggregate_concurrency_accepts_positive_values(value):
    assert Settings(DB_AGGREGATE_CONCURRENCY=value).DB_AGGREGATE_CONCURRENCY == value


@pytest.mark.anyio
async def test_run_bounded_returns_the_awaited_value(monkeypatch):
    monkeypatch.setattr(db_limits, "_AGGREGATE_SEMAPHORE", asyncio.Semaphore(1))

    async def _value():
        return "ok"

    assert await db_limits.run_bounded(_value()) == "ok"


@pytest.mark.anyio
async def test_run_bounded_limits_concurrency_per_query(monkeypatch):
    """The permit is taken per coroutine, so a batch cannot exceed the budget."""
    monkeypatch.setattr(db_limits, "_AGGREGATE_SEMAPHORE", asyncio.Semaphore(2))

    in_flight = 0
    peak = 0

    async def _work():
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1

    # Six independent queries, together with a one-permit-held batch scope this
    # would have observed all six at once.
    await asyncio.gather(*(db_limits.run_bounded(_work()) for _ in range(6)))

    assert peak == 2


@pytest.mark.anyio
async def test_run_bounded_releases_the_permit_when_the_query_raises(monkeypatch):
    """A failing aggregate must not leak its permit and stall the endpoint."""
    monkeypatch.setattr(db_limits, "_AGGREGATE_SEMAPHORE", asyncio.Semaphore(1))

    async def _boom():
        raise RuntimeError("query failed")

    with pytest.raises(RuntimeError, match="query failed"):
        await db_limits.run_bounded(_boom())

    # With the permit leaked this would hang rather than complete.
    async def _ok():
        return 1

    assert await asyncio.wait_for(db_limits.run_bounded(_ok()), timeout=1) == 1
