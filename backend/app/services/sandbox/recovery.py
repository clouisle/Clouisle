"""Bounded, coalesced node-local recovery and explicit workspace-loss reporting."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

from app.core.config import settings

from .affinity import sandbox_worker_queue
from .audit import log_sandbox_task_event
from .models import SandboxBinding, SandboxTaskStatus
from .result_store import TERMINAL_STATUSES, sandbox_result_store
from .session_store import sandbox_session_store
from .worker_registry import WorkerPresence, sandbox_worker_registry

StopRequested = Callable[[], Awaitable[bool]]
_notices: ContextVar[list[dict] | None] = ContextVar(
    "sandbox_reset_notices", default=None
)
_observed: ContextVar[dict[str, SandboxBinding] | None] = ContextVar(
    "sandbox_observed_bindings", default=None
)
_scope: ContextVar[tuple[float | None, StopRequested | None]] = ContextVar(
    "sandbox_execution_scope", default=(None, None)
)


class WorkspaceReset(ValueError):
    code = "WORKSPACE_RESET"

    def __init__(self, notice: dict):
        self.notice = notice
        super().__init__(notice["message"])


class SandboxUnavailable(RuntimeError):
    code = "SANDBOX_UNAVAILABLE"


class SandboxGuardLost(RuntimeError):
    def __init__(self, message: str, code: str = "EXECUTION_UNCERTAIN"):
        self.code = code
        super().__init__(message)


@contextmanager
def capture_workspace_resets() -> Iterator[list[dict]]:
    notices: list[dict] = []
    token = _notices.set(notices)
    observed_token = _observed.set({})
    try:
        yield notices
    finally:
        _observed.reset(observed_token)
        _notices.reset(token)


def record_workspace_reset(notice: dict) -> None:
    notices = _notices.get()
    if notices is not None and not any(
        n.get("session_id") == notice.get("session_id")
        and n.get("generation") == notice.get("generation")
        for n in notices
    ):
        notices.append(notice)


@contextmanager
def sandbox_execution_scope(
    deadline_at: float | None = None, stop_requested: StopRequested | None = None
) -> Iterator[None]:
    previous_deadline, previous_stop = _scope.get()
    if previous_deadline is not None:
        deadline_at = (
            min(previous_deadline, deadline_at)
            if deadline_at is not None
            else previous_deadline
        )
    token = _scope.set((deadline_at, stop_requested or previous_stop))
    try:
        yield
    finally:
        _scope.reset(token)


def bounded_deadline(deadline_at: float) -> float:
    scope_deadline, _ = _scope.get()
    return (
        min(deadline_at, scope_deadline) if scope_deadline is not None else deadline_at
    )


async def check_scope(deadline_at: float) -> None:
    _, stop = _scope.get()
    if stop is not None and await stop():
        raise SandboxGuardLost("Sandbox operation cancelled", "CANCELLED")
    if time.time() >= bounded_deadline(deadline_at):
        raise SandboxGuardLost(
            "Sandbox operation deadline expired", "DEADLINE_EXCEEDED"
        )


def observe_binding(session_id: str, binding: SandboxBinding | None) -> None:
    if binding is not None:
        values = dict(_observed.get() or {})
        values[session_id] = binding
        _observed.set(values)


def observed_binding(session_id: str) -> SandboxBinding | None:
    return (_observed.get() or {}).get(session_id)


def reset_notice(
    session_id: str, before: SandboxBinding, after: SandboxBinding
) -> dict:
    return {
        "code": "WORKSPACE_RESET",
        "session_id": session_id,
        "generation": after.generation,
        "previous_generation": before.generation,
        "previous_worker_id": before.worker_id,
        "worker_id": after.worker_id,
        "workspace_id": after.workspace_id,
        "message": "Sandbox workspace was reset after its worker/storage could not be recovered. Old paths, files, edit snapshots and process handles are lost. Do not blindly replay commands whose execution is uncertain. Existing authorized assets can be rematerialized in the new workspace.",
    }


def report_reset(
    session_id: str, before: SandboxBinding | None, after: SandboxBinding
) -> dict | None:
    if before is None or before.generation == after.generation:
        return None
    notice = reset_notice(session_id, before, after)
    record_workspace_reset(notice)
    observe_binding(session_id, after)
    return notice


def presence_matches(
    binding: SandboxBinding, presence: WorkerPresence | None, *, instance: bool = True
) -> bool:
    return bool(
        presence
        and presence.ready
        and presence.worker_id == binding.worker_id
        and presence.node_id == binding.node_id
        and presence.storage_id == binding.storage_id
        and (not instance or presence.instance_id == binding.instance_id)
    )


async def _prepare(
    session_id: str,
    expected: SandboxBinding,
    token: str,
    candidate: WorkerPresence,
    workspace_id: str,
    restore: bool,
    deadline_at: float,
) -> bool:
    from app.tasks.sandbox import prepare_sandbox_workspace_task

    await check_scope(deadline_at)
    job_id = str(uuid4())
    await sandbox_result_store.create_queued_result(job_id, deadline_at=deadline_at)
    prepare_sandbox_workspace_task.apply_async(
        args=[
            session_id,
            job_id,
            expected.model_dump(mode="json"),
            token,
            candidate.model_dump(mode="json"),
            workspace_id,
            restore,
            deadline_at,
        ],
        queue=sandbox_worker_queue(candidate.worker_id),
    )
    try:
        while True:
            await check_scope(deadline_at)
            status = await sandbox_result_store.get_status(job_id)
            if status in TERMINAL_STATUSES:
                result = await sandbox_result_store.get_result(job_id)
                return bool(result and result.success)
            live = await sandbox_worker_registry.get(candidate.worker_id)
            if not live or live.instance_id != candidate.instance_id or not live.ready:
                existing = await sandbox_result_store.get_result(job_id)
                result = await sandbox_result_store.update_status(
                    job_id,
                    SandboxTaskStatus.FAILED,
                    error="Workspace preparation worker lost",
                    error_code="SANDBOX_UNAVAILABLE",
                )
                if (
                    existing is None or existing.status not in TERMINAL_STATUSES
                ) and result.status == SandboxTaskStatus.FAILED:
                    await log_sandbox_task_event(
                        job_id=job_id,
                        event="failed",
                        session_id=session_id,
                        source="workspace_prepare",
                        worker_id=candidate.worker_id,
                        error_code=result.error_code,
                    )
                return False
            await asyncio.sleep(
                min(
                    settings.SANDBOX_RECOVERY_POLL_SECONDS,
                    max(0, deadline_at - time.time()),
                )
            )
    except BaseException:
        existing = await sandbox_result_store.get_result(job_id)
        result = await sandbox_result_store.update_status(
            job_id,
            SandboxTaskStatus.CANCELLED,
            error="Workspace preparation cancelled",
        )
        if (
            existing is None or existing.status not in TERMINAL_STATUSES
        ) and result.status == SandboxTaskStatus.CANCELLED:
            await log_sandbox_task_event(
                job_id=job_id,
                event="cancelled",
                session_id=session_id,
                source="workspace_prepare",
                error_code=result.error_code,
            )
        raise


async def ensure_ready(
    session_id: str,
    deadline_at: float,
    *,
    force: bool = False,
    expected_binding: SandboxBinding | None = None,
) -> SandboxBinding:
    """Only a successful physical preparation may publish a new placement."""
    deadline_at = min(
        bounded_deadline(deadline_at),
        time.time() + settings.SANDBOX_WORKER_RECOVERY_SECONDS,
    )
    force_epoch: int | None = (
        expected_binding.epoch if expected_binding is not None else None
    )
    while True:
        await check_scope(deadline_at)
        if await sandbox_session_store.get(session_id) is None:
            raise ValueError("Sandbox session not found or expired")
        binding = await sandbox_session_store.get_binding(session_id)
        if force and binding is not None:
            if force_epoch is None:
                force_epoch = binding.epoch
            elif binding.epoch != force_epoch:
                force = False
        if binding is not None and binding.status == "READY" and not force:
            live = await sandbox_worker_registry.get(binding.worker_id)
            if presence_matches(binding, live):
                return binding
        candidates = await sandbox_worker_registry.list_ready()
        if binding is None and not candidates:
            await asyncio.sleep(
                min(
                    settings.SANDBOX_RECOVERY_POLL_SECONDS,
                    max(0, deadline_at - time.time()),
                )
            )
            continue
        initial = None
        if binding is None:
            candidate = random.choice(candidates)
            initial = SandboxBinding(
                worker_id=candidate.worker_id,
                instance_id=candidate.instance_id,
                node_id=candidate.node_id,
                storage_id=candidate.storage_id,
                workspace_id=session_id,
                status="RESETTING",
            )
        token = str(uuid4())
        acquired = await sandbox_session_store.acquire_recovery(
            session_id, binding, token, max(0.001, deadline_at - time.time()), initial
        )
        if acquired is None:
            await asyncio.sleep(
                min(
                    settings.SANDBOX_RECOVERY_POLL_SECONDS,
                    max(0, deadline_at - time.time()),
                )
            )
            continue
        try:
            recovered = await _recover_owned(
                session_id, acquired, token, deadline_at, first=binding is None
            )
            if recovered is not None:
                return recovered
        except BaseException:
            await sandbox_session_store.abandon_recovery(session_id, acquired, token)
            raise
        force = False


async def _recover_owned(
    session_id: str,
    binding: SandboxBinding,
    token: str,
    deadline_at: float,
    *,
    first: bool,
) -> SandboxBinding | None:
    # Reserve a bounded part of the original budget for a fresh-worker ack.
    remaining = max(0, deadline_at - time.time())
    local_deadline = deadline_at - min(5.0, remaining / 3)
    local_failed = False
    while not local_failed:
        await check_scope(deadline_at)
        live = await sandbox_worker_registry.get(binding.worker_id)
        if presence_matches(binding, live, instance=False):
            if await _prepare(
                session_id,
                binding,
                token,
                live,
                binding.workspace_id,
                not first,
                deadline_at,
            ):
                refreshed = binding.model_copy(
                    update={
                        "instance_id": live.instance_id,
                        "epoch": binding.epoch + 1,
                        "status": "READY",
                        "recovery_id": None,
                        "recovery_started_at": None,
                    }
                )
                current = await sandbox_worker_registry.get(live.worker_id)
                if not presence_matches(refreshed, current):
                    if not await sandbox_session_store.recovery_matches(
                        session_id, binding, token
                    ):
                        return None
                    local_failed = time.time() >= local_deadline
                    continue
                await check_scope(deadline_at)
                if await sandbox_session_store.commit_recovery(
                    session_id, binding, token, refreshed
                ):
                    return refreshed
                return None
            current = await sandbox_worker_registry.get(binding.worker_id)
            local_failed = (
                presence_matches(binding, current, instance=False)
                and current.instance_id == live.instance_id
            )
            if (
                current is not None
                and current.ready
                and current.storage_id != binding.storage_id
            ):
                local_failed = True
            if not local_failed and time.time() >= local_deadline:
                break
        elif first or time.time() >= local_deadline:
            break
        else:
            await asyncio.sleep(
                min(
                    settings.SANDBOX_RECOVERY_POLL_SECONDS,
                    max(0, local_deadline - time.time()),
                )
            )
    if binding.reset_count >= settings.SANDBOX_SESSION_MAX_RESETS:
        await sandbox_session_store.abandon_recovery(session_id, binding, token)
        raise SandboxUnavailable(
            "Sandbox workspace is unavailable and its reset limit was reached"
        )
    resetting = await sandbox_session_store.mark_resetting(session_id, binding, token)
    if resetting is None:
        return None
    binding = resetting
    while True:
        await check_scope(deadline_at)
        candidates = await sandbox_worker_registry.list_ready()
        candidates.sort(
            key=lambda p: (
                p.node_id != binding.node_id,
                p.storage_id != binding.storage_id,
                p.worker_id,
            )
        )
        for candidate in candidates:
            await check_scope(deadline_at)
            workspace_id = str(uuid4())
            if not await _prepare(
                session_id, binding, token, candidate, workspace_id, False, deadline_at
            ):
                continue
            replacement = SandboxBinding(
                worker_id=candidate.worker_id,
                instance_id=candidate.instance_id,
                node_id=candidate.node_id,
                storage_id=candidate.storage_id,
                epoch=binding.epoch + 1,
                generation=binding.generation + 1,
                workspace_id=workspace_id,
                reset_count=binding.reset_count + 1,
            )
            current = await sandbox_worker_registry.get(candidate.worker_id)
            if not presence_matches(replacement, current):
                if not await sandbox_session_store.recovery_matches(
                    session_id, binding, token
                ):
                    return None
                continue
            await check_scope(deadline_at)
            if await sandbox_session_store.commit_recovery(
                session_id, binding, token, replacement
            ):
                return replacement
            return None
        await asyncio.sleep(
            min(
                settings.SANDBOX_RECOVERY_POLL_SECONDS,
                max(0, deadline_at - time.time()),
            )
        )


async def guard_job(
    job_id: str,
    session_id: str | None,
    expected: SandboxBinding | None,
    deadline_at: float | None,
) -> None:
    if deadline_at is not None and time.time() >= deadline_at:
        raise SandboxGuardLost("Sandbox job deadline expired", "DEADLINE_EXCEEDED")
    if await sandbox_result_store.get_status(job_id) in TERMINAL_STATUSES:
        raise SandboxGuardLost("Sandbox job is already terminal", "CANCELLED")
    if session_id:
        current = await sandbox_session_store.get_binding(session_id)
        if expected is None or not expected.matches(current):
            raise SandboxGuardLost(
                "Sandbox execution lost its session binding; execution may have occurred"
            )
        live = await sandbox_worker_registry.get(expected.worker_id)
        if not presence_matches(expected, live):
            raise SandboxGuardLost(
                "Sandbox worker lease was lost; execution may have occurred"
            )
