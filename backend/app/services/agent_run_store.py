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

from tortoise.transactions import in_transaction
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
from app.models.agent import Message, MessageRole, MessageRoundRole

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


async def park_run_waiting(
    run: AgentRun,
    *,
    tool_call_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    round_id: UUID,
    round_index: int,
    iteration_index: int,
    worker_payload: dict[str, Any] | None = None,
) -> AgentRun:
    """Atomically persist a pending interaction before its event is published."""
    updated_at = now_utc()
    updates: dict[str, Any] = {
        "status": AgentRunStatus.WAITING,
        "pending_tool_call_id": tool_call_id,
        "pending_tool_name": tool_name,
        "pending_tool_input": tool_input,
        "pending_tool_round_id": round_id,
        "pending_tool_round_index": round_index,
        "pending_tool_iteration_index": iteration_index,
        "updated_at": updated_at,
    }
    if worker_payload is not None:
        updates["worker_payload"] = worker_payload
    updated = await AgentRun.filter(id=run.id, status=AgentRunStatus.RUNNING).update(
        **updates
    )
    if updated != 1:
        raise RuntimeError("AgentRun is no longer running")

    run.status = AgentRunStatus.WAITING
    run.pending_tool_call_id = tool_call_id
    run.pending_tool_name = tool_name
    run.pending_tool_input = tool_input
    run.pending_tool_round_id = round_id
    run.pending_tool_round_index = round_index
    run.pending_tool_iteration_index = iteration_index
    run.updated_at = updated_at
    if worker_payload is not None:
        run.worker_payload = worker_payload
    await _write_state_cache(run.id, AgentRunStatus.WAITING)
    return run


def validate_user_answers(
    pending_input: dict[str, Any] | None,
    answers: Any,
) -> None:
    """Validate answer keys, required fields, and option values."""
    if not isinstance(pending_input, dict):
        raise ValueError("pending questions are invalid")
    questions = pending_input.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("pending questions are invalid")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")

    question_ids: set[str] = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("pending questions are invalid")
        question_id = item.get("id")
        question = item.get("question")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("pending questions are invalid")
        if question_id in question_ids:
            raise ValueError("pending questions are invalid")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("pending questions are invalid")
        options = item.get("options")
        if options is not None and (
            not isinstance(options, list)
            or any(
                not isinstance(option, str) or not option.strip() for option in options
            )
        ):
            raise ValueError("pending questions are invalid")
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ValueError("pending questions are invalid")
        question_ids.add(question_id)

    unknown = set(answers) - question_ids
    if unknown:
        raise ValueError("answers contain an unknown question id")

    for item in questions:
        question_id = item["id"]
        has_answer = question_id in answers
        answer = answers.get(question_id)
        if item.get("required", True) and (
            not has_answer
            or answer is None
            or (isinstance(answer, str) and not answer.strip())
            or (isinstance(answer, (list, dict)) and not answer)
        ):
            raise ValueError(f"answer required for {question_id}")
        options = item.get("options")
        if has_answer and isinstance(options, list) and options:
            if not isinstance(answer, str) or answer not in options:
                raise ValueError(f"answer is not a valid option for {question_id}")


