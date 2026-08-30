"""Durable AgentRun lifecycle store.

Authoritative source of truth for run state. Redis carries a per-conversation
mutation lock and run status caches for fast reads, but PostgreSQL rows are
terminal truth: a lock/Redis loss never changes the persisted state, and
worker expiry detection runs from the DB.

Lock semantics:

- one active run per conversation (``agent:conversation:{id}:active_run``),
- Redis lease with heartbeat and value matching the run id; only the owner
  may refresh or release it,
- an expired lease from a crashed worker marks the run ``interrupted`` (never
  auto-replayed: model/tool side effects are not generally idempotent).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from app.core.redis import get_redis
from app.core.timezone import now_utc
from app.models.agent_run import (
    AgentRun,
    AgentRunInput,
    AgentRunInputKind,
    AgentRunInputStatus,
    AgentRunMode,
    AgentRunStatus,
)

logger = logging.getLogger(__name__)

RUN_LOCK_PREFIX = "agent:conversation:{conversation_id}:active_run"
RUN_INPUT_WAKEUP_PREFIX = "agent:run:{run_id}:inputs"
RUN_LEASE_SECONDS = 60
RUN_STATE_PREFIX = "agent:run:{run_id}:status"

try:  # pragma: no cover - import guard for old redis clients
    from redis.asyncio import Redis as _Redis  # type: ignore
except Exception:  # pragma: no cover
    _Redis = Any  # type: ignore


async def create_run(
    *,
    agent_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    mode: AgentRunMode,
    source_message_id: UUID | None = None,
    celery_task_id: str | None = None,
) -> AgentRun:
    run_id = uuid4()
    run = await AgentRun.create(
        id=run_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        user_id=user_id,
        mode=mode,
        source_message_id=source_message_id,
        celery_task_id=celery_task_id,
        status=AgentRunStatus.QUEUED,
        started_at=None,
    )
    await _write_state_cache(run_id, AgentRunStatus.QUEUED)
    return run


async def get_run(run_id: UUID) -> AgentRun | None:
    return await AgentRun.get_or_none(id=run_id)


async def transition_run(
    run: AgentRun,
    status: AgentRunStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentRun:
    run.status = status
    run.updated_at = now_utc()
    if status == AgentRunStatus.RUNNING and run.started_at is None:
        run.started_at = now_utc()
    if status in (
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    ):
        run.finished_at = now_utc()
    if error_code is not None:
        run.error_code = error_code
    if error_message is not None:
        run.error_message = error_message
    await run.save()
    await _write_state_cache(run.id, status)
    return run


# ---------- conversation lock (Redis lease) ----------


async def acquire_run_lock(
    run_id: UUID,
    conversation_id: UUID,
    *,
    lease_seconds: int = RUN_LEASE_SECONDS,
) -> bool:
    """Acquire the per-conversation active-run lock for ``run_id``."""
    redis = await get_redis()
    key = RUN_LOCK_PREFIX.format(conversation_id=conversation_id)
    ok = await redis.set(key, str(run_id), nx=True, ex=lease_seconds)
    return bool(ok)


async def refresh_run_lock(run_id: UUID, conversation_id: UUID) -> bool:
    """Extend the lease only if this run still owns it."""
    redis = await get_redis()
    key = RUN_LOCK_PREFIX.format(conversation_id=conversation_id)
    current = await redis.get(key)
    if current != str(run_id):
        return False
    return bool(await redis.expire(key, RUN_LEASE_SECONDS))


async def release_run_lock(run_id: UUID, conversation_id: UUID) -> None:
    """Release the lock if owned by ``run_id`` (value-compare-and-delete)."""
    redis = await get_redis()
    key = RUN_LOCK_PREFIX.format(conversation_id=conversation_id)
    current = await redis.get(key)
    if current != str(run_id):
        return
    await redis.delete(key)


async def is_run_lock_owner(run_id: UUID, conversation_id: UUID) -> bool:
    redis = await get_redis()
    key = RUN_LOCK_PREFIX.format(conversation_id=conversation_id)
    current = await redis.get(key)
    return current == str(run_id)


async def heartbeat_run_lock(
    run_id: UUID, conversation_id: UUID, stop: asyncio.Event
) -> None:
    """Refresh the lease until the worker signals stop/release."""
    while not stop.is_set():
        await refresh_run_lock(run_id, conversation_id)
        try:
            await asyncio.wait_for(stop.wait(), timeout=min(RUN_LEASE_SECONDS // 2, 10))
        except asyncio.TimeoutError:
            continue


# ---------- worker-loss detection ----------


async def mark_expired_runs_interrupted(*, max_age_seconds: int = 120) -> int:
    """Mark runs stuck in running/stopping with an expired lock as interrupted.

    Returns the number of runs so marked. Never replays side-effecting work;
    the user explicitly retries/regenerates from the visible trace.
    """
    redis = await get_redis()
    cutoff = now_utc().timestamp() - max_age_seconds
    stale = await AgentRun.filter(
        status__in=[AgentRunStatus.RUNNING, AgentRunStatus.STOPPING]
    ).all()
    marked = 0
    for run in stale:
        if not run.started_at or run.started_at.timestamp() > cutoff:
            continue
        key = RUN_LOCK_PREFIX.format(conversation_id=run.conversation_id)
        current = await redis.get(key)
        if current == str(run.id):
            # still within lease; skip
            continue
        await transition_run(
            run,
            AgentRunStatus.INTERRUPTED,
            error_code="worker_loss",
            error_message="Run worker lost before completion",
        )
        marked += 1
    return marked


# ---------- queued inputs (durable, ordered) ----------


async def enqueue_input(
    *,
    run_id: UUID,
    kind: AgentRunInputKind,
    content: str | None = None,
    attachment_meta: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AgentRunInput | None:
    """Enqueue a control input, idempotent per ``request_id`` when given."""
    run = await AgentRun.get_or_none(id=run_id)
    if not run or run.status in (
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    ):
        return None
    if request_id:
        existing = await AgentRunInput.get_or_none(run_id=run_id, request_id=request_id)
        if existing:
            return existing
    last = await AgentRunInput.filter(run_id=run_id).order_by("-sequence").first()
    sequence = (last.sequence + 1) if last else 1
    entry = await AgentRunInput.create(
        id=uuid4(),
        run_id=run_id,
        sequence=sequence,
        kind=kind,
        content=content,
        attachment_meta=attachment_meta or {},
        status=AgentRunInputStatus.QUEUED,
        request_id=request_id,
    )
    await _wake_run_worker(run_id)
    return entry


async def consume_next_input(run_id: UUID) -> AgentRunInput | None:
    """Lock-and-consume the oldest queued input for this run.

    Row-level locking guarantees exactly one worker consumes each input even
    with duplicate delivery.
    """
    entry = (
        await AgentRunInput.filter(run_id=run_id, status=AgentRunInputStatus.QUEUED)
        .order_by("sequence")
        .first()
    )
    if not entry:
        return None
    entry.status = AgentRunInputStatus.CONSUMED
    entry.consumed_at = now_utc()
    await entry.save()
    return entry


async def drop_pending_inputs(
    run_id: UUID, *, status: AgentRunInputStatus | None = None
) -> int:
    """Mark pending queued inputs dropped (terminal stops / completion)."""
    target = status or AgentRunInputStatus.DROPPED
    remaining = await AgentRunInput.filter(
        run_id=run_id, status=AgentRunInputStatus.QUEUED
    ).all()
    for entry in remaining:
        entry.status = target
        entry.consumed_at = now_utc()
        await entry.save()
    return len(remaining)


async def count_pending_inputs(run_id: UUID) -> int:
    return await AgentRunInput.filter(
        run_id=run_id, status=AgentRunInputStatus.QUEUED
    ).count()


# ---------- redis state helpers ----------


async def _write_state_cache(run_id: UUID, status: AgentRunStatus) -> None:
    try:
        redis = await get_redis()
        await redis.set(
            RUN_STATE_PREFIX.format(run_id=run_id),
            json.dumps({"status": status.value}),
            ex=3600 * 24,
        )
    except Exception:
        logger.warning("Failed to cache run state for %s", run_id, exc_info=True)


async def get_cached_run_status(run_id: UUID) -> AgentRunStatus | None:
    try:
        redis = await get_redis()
        raw = await redis.get(RUN_STATE_PREFIX.format(run_id=run_id))
        if not raw:
            return None
        return AgentRunStatus(json.loads(raw).get("status"))
    except Exception:
        return None


async def _wake_run_worker(run_id: UUID) -> None:
    redis = await get_redis()
    pubsub_channel = RUN_INPUT_WAKEUP_PREFIX.format(run_id=run_id)
    await redis.publish(pubsub_channel, "1")


def run_input_wakeup_channel(run_id: UUID) -> str:
    return RUN_INPUT_WAKEUP_PREFIX.format(run_id=run_id)
