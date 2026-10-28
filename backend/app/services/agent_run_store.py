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
from datetime import datetime
from typing import TYPE_CHECKING, Any
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

if TYPE_CHECKING:
    from app.models.tool_approval import ToolExecution

logger = logging.getLogger(__name__)

RUN_LOCK_PREFIX = "agent:conversation:{conversation_id}:active_run"
RUN_INPUT_WAKEUP_PREFIX = "agent:run:{run_id}:inputs"
RUN_LEASE_SECONDS = 60
RUN_STATE_PREFIX = "agent:run:{run_id}:status"

try:  # pragma: no cover - import guard for old redis clients
    from redis.asyncio import Redis as _Redis  # type: ignore
except Exception:  # pragma: no cover
    _Redis = Any  # type: ignore

_OBSERVABILITY_PROGRESS_TASKS: set[asyncio.Task[Any]] = set()


async def _record_terminal_observability(run: AgentRun) -> None:
    if run.status not in {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    }:
        return
    try:
        from app.models.agent import Agent
        from app.services.observability_v2 import agent_terminal_summary, record_run

        async def persist_summary() -> None:
            details, messages = await asyncio.gather(
                Agent.filter(id=run.agent_id)
                .limit(1)
                .values("name", "team_id", "team__name"),
                Message.filter(id=run.canonical_message_id)
                .limit(1)
                .values("model_used", "token_usage")
                if run.canonical_message_id
                else asyncio.sleep(0, result=[]),
            )
            await record_run(
                **agent_terminal_summary(
                    run,
                    details[0] if details else {},
                    messages[0] if messages else {},
                )
            )

        await asyncio.wait_for(persist_summary(), timeout=0.15)
    except Exception:
        logger.debug("AgentRun telemetry write dropped for %s", run.id, exc_info=True)


def record_observability_progress(
    run_id: UUID,
    *,
    status: str | None = None,
    expected_status: str | None = None,
    started_at: datetime | None = None,
    message_started_at: datetime | None = None,
    first_token_ms: int | None = None,
) -> None:
    from app.services.observability_v2 import update_run_progress

    task = asyncio.create_task(
        update_run_progress(
            run_id,
            source="agent",
            status=status,
            expected_status=expected_status,
            started_at=started_at,
            message_started_at=message_started_at,
            first_token_ms=first_token_ms,
        )
    )
    _OBSERVABILITY_PROGRESS_TASKS.add(task)
    task.add_done_callback(_OBSERVABILITY_PROGRESS_TASKS.discard)


async def create_run(
    *,
    agent_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    mode: AgentRunMode,
    resource_name: str | None = None,
    team_id: str | None = None,
    source_message_id: UUID | None = None,
    celery_task_id: str | None = None,
    api_key_id: UUID | None = None,
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
        api_key_id=api_key_id,
        status=AgentRunStatus.QUEUED,
        started_at=None,
        submitted_at=now_utc(),
    )
    try:
        from app.services.observability_v2 import record_run

        await asyncio.wait_for(
            record_run(
                run_id=run.id,
                source="agent",
                resource_id=str(agent_id),
                resource_name=resource_name,
                team_id=team_id,
                team_name=None,
                status=AgentRunStatus.QUEUED.value,
                submitted_at=run.submitted_at,
                started_at=None,
                message_started_at=None,
                finished_at=None,
                total_duration_ms=None,
            ),
            timeout=0.05,
        )
    except Exception:
        logger.debug(
            "AgentRun submission telemetry dropped for %s", run.id, exc_info=True
        )
    await _write_state_cache(run_id, AgentRunStatus.QUEUED)
    return run


async def get_run(run_id: UUID) -> AgentRun | None:
    return await AgentRun.get_or_none(id=run_id)


def _transition_updates(
    run: AgentRun,
    status: AgentRunStatus,
    *,
    updated_at: datetime,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "status": status,
        "updated_at": updated_at,
    }
    if status == AgentRunStatus.RUNNING and run.started_at is None:
        updates["started_at"] = updated_at
    if status in (
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    ):
        updates["finished_at"] = updated_at
        updates["message_started_at"] = run.message_started_at
        updates["first_token_ms"] = run.first_token_ms
    if error_code is not None:
        updates["error_code"] = error_code
    if error_message is not None:
        updates["error_message"] = error_message
    return updates


