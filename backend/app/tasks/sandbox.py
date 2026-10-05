"""Fenced Celery sandbox execution and physical workspace lifecycle tasks."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

from celery import shared_task

from app.services.error_messages import resolve_user_visible_error
from app.services.sandbox.affinity import (
    sandbox_instance_id,
    sandbox_node_id,
    sandbox_storage_id,
    sandbox_worker_id,
)
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import (
    SandboxBinding,
    SandboxExecutionMetadata,
    SandboxJob,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.recovery import SandboxGuardLost, guard_job, presence_matches
from app.services.sandbox.result_store import sandbox_result_store
from app.services.sandbox.session_store import STANDALONE_ROUND, sandbox_session_store
from app.services.sandbox.worker_registry import WorkerPresence, sandbox_worker_registry
from app.services.sandbox.workspace import SandboxWorkspaceManager

logger = logging.getLogger(__name__)


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def _local_identity(
    worker_id: str, instance_id: str, node_id: str, storage_id: str
) -> bool:
    return (worker_id, instance_id, node_id, storage_id) == (
        sandbox_worker_id(),
        sandbox_instance_id(),
        sandbox_node_id(),
        sandbox_storage_id(),
    )


async def _failure(
    job_id: str, exc: Exception, *, code: str | None = None
) -> SandboxResult:
    existing = await sandbox_result_store.get_result(job_id)
    metadata = existing.metadata if existing else SandboxExecutionMetadata()
    metadata.mark_completed(datetime.now(UTC))
    error_code = code or getattr(exc, "code", None)
    if isinstance(exc, FileNotFoundError) and str(exc).startswith(
        "Sandbox workspace and checkpoint are missing:"
    ):
        error_code = "WORKSPACE_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        error_code = "DEADLINE_EXCEEDED"
    error = (
        str(exc)
        if error_code
        else resolve_user_visible_error(str(exc), fallback_key="tool_execution_failed")
    )
    if error_code == "EXECUTION_UNCERTAIN":
        error += " Execution may have occurred; do not blindly replay the command."
    return await sandbox_result_store.update_status(
        job_id,
        SandboxTaskStatus.CANCELLED
        if error_code == "CANCELLED"
        else SandboxTaskStatus.FAILED,
        metadata=metadata,
        success=False,
        error_code=error_code,
        error=error,
    )


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def run_sandbox_job_task(self, job_payload: dict) -> dict:
    async def _run() -> dict:
        job_id = job_payload["job_id"]
        try:
            job = SandboxJob.model_validate(job_payload)
            if job.deadline_at is None:
                raise SandboxGuardLost(
                    "Sandbox message has no execution deadline", "DEADLINE_EXCEEDED"
                )
            if job.session_id:
                if (
                    await sandbox_gateway.get_session_workspace(
                        job.session_id,
                        agent_id=job_payload.get("session_agent_id"),
                        team_id=job_payload.get("session_team_id"),
                    )
                    is None
                ):
                    raise ValueError("Sandbox session not found or expired")
                if job.binding is None or not _local_identity(
                    job.binding.worker_id,
                    job.binding.instance_id,
                    job.binding.node_id,
                    job.binding.storage_id,
                ):
                    raise SandboxGuardLost(
                        "Sandbox queued message belongs to an obsolete worker instance",
                        "JOB_OBSOLETE",
                    )
            await guard_job(job_id, job.session_id, job.binding, job.deadline_at)
            if not await sandbox_result_store.claim_execution(job_id, job.deadline_at):
                return {"job_id": job_id, "skipped": "duplicate_or_terminal"}
            manager = SandboxManager()
            result = await manager.execute(
                job,
                session_id=job.session_id,
                session_agent_id=job_payload.get("session_agent_id"),
                session_team_id=job_payload.get("session_team_id"),
            )
        except SandboxGuardLost as exc:
            existing = await sandbox_result_store.get_result(job_id)
            # A message rejected before it starts is obsolete, not an uncertain replay.
            code = exc.code
            if code == "EXECUTION_UNCERTAIN" and (
                existing is None or existing.metadata.started_at is None
            ):
                code = "JOB_OBSOLETE"
            result = await _failure(job_id, exc, code=code)
        except Exception as exc:
            logger.exception("Sandbox job execution failed: %s", exc)
            result = await _failure(job_id, exc)
        return {
            "job_id": result.job_id,
            "status": result.status,
            "success": result.success,
        }

    return _get_worker_loop().run_until_complete(_run())


async def _lifecycle_binding(
    session_id: str,
    expected: dict | None,
    deadline_at: float | None,
    *,
    allow_expired: bool = False,
) -> SandboxBinding | None:
    # Old/unversioned lifecycle messages are never upgraded or forwarded.
    if expected is None or deadline_at is None or time.time() >= deadline_at:
        return None
    binding = SandboxBinding.model_validate(expected)
    if not _local_identity(
        binding.worker_id, binding.instance_id, binding.node_id, binding.storage_id
    ):
        return None
    current = await sandbox_session_store.get_binding(session_id)
    if not binding.matches(current):
        return None
    if not presence_matches(
        binding, await sandbox_worker_registry.get(binding.worker_id)
    ):
        return None
    if not allow_expired and await sandbox_session_store.get(session_id) is None:
        return None
    return binding


async def prepare_workspace(
    session_id: str,
    job_id: str,
    expected: dict,
    recovery_id: str,
    candidate_payload: dict,
    workspace_id: str,
    restore: bool,
    deadline_at: float,
) -> dict:
    try:
        binding = SandboxBinding.model_validate(expected)
        candidate = WorkerPresence.model_validate(candidate_payload)
        if not _local_identity(
            candidate.worker_id,
            candidate.instance_id,
            candidate.node_id,
            candidate.storage_id,
        ):
            raise SandboxGuardLost(
                "Workspace preparation targets an obsolete worker", "JOB_OBSOLETE"
            )

        async def validate():
            await guard_job(job_id, None, None, deadline_at)
            if not await sandbox_session_store.recovery_matches(
                session_id, binding, recovery_id
            ):
                raise SandboxGuardLost(
                    "Workspace preparation recovery lease expired", "JOB_OBSOLETE"
                )
            live = await sandbox_worker_registry.get(candidate.worker_id)
            if (
                not live
                or not live.ready
                or (live.instance_id, live.node_id, live.storage_id)
                != (candidate.instance_id, candidate.node_id, candidate.storage_id)
            ):
                raise SandboxGuardLost(
                    "Workspace preparation worker lease lost", "JOB_OBSOLETE"
                )
            session = await sandbox_session_store.get(session_id)
            if session is None:
                raise ValueError("Sandbox session not found or expired")
            return session

        await validate()
        if not await sandbox_result_store.claim_execution(job_id, deadline_at):
            return {"job_id": job_id, "skipped": "duplicate_or_terminal"}
        workspace_manager = SandboxWorkspaceManager()
        async with workspace_manager.session_lock(
            workspace_id, deadline_at=deadline_at, guard=validate
        ):
            session = await validate()
            if restore:
                if (candidate.worker_id, candidate.node_id, candidate.storage_id) != (
                    binding.worker_id,
                    binding.node_id,
                    binding.storage_id,
                ) or workspace_id != binding.workspace_id:
                    raise ValueError(
                        "Workspace restore must use its original disk identity"
                    )
                previous = await sandbox_session_store.get_workspace_round(session_id)
                active = await sandbox_session_store.get_active_round(session_id)
                interrupted = previous is not None and previous not in (
                    active,
                    STANDALONE_ROUND,
                )
                workspace_manager.restore_session(
                    workspace_id,
                    allow_empty=session.disk_usage_bytes == 0,
                    force=interrupted,
                )
            else:
                # First generation may use its logical ID; resets never reuse data.
                if workspace_id != session_id and (
                    workspace_manager.get_session_root(workspace_id).exists()
                    or workspace_manager.checkpoints.checkpoint_path(
                        workspace_id
                    ).exists()
                ):
                    raise ValueError("Fresh workspace namespace already exists")
                workspace_manager.prepare_session(workspace_id)
            await validate()
            metadata = SandboxExecutionMetadata()
            metadata.mark_completed(datetime.now(UTC))
            result = await sandbox_result_store.save_result(
                SandboxResult(
                    job_id=job_id,
                    status=SandboxTaskStatus.COMPLETED,
                    success=True,
                    result={"prepared": True, "workspace_id": workspace_id},
                    metadata=metadata,
                    deadline_at=deadline_at,
                )
            )
            return {"job_id": job_id, "success": result.success}
    except Exception as exc:
        result = await _failure(job_id, exc)
        return {"job_id": job_id, "success": result.success}


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def prepare_sandbox_workspace_task(
    self,
    session_id: str,
    job_id: str,
    expected: dict,
    recovery_id: str,
    candidate_payload: dict,
    workspace_id: str,
    restore: bool,
    deadline_at: float,
) -> dict:
    return _get_worker_loop().run_until_complete(
        prepare_workspace(
            session_id,
            job_id,
            expected,
            recovery_id,
            candidate_payload,
            workspace_id,
            restore,
            deadline_at,
        )
    )


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def cleanup_sandbox_session_task(
    self,
    session_id: str,
    expired_only: bool = False,
    expected: dict | None = None,
    deadline_at: float | None = None,
) -> dict:
    async def _run() -> dict:
        binding = await _lifecycle_binding(
            session_id, expected, deadline_at, allow_expired=True
        )
        if binding is None:
            return {"session_id": session_id, "skipped": "obsolete_binding"}
        workspace_manager = SandboxWorkspaceManager()
        async with workspace_manager.session_lock(
            binding.workspace_id, deadline_at=deadline_at
        ):
            if (
                await _lifecycle_binding(
                    session_id, expected, deadline_at, allow_expired=True
                )
                is None
            ):
                return {"session_id": session_id, "skipped": "obsolete_binding"}
            if await sandbox_session_store.get_active_round(session_id) is not None:
                return {"session_id": session_id, "skipped": "active_round"}
            if expired_only and await sandbox_session_store.get(session_id) is not None:
                return {"session_id": session_id, "skipped": "retention_refreshed"}
            # Tombstone first, so no late consumer can write this physical workspace.
            if not await sandbox_session_store.delete(
                session_id, expected_binding=binding, expired_only=expired_only
            ):
                return {"session_id": session_id, "skipped": "retention_refreshed"}
            workspace_manager.delete_session(binding.workspace_id)
        return {"session_id": session_id, "cleaned": True}

    return _get_worker_loop().run_until_complete(_run())


async def checkpoint_session(
    session_id: str,
    job_id: str,
    round_id: str,
    expected: dict | None = None,
    deadline_at: float | None = None,
) -> dict:
    try:
        binding = await _lifecycle_binding(session_id, expected, deadline_at)
        if binding is None:
            raise SandboxGuardLost(
                "Checkpoint belongs to an obsolete binding", "JOB_OBSOLETE"
            )
        await guard_job(job_id, session_id, binding, deadline_at)
        if not await sandbox_result_store.claim_execution(job_id, deadline_at):
            return {"job_id": job_id, "skipped": "duplicate_or_terminal"}
        workspace_manager = SandboxWorkspaceManager()
        async with workspace_manager.session_lock(
            binding.workspace_id,
            deadline_at=deadline_at,
            guard=lambda: guard_job(job_id, session_id, binding, deadline_at),
        ):
            await guard_job(job_id, session_id, binding, deadline_at)
            session = await sandbox_session_store.get(session_id)
            if session is None:
                raise ValueError("Sandbox session not found or expired")
            active_round = await sandbox_session_store.get_active_round(session_id)
            if active_round is not None and active_round != round_id:
                raise ValueError("Sandbox checkpoint belongs to a superseded round")
            previous = await sandbox_session_store.get_workspace_round(session_id)
            interrupted = previous is not None and previous not in (
                round_id,
                STANDALONE_ROUND,
            )
            if interrupted or session.disk_usage_bytes > 0:
                workspace_manager.restore_session(
                    binding.workspace_id, allow_empty=False, force=interrupted
                )
            saved = workspace_manager.save_checkpoint(binding.workspace_id)
            await guard_job(job_id, session_id, binding, deadline_at)
            await sandbox_session_store.clear_workspace_round(
                session_id, expected_binding=binding
            )
            await sandbox_session_store.touch(session_id, expected_binding=binding)
            await sandbox_session_store.finish_round(
                session_id, round_id, expected_binding=binding
            )
            metadata = SandboxExecutionMetadata()
            metadata.mark_completed(datetime.now(UTC))
            result = await sandbox_result_store.save_result(
                SandboxResult(
                    job_id=job_id,
                    status=SandboxTaskStatus.COMPLETED,
                    success=True,
                    result={"checkpointed": saved},
                    session_id=session_id,
                    binding=binding,
                    deadline_at=deadline_at,
                    metadata=metadata,
                )
            )
            return {"job_id": job_id, "checkpointed": saved, "success": result.success}
    except Exception as exc:
        result = await _failure(job_id, exc)
        return {"job_id": job_id, "success": result.success}


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def checkpoint_sandbox_session_task(
    self,
    session_id: str,
    job_id: str,
    round_id: str,
    expected: dict | None = None,
    deadline_at: float | None = None,
) -> dict:
    return _get_worker_loop().run_until_complete(
        checkpoint_session(session_id, job_id, round_id, expected, deadline_at)
    )


@shared_task(bind=True, max_retries=0, ignore_result=True, queue="sandbox")
def evict_sandbox_session_task(
    self,
    session_id: str,
    cutoff: float,
    expected: dict | None = None,
    deadline_at: float | None = None,
) -> dict:
    async def _run() -> dict:
        binding = await _lifecycle_binding(session_id, expected, deadline_at)
        if binding is None:
            return {"session_id": session_id, "skipped": "obsolete_binding"}
        workspace_manager = SandboxWorkspaceManager()
        async with workspace_manager.session_lock(
            binding.workspace_id, deadline_at=deadline_at
        ):
            if await _lifecycle_binding(session_id, expected, deadline_at) is None:
                return {"session_id": session_id, "skipped": "obsolete_binding"}
            session = await sandbox_session_store.get(session_id)
            if session is None or session.last_accessed_at.timestamp() > cutoff:
                return {"session_id": session_id, "skipped": "not_idle"}
            if await sandbox_session_store.get_active_round(session_id) is not None:
                return {"session_id": session_id, "skipped": "active_round"}
            previous = await sandbox_session_store.get_workspace_round(session_id)
            if previous is not None and previous != STANDALONE_ROUND:
                workspace_manager.restore_session(
                    binding.workspace_id, allow_empty=False, force=True
                )
            # Recheck after checkpoint construction; a superseded workspace must not
            # delete or mutate metadata belonging to its replacement.
            saved = workspace_manager.save_checkpoint(binding.workspace_id)
            if (
                not saved
                or await _lifecycle_binding(session_id, expected, deadline_at) is None
            ):
                return {"session_id": session_id, "evicted": False}
            workspace_manager.cleanup_session(binding.workspace_id)
            await sandbox_session_store.clear_workspace_round(
                session_id, expected_binding=binding
            )
            await sandbox_session_store.mark_evicted(
                session_id, expected_binding=binding
            )
            return {"session_id": session_id, "evicted": True}

    return _get_worker_loop().run_until_complete(_run())


@shared_task(
    name="tasks.cleanup_expired_sandbox_sessions", ignore_result=True, queue="sandbox"
)
def cleanup_expired_sandbox_sessions_task() -> dict:
    async def _run() -> dict:
        return {
            "cleaned": await sandbox_gateway.cleanup_expired_sessions(),
            "cleanup_retried": await sandbox_gateway.retry_pending_expired_sessions(),
            "eviction_scheduled": await sandbox_gateway.evict_idle_sessions(),
            "eviction_retried": await sandbox_gateway.retry_pending_idle_evictions(),
        }

    return _get_worker_loop().run_until_complete(_run())