async def submit_user_answers(
    run_id: UUID,
    *,
    tool_call_id: str,
    answers: dict[str, Any],
) -> AgentRun | None:
    """Consume one waiting interaction and persist its matching tool result.

    The row lock makes duplicate submissions harmless: only the first caller
    can change ``waiting`` to ``queued`` and create the tool-result message.
    """
    result_content = json.dumps({"answers": answers}, ensure_ascii=False, default=str)
    async with in_transaction() as conn:
        run = await (
            AgentRun.filter(id=run_id).using_db(conn).select_for_update().first()
        )
        if (
            run is None
            or run.status != AgentRunStatus.WAITING
            or run.pending_tool_call_id != tool_call_id
            or getattr(run, "pending_tool_name", None) != "ask_user"
        ):
            return None

        validate_user_answers(run.pending_tool_input, answers)
        await Message.create(
            conversation_id=run.conversation_id,
            role=MessageRole.TOOL,
            content=result_content,
            tool_call_id=tool_call_id,
            tool_name=run.pending_tool_name,
            round_id=run.pending_tool_round_id or run.active_round_id,
            round_index=run.pending_tool_round_index or 0,
            round_role=MessageRoundRole.TOOL_RESULT,
            is_round_canonical=False,
            iteration_index=run.pending_tool_iteration_index,
            using_db=conn,
        )

        worker_payload = dict(run.worker_payload or {})
        exclude_ids = list(worker_payload.get("exclude_message_ids") or [])
        if run.canonical_message_id:
            canonical_id = str(run.canonical_message_id)
            if canonical_id not in exclude_ids:
                exclude_ids.append(canonical_id)
        worker_payload["exclude_message_ids"] = exclude_ids
        history_override = list(worker_payload.get("history_override") or [])
        history_override.append(
            {
                "role": "tool",
                "content": result_content,
                "round_id": str(run.pending_tool_round_id or run.active_round_id),
                "round_index": run.pending_tool_round_index or 0,
                "round_role": "tool_result",
                "is_round_canonical": False,
                "iteration_index": run.pending_tool_iteration_index,
                "tool_call_id": tool_call_id,
                "tool_name": run.pending_tool_name or "ask_user",
            }
        )
        worker_payload["history_override"] = history_override
        worker_payload["resume_tool_result"] = {
            "tool_call_id": tool_call_id,
            "tool_name": "ask_user",
            "tool_display_name": "Ask user",
            "result": result_content,
            "is_error": False,
        }
        if run.pending_tool_round_index is not None:
            worker_payload["first_round_index"] = run.pending_tool_round_index + 1

        run.status = AgentRunStatus.QUEUED
        run.worker_payload = worker_payload
        run.pending_tool_call_id = None
        run.pending_tool_name = None
        run.pending_tool_input = None
        run.pending_tool_round_id = None
        run.pending_tool_round_index = None
        run.pending_tool_iteration_index = None
        run.updated_at = now_utc()
        await run.save(
            using_db=conn,
            update_fields=[
                "status",
                "worker_payload",
                "pending_tool_call_id",
                "pending_tool_name",
                "pending_tool_input",
                "pending_tool_round_id",
                "pending_tool_round_index",
                "pending_tool_iteration_index",
                "updated_at",
            ],
        )

    await _write_state_cache(run_id, AgentRunStatus.QUEUED)
    return run


async def stop_waiting_run(run_id: UUID) -> AgentRun | None:
    """Atomically stop a run that is waiting for user answers."""
    async with in_transaction() as conn:
        run = await (
            AgentRun.filter(id=run_id).using_db(conn).select_for_update().first()
        )
        if run is None or run.status != AgentRunStatus.WAITING:
            return None
        run.status = AgentRunStatus.STOPPED
        run.finished_at = now_utc()
        run.updated_at = now_utc()
        run.pending_tool_call_id = None
        run.pending_tool_name = None
        run.pending_tool_input = None
        run.pending_tool_round_id = None
        run.pending_tool_round_index = None
        run.pending_tool_iteration_index = None
        await run.save(
            using_db=conn,
            update_fields=[
                "status",
                "finished_at",
                "updated_at",
                "pending_tool_call_id",
                "pending_tool_name",
                "pending_tool_input",
                "pending_tool_round_id",
                "pending_tool_round_index",
                "pending_tool_iteration_index",
            ],
        )
    await _write_state_cache(run_id, AgentRunStatus.STOPPED)
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
        try:
            await refresh_run_lock(run_id, conversation_id)
        except Exception:
            logger.warning("Failed to refresh run lease for %s", run_id, exc_info=True)
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


async def has_pending_inputs(
    run_id: UUID, kind: AgentRunInputKind | None = None
) -> bool:
    """Whether the run has queued inputs (optionally of one kind)."""
    qs = AgentRunInput.filter(run_id=run_id, status=AgentRunInputStatus.QUEUED)
    if kind is not None:
        qs = qs.filter(kind=kind)
    return await qs.exists()