def _apply_transition_updates(run: AgentRun, updates: dict[str, Any]) -> None:
    for field, value in updates.items():
        setattr(run, field, value)


async def transition_run_if_status(
    run: AgentRun,
    expected_status: AgentRunStatus,
    status: AgentRunStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentRun | None:
    """Transition only if the database row still has ``expected_status``.

    The conditional update closes lifecycle races with stop requests and other
    workers.  A ``None`` result means another actor won the transition.
    """
    updates = _transition_updates(
        run,
        status,
        updated_at=now_utc(),
        error_code=error_code,
        error_message=error_message,
    )
    changed = await AgentRun.filter(id=run.id, status=expected_status).update(**updates)
    if changed != 1:
        return None
    _apply_transition_updates(run, updates)
    await _write_state_cache(run.id, status)
    if status not in {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    }:
        record_observability_progress(
            run.id,
            status=status.value,
            expected_status=expected_status.value,
            started_at=run.started_at,
            message_started_at=run.message_started_at,
            first_token_ms=run.first_token_ms,
        )
    await _record_terminal_observability(run)
    return run


async def claim_queued_run(run_id: UUID) -> AgentRun | None:
    """Atomically claim a queued run for one worker."""
    claimed_at = now_utc()
    async with in_transaction() as conn:
        run = await (
            AgentRun.filter(id=run_id, status=AgentRunStatus.QUEUED)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if run is None:
            return None
        run.status = AgentRunStatus.RUNNING
        run.updated_at = claimed_at
        update_fields = ["status", "updated_at"]
        if run.started_at is None:
            run.started_at = claimed_at
            update_fields.append("started_at")
        await run.save(using_db=conn, update_fields=update_fields)
    await _write_state_cache(run_id, AgentRunStatus.RUNNING)
    record_observability_progress(
        run.id,
        status=AgentRunStatus.RUNNING.value,
        expected_status=AgentRunStatus.QUEUED.value,
        started_at=run.started_at,
    )
    return run


async def transition_run(
    run: AgentRun,
    status: AgentRunStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentRun:
    expected_status = run.status.value
    updated_at = now_utc()
    updates = _transition_updates(
        run,
        status,
        updated_at=updated_at,
        error_code=error_code,
        error_message=error_message,
    )
    _apply_transition_updates(run, updates)
    await run.save(update_fields=list(updates))
    await _write_state_cache(run.id, status)
    if status not in {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    }:
        record_observability_progress(
            run.id,
            status=status.value,
            expected_status=expected_status,
            started_at=run.started_at,
            message_started_at=run.message_started_at,
            first_token_ms=run.first_token_ms,
        )
    await _record_terminal_observability(run)
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
        "message_started_at": run.message_started_at,
        "first_token_ms": run.first_token_ms,
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
    record_observability_progress(
        run.id,
        status=AgentRunStatus.WAITING.value,
        expected_status=AgentRunStatus.RUNNING.value,
        started_at=run.started_at,
        message_started_at=run.message_started_at,
        first_token_ms=run.first_token_ms,
    )
    return run


def validate_user_answers(
    pending_input: dict[str, Any] | None,
    answers: Any,
    *,
    skipped: bool = False,
) -> None:
    """Validate answer keys, required fields, and explicit skips."""
    if not isinstance(pending_input, dict):
        raise ValueError("pending questions are invalid")
    questions = pending_input.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("pending questions are invalid")
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    if not isinstance(skipped, bool):
        raise ValueError("skipped must be a boolean")

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

    if skipped:
        if answers:
            raise ValueError("skipped answers must be empty")
        return

    unknown = set(answers) - question_ids
    if unknown:
        raise ValueError("answers contain an unknown question id")

    for item in questions:
        question_id = item["id"]
        has_answer = question_id in answers
        answer = answers.get(question_id)
        options = item.get("options")
        is_required = item.get("required", True)
        if is_required and (
            not has_answer
            or answer is None
            or (isinstance(answer, str) and not answer.strip())
            or (isinstance(answer, (list, dict)) and not answer)
        ):
            raise ValueError(f"answer required for {question_id}")
        if has_answer and isinstance(options, list) and options:
            if not is_required and (
                answer is None or (isinstance(answer, str) and not answer.strip())
            ):
                continue
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError(f"answer must be a non-empty string for {question_id}")


async def submit_user_answers(
    run_id: UUID,
    *,
    tool_call_id: str,
    answers: dict[str, Any],
    skipped: bool = False,
) -> AgentRun | None:
    """Consume one waiting interaction and persist its matching tool result.

    The row lock makes duplicate submissions harmless: only the first caller
    can change ``waiting`` to ``queued`` and create the tool-result message.
    """
    result_payload: dict[str, Any] = {"answers": answers}
    if skipped:
        result_payload["skipped"] = True
    result_content = json.dumps(result_payload, ensure_ascii=False, default=str)
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

        validate_user_answers(run.pending_tool_input, answers, skipped=skipped)
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
        worker_payload["created_message_count"] = (
            int(worker_payload.get("created_message_count", 2)) + 1
        )
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
    record_observability_progress(
        run_id,
        status=AgentRunStatus.QUEUED.value,
        expected_status=AgentRunStatus.WAITING.value,
        started_at=run.started_at,
        message_started_at=run.message_started_at,
        first_token_ms=run.first_token_ms,
    )
    return run


_APPROVAL_TOOL_ERRORS: dict[str, str] = {
    "rejected": "Tool execution was rejected by an approver.",
    "expired": "Tool execution approval expired before it could run.",
    "binding_changed": (
        "Tool execution approval is no longer valid because its binding changed."
    ),
    "revoked": "Tool execution was revoked before it could run.",
    "cancelled": "Tool execution was cancelled before it could run.",
    "policy_denied": "Tool execution was denied by policy.",
}


def _enum_text(value: Any) -> str | None:
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else None


def _approval_resume_error(execution: "ToolExecution") -> str | None:
    status = _enum_text(execution.status)
    if status == "ready":
        return None
    if status != "cancelled":
        return None
    return _APPROVAL_TOOL_ERRORS.get(_enum_text(execution.cancel_reason) or "")


async def _append_approval_tool_result_locked(
    run: AgentRun,
    conn: Any,
    payload: dict[str, Any],
    *,
    tool_call_id: str,
    tool_name: str,
    tool_display_name: str,
    display_result: str,
    llm_result: str,
    is_error: bool,
    round_id: UUID | None,
    round_index: int | None,
    iteration_index: int | None,
) -> dict[str, Any]:
    """Persist one tool result for a resumed approval and update the payload."""
    resolved_round_id = round_id or run.active_round_id
    resolved_round_index = round_index or 0
    await Message.create(
        conversation_id=run.conversation_id,
        role=MessageRole.TOOL,
        content=display_result,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        round_id=resolved_round_id,
        round_index=resolved_round_index,
        round_role=MessageRoundRole.TOOL_RESULT,
        is_round_canonical=False,
        iteration_index=iteration_index,
        using_db=conn,
    )

    exclude_ids = list(payload.get("exclude_message_ids") or [])
    if run.canonical_message_id:
        canonical_id = str(run.canonical_message_id)
        if canonical_id not in exclude_ids:
            exclude_ids.append(canonical_id)
    payload["exclude_message_ids"] = exclude_ids

    history_override = list(payload.get("history_override") or [])
    history_override.append(
        {
            "role": "tool",
            "content": llm_result,
            "round_id": str(resolved_round_id) if resolved_round_id else "",
            "round_index": resolved_round_index,
            "round_role": "tool_result",
            "is_round_canonical": False,
            "iteration_index": iteration_index,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
        }
    )
    payload["history_override"] = history_override
    payload["resume_tool_result"] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_display_name": tool_display_name,
        "result": display_result,
        "is_error": is_error,
    }
    payload["first_round_index"] = resolved_round_index + 1
    payload["created_message_count"] = int(payload.get("created_message_count", 2)) + 1
    payload.pop("resume_tool_approval", None)
    return payload


async def queue_agent_run_approval_resume(
    execution: "ToolExecution",
) -> AgentRun | None:
    """Queue the waiting AgentRun that owns this tool execution.

    ``ready`` queues a marker so the worker executes the original pending call
    before resuming the model. A cancelled execution queues a tool error so the
    model continues without the side effect. ``run_stopped`` never resumes.
    """
    if _enum_text(execution.run_kind) != "agent" or execution.run_id is None:
        return None
    if execution.tool_call_id is None:
        return None
    error_message = _approval_resume_error(execution)
    status = _enum_text(execution.status)
    if status not in {"ready", "cancelled"}:
        return None
    if status == "cancelled" and error_message is None:
        return None

    async with in_transaction() as conn:
        run = (
            await AgentRun.filter(id=execution.run_id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        if (
            run is None
            or run.status != AgentRunStatus.WAITING
            or not run.pending_tool_call_id
            or run.pending_tool_call_id != execution.tool_call_id
            or not run.pending_tool_name
        ):
            return None

        payload = dict(run.worker_payload or {})
        tool_name = run.pending_tool_name
        tool_display_name = str(payload.get("pending_tool_display_name") or tool_name)
        round_id = run.pending_tool_round_id or run.active_round_id
        round_index = run.pending_tool_round_index
        iteration_index = run.pending_tool_iteration_index

        if status == "ready":
            payload["resume_tool_approval"] = {
                "execution_id": str(execution.id),
                "tool_call_id": execution.tool_call_id,
                "tool_name": tool_name,
                "tool_display_name": tool_display_name,
                "round_id": str(round_id) if round_id else None,
                "round_index": round_index,
                "iteration_index": iteration_index,
            }
        else:
            assert error_message is not None
            payload = await _append_approval_tool_result_locked(
                run,
                conn,
                payload,
                tool_call_id=execution.tool_call_id,
                tool_name=tool_name,
                tool_display_name=tool_display_name,
                display_result=json.dumps({"error": error_message}, ensure_ascii=False),
                llm_result=json.dumps({"error": error_message}, ensure_ascii=False),
                is_error=True,
                round_id=round_id,
                round_index=round_index,
                iteration_index=iteration_index,
            )

        run.status = AgentRunStatus.QUEUED
        run.worker_payload = payload
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

    await _write_state_cache(run.id, AgentRunStatus.QUEUED)
    record_observability_progress(
        run.id,
        status=AgentRunStatus.QUEUED.value,
        expected_status=AgentRunStatus.WAITING.value,
        started_at=run.started_at,
        message_started_at=run.message_started_at,
        first_token_ms=run.first_token_ms,
    )
    return run


async def queue_agent_run_resume_if_approval_terminal(
    run_id: UUID,
) -> AgentRun | None:
    """Close the park/decision race: queue a WAITING run whose approval is done.

    An approval can be decided while the worker is still running, before the
    run row becomes WAITING. The decision scheduler then correctly finds no
    waiting run. This post-park recheck finds the execution for the persisted
    pending call and queues the matching resume (marker or tool error) if the
    execution already reached a terminal approval state.
    """
    run = await get_run(run_id)
    if (
        run is None
        or run.status != AgentRunStatus.WAITING
        or not run.pending_tool_call_id
    ):
        return None
    pending_input = run.pending_tool_input
    if (
        not isinstance(pending_input, dict)
        or pending_input.get("interaction_kind") != "tool_approval"
    ):
        # ask_user / other durable interactions are not tool approvals.
        return None
    from app.models.tool_approval import ToolExecution

    execution = (
        await ToolExecution.filter(
            run_kind="agent",
            run_id=run.id,
            tool_call_id=run.pending_tool_call_id,
        )
        .order_by("-created_at")
        .first()
    )
    if execution is None:
        return None
    return await queue_agent_run_approval_resume(execution)


async def record_resumed_tool_result(
    run_id: UUID,
    *,
    tool_call_id: str,
    tool_name: str,
    tool_display_name: str,
    display_result: str,
    llm_result: str,
    is_error: bool,
    round_id: UUID | None,
    round_index: int | None,
    iteration_index: int | None,
) -> dict[str, Any] | None:
    """Persist the original call's result and return the updated worker payload."""
    async with in_transaction() as conn:
        run = (
            await AgentRun.filter(id=run_id).using_db(conn).select_for_update().first()
        )
        if run is None or run.status != AgentRunStatus.RUNNING:
            return None
        payload = await _append_approval_tool_result_locked(
            run,
            conn,
            dict(run.worker_payload or {}),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_display_name=tool_display_name,
            display_result=display_result,
            llm_result=llm_result,
            is_error=is_error,
            round_id=round_id,
            round_index=round_index,
            iteration_index=iteration_index,
        )
        run.worker_payload = payload
        run.updated_at = now_utc()
        await run.save(using_db=conn, update_fields=["worker_payload", "updated_at"])
    return payload


async def schedule_agent_run_approval_resume(
    execution: "ToolExecution",
) -> AgentRun | None:
    """Queue and dispatch the approval resume; failures mark the run failed."""
    run = await queue_agent_run_approval_resume(execution)
    if run is None:
        return None
    try:
        payload = run.worker_payload
        if not isinstance(payload, dict):  # pragma: no cover - defensive
            raise RuntimeError("run resume payload is missing")
        from app.services.agent_submission import dispatch_run

        await dispatch_run(payload, run)
    except Exception as exc:
        logger.exception("Failed to dispatch approval resume for run %s", run.id)
        await transition_run_if_status(
            run,
            AgentRunStatus.QUEUED,
            AgentRunStatus.FAILED,
            error_code="enqueue_failed",
            error_message=str(exc),
        )
        current = await AgentRun.get_or_none(id=run.id)
        return current
    return run


async def stop_waiting_run(run_id: UUID) -> AgentRun | None:
    """Atomically stop a run that is waiting for user answers."""
    async with in_transaction() as conn:
        run = await (
            AgentRun.filter(id=run_id).using_db(conn).select_for_update().first()
        )
        if run is None or run.status != AgentRunStatus.WAITING:
            return None
        stopped_at = now_utc()
        run.status = AgentRunStatus.STOPPED
        run.finished_at = stopped_at
        run.updated_at = stopped_at
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
    await _record_terminal_observability(run)
    await _cancel_pending_tool_executions(run_id)
    return run


async def _cancel_pending_tool_executions(run_id: UUID) -> None:
    """Stop is terminal: an outstanding approval must not stay actionable."""
    from app.models.tool_approval import ExecutionRunKind
    from app.schemas.tool_approval import ToolExecutionCancelReason
    from app.services import tool_approvals

    await tool_approvals.cancel_pending_for_run(
        run_kind=ExecutionRunKind.AGENT,
        run_id=run_id,
        reason=ToolExecutionCancelReason.RUN_STOPPED,
    )


async def stop_queued_run(run_id: UUID) -> AgentRun | None:
    """Atomically stop a run that is queued before worker execution starts."""
    async with in_transaction() as conn:
        run = await (
            AgentRun.filter(id=run_id).using_db(conn).select_for_update().first()
        )
        if run is None or run.status != AgentRunStatus.QUEUED:
            return None
        stopped_at = now_utc()
        run.status = AgentRunStatus.STOPPED
        run.finished_at = stopped_at
        run.updated_at = stopped_at
        await run.save(
            using_db=conn,
            update_fields=["status", "finished_at", "updated_at"],
        )
    await _write_state_cache(run_id, AgentRunStatus.STOPPED)
    await _record_terminal_observability(run)
    await _cancel_pending_tool_executions(run_id)
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
        transitioned = await transition_run_if_status(
            run,
            run.status,
            AgentRunStatus.INTERRUPTED,
            error_code="worker_loss",
            error_message="Run worker lost before completion",
        )
        if transitioned is not None:
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
    """Best-effort latency hint; the input row is already durable in PostgreSQL.

    A Redis outage must not fail ``enqueue_input``: the worker also polls queued
    inputs, so the only cost of a missed publish is a later wake-up.
    """
    try:
        redis = await get_redis()
        pubsub_channel = RUN_INPUT_WAKEUP_PREFIX.format(run_id=run_id)
        await redis.publish(pubsub_channel, "1")
    except Exception:
        logger.warning("Failed to wake run worker for %s", run_id, exc_info=True)


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
