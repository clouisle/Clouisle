"""Suite-wide guards that keep unit tests off real infrastructure.

The suite runs without a Redis server or a Celery worker, both locally and in
CI, so code paths that reach for them exercise the "infrastructure is down"
branches. With production retry policies in place those branches dominated the
suite runtime: roughly 19s per Celery publish (result-backend retries) and 4s
per Redis command (redis-py retries with backoff) before the call finally
failed. The guards below keep the outcome of each call identical - the
operation still fails immediately - and only remove the waiting.

Tests that assert on infrastructure calls patch the call site themselves, which
takes precedence over these defaults.
"""

import os
from pathlib import Path

import pytest
import redis.asyncio as aioredis
from kombu.exceptions import OperationalError
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.core.celery import celery_app

# tiktoken downloads its BPE files on first use. Left to its default it caches
# them under the process temp dir, which pytest workers get a fresh copy of, so
# every run re-downloaded them (measured: 12s for one token-counting test).
# Pin a stable cache location; an explicit TIKTOKEN_CACHE_DIR still wins.
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path.home() / ".cache" / "tiktoken"))

_redis_init = aioredis.Redis.__init__


def _redis_init_without_retries(self, *args, **kwargs):
    """Build Redis clients that give up on the first connection failure.

    Unreachable Redis is the normal test condition, so retrying it only costs
    wall-clock time; callers already handle the raised error.
    """
    kwargs.setdefault("retry", Retry(NoBackoff(), 0))
    kwargs.setdefault("socket_connect_timeout", 0.05)
    kwargs.setdefault("socket_timeout", 0.05)
    _redis_init(self, *args, **kwargs)


def _send_task_without_broker(*args, **kwargs):
    """Fail publishes the way an unreachable broker does, but immediately."""
    raise OperationalError(
        "The test suite has no Celery broker; patch celery_app.send_task to "
        "assert that a task was published."
    )


@pytest.fixture(scope="session", autouse=True)
def _fail_fast_infrastructure():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(aioredis.Redis, "__init__", _redis_init_without_retries)
    monkeypatch.setattr(celery_app, "send_task", _send_task_without_broker)
    yield
    monkeypatch.undo()
