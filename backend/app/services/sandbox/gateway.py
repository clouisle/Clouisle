"""Sandbox submission gateway: authorize, recover, fence, then dispatch once."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.config import settings
from app.core.i18n import t

from .affinity import sandbox_worker_queue
from .models import (
    SandboxExecutionMetadata,
    SandboxJob,
    SandboxResult,
    SandboxTaskStatus,
)
from .policies import sandbox_policy_engine
from .recovery import (
    SandboxGuardLost,
    SandboxUnavailable,
    WorkspaceReset,
    bounded_deadline,
    check_scope,
    ensure_ready,
    observe_binding,
    observed_binding,
    presence_matches,
    report_reset,
)
from .result_store import TERMINAL_STATUSES, sandbox_result_store
from .session_store import sandbox_session_store
from .worker_registry import sandbox_worker_registry

if TYPE_CHECKING:
    from .workspace import SandboxWorkspace, SandboxWorkspaceManager


class SandboxGateway:
    MAX_POLL_INTERVAL = 0.25
    _workspace_manager: "SandboxWorkspaceManager | None" = None

    @classmethod
    def _get_workspace_manager(cls) -> "SandboxWorkspaceManager":
        if cls._workspace_manager is None:
            from .workspace import SandboxWorkspaceManager

            cls._workspace_manager = SandboxWorkspaceManager()
        return cls._workspace_manager

    async def create_session(
        self,
        agent_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        ttl_hours: int = 24,
        conversation_id: str | None = None,
    ) -> str:
        if conversation_id:
            existing = await sandbox_session_store.get_by_conversation(conversation_id)
            if existing is not None and (
                existing.agent_id,
                existing.team_id,
                existing.user_id,
            ) == (agent_id, team_id, user_id):
                await sandbox_session_store.touch(existing.session_id)
                return existing.session_id
        session_id = str(uuid4())
        await sandbox_session_store.create(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            user_id=user_id,
            ttl_hours=ttl_hours,
        )
        return session_id

    async def get_session_workspace(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
    ) -> "SandboxWorkspace | None":
        session = await sandbox_session_store.get(session_id)
        if (
            session is None
            or (agent_id is not None and session.agent_id != agent_id)
            or (team_id is not None and session.team_id != team_id)
            or (user_id is not None and session.user_id != user_id)
        ):
            return None
        from .workspace import SandboxWorkspace

        binding = await sandbox_session_store.get_binding(session_id)
        observe_binding(session_id, binding)
        root = self._get_workspace_manager().get_session_root(
            binding.workspace_id if binding else session_id
        )
        return SandboxWorkspace(
            root=root,
            input_dir=root / "input",
            output_dir=root / "output",
            tmp_dir=root / "tmp",
            logs_dir=root / "logs",
        )

    async def cleanup_session(
        self, session_id: str, *, expired_only: bool = False
    ) -> None:
        from app.tasks.sandbox import cleanup_sandbox_session_task

        binding = await sandbox_session_store.get_binding(session_id)
        if binding is None:
            await sandbox_session_store.delete(session_id, expired_only=expired_only)
            return
        live = await sandbox_worker_registry.get(binding.worker_id)
        if binding.status != "READY" or not presence_matches(binding, live):
            if await sandbox_session_store.get_active_round(session_id) is None:
                await sandbox_session_store.delete(
                    session_id, expected_binding=binding, expired_only=expired_only
                )
            return
        cleanup_sandbox_session_task.apply_async(
            args=[
                session_id,
                expired_only,
                binding.model_dump(mode="json"),
                time.time() + settings.SANDBOX_CHECKPOINT_TIMEOUT_SECONDS,
            ],
            queue=sandbox_worker_queue(binding.worker_id),
        )

    async def cleanup_expired_sessions(self) -> int:
        ids = await sandbox_session_store.expired_session_ids()
        for session_id in ids:
            await self.cleanup_session(session_id, expired_only=True)
        return len(ids)

    async def begin_round(
        self, session_id: str, round_id: str, *, ttl_seconds: float
    ) -> None:
        await sandbox_session_store.begin_round(session_id, round_id, ttl_seconds)

    async def finish_round(self, session_id: str, round_id: str) -> None:
        from app.tasks.sandbox import checkpoint_sandbox_session_task

        before = await sandbox_session_store.get_binding(session_id)
        if before is None:
            await sandbox_session_store.finish_round(session_id, round_id)
            return
        deadline = bounded_deadline(
            time.time() + settings.SANDBOX_CHECKPOINT_TIMEOUT_SECONDS
        )
        binding = await ensure_ready(session_id, deadline)
        report_reset(session_id, before, binding)
        job_id = str(uuid4())
        await sandbox_result_store.create_queued_result(
            job_id, session_id=session_id, binding=binding, deadline_at=deadline
        )
        checkpoint_sandbox_session_task.apply_async(
            args=[
                session_id,
                job_id,
                round_id,
                binding.model_dump(mode="json"),
                deadline,
            ],
            queue=sandbox_worker_queue(binding.worker_id),
        )
        result = await self.await_result(
            job_id, timeout_seconds=max(0, deadline - time.time())
        )
        if result.success:
            return
        current = await sandbox_session_store.get_binding(session_id)
        if current is not None and current.generation != binding.generation:
            report_reset(session_id, binding, current)
            await sandbox_session_store.finish_round(
                session_id, round_id, expected_binding=current
            )
            return
        if result.error_code == "JOB_OBSOLETE":
            await sandbox_session_store.finish_round(
                session_id, round_id, expected_binding=current
            )
            return
        raise RuntimeError(result.error or "Sandbox checkpoint could not be saved")

    async def evict_idle_sessions(self) -> int:
        from app.tasks.sandbox import evict_sandbox_session_task

        cutoff = time.time() - settings.SANDBOX_WORKSPACE_IDLE_SECONDS
        scheduled = 0
        for session_id in await sandbox_session_store.idle_session_ids(cutoff):
            if await sandbox_session_store.get_active_round(session_id) is not None:
                continue
            binding = await sandbox_session_store.get_binding(session_id)
            if binding is None:
                await sandbox_session_store.mark_evicted(session_id)
                continue
            evict_sandbox_session_task.apply_async(
                args=[
                    session_id,
                    cutoff,
                    binding.model_dump(mode="json"),
                    time.time() + settings.SANDBOX_CHECKPOINT_TIMEOUT_SECONDS,
                ],
                queue=sandbox_worker_queue(binding.worker_id),
            )
            scheduled += 1
        return scheduled

    async def submit(
        self,
        job: SandboxJob,
        session_id: str | None = None,
        *,
        agent_id: str | None = None,
        team_id: str | None = None,
        deadline_at: float | None = None,
    ) -> str:
        from app.tasks.sandbox import run_sandbox_job_task

        sandbox_policy_engine.validate(job)
        deadline = bounded_deadline(
            deadline_at
            if deadline_at is not None
            else time.time() + job.limits.timeout_seconds + 5
        )
        if job.deadline_at is not None:
            deadline = min(deadline, job.deadline_at)
        await check_scope(deadline)
        binding = None
        if session_id:
            # Remember what the caller built paths against before descriptor lookup
            # observes the latest binding. Never run a pre-reset command in new data.
            before = observed_binding(
                session_id
            ) or await sandbox_session_store.get_binding(session_id)
            if (
                await self.get_session_workspace(
                    session_id, agent_id=agent_id, team_id=team_id
                )
                is None
            ):
                raise ValueError("Sandbox session not found or expired")
            binding = await ensure_ready(session_id, deadline)
            notice = report_reset(session_id, before, binding)
            if notice is not None:
                raise WorkspaceReset(notice)
            observe_binding(session_id, binding)
        job = job.model_copy(
            update={
                "session_id": session_id,
                "binding": binding,
                "deadline_at": deadline,
            }
        )
        await sandbox_result_store.create_queued_result(
            job.job_id,
            session_id=session_id,
            binding=binding,
            deadline_at=deadline,
            metadata=SandboxExecutionMetadata(queued_at=datetime.now(UTC)),
        )
        payload = job.model_dump(mode="json")
        payload["session_agent_id"] = agent_id
        payload["session_team_id"] = team_id
        run_sandbox_job_task.apply_async(
            args=[payload],
            queue=sandbox_worker_queue(binding.worker_id) if binding else "sandbox",
        )
        return job.job_id

    def _advance_poll_interval(self, poll_interval: float) -> float:
        return (
            min(self.MAX_POLL_INTERVAL, poll_interval * 2) if poll_interval > 0 else 0
        )

    async def get_result(self, job_id: str) -> SandboxResult | None:
        return await sandbox_result_store.get_result(job_id)

    async def _recover_result_binding(
        self, result: SandboxResult, deadline: float, *, force: bool = False
    ) -> None:
        if not result.session_id or not result.binding:
            return
        deadline = bounded_deadline(
            min(deadline, result.deadline_at)
            if result.deadline_at is not None
            else deadline
        )
        if time.time() >= deadline:
            return
        current = await sandbox_session_store.get_binding(result.session_id)
        try:
            binding = await ensure_ready(
                result.session_id,
                deadline,
                force=force and result.binding.matches(current),
                expected_binding=result.binding,
            )
        except (SandboxGuardLost, SandboxUnavailable) as exc:
            result.recovery = {"code": exc.code, "message": str(exc)}
            return
        notice = report_reset(result.session_id, result.binding, binding)
        if notice:
            result.recovery = notice

    async def await_result(
        self, job_id: str, *, timeout_seconds: float = 30.0, poll_interval: float = 0.02
    ) -> SandboxResult:
        try:
            return await self._await_result(
                job_id, timeout_seconds=timeout_seconds, poll_interval=poll_interval
            )
        except asyncio.CancelledError:
            await self.cancel(job_id)
            raise

    async def _await_result(
        self, job_id: str, *, timeout_seconds: float, poll_interval: float
    ) -> SandboxResult:
        deadline = bounded_deadline(time.time() + timeout_seconds)
        current_poll_interval = poll_interval
        context: SandboxResult | None = None
        while True:
            status = await sandbox_result_store.get_status(job_id)
            if status in TERMINAL_STATUSES:
                result = await sandbox_result_store.get_result(job_id)
                if result is not None:
                    if (
                        result.error_code
                        in {
                            "EXECUTION_UNCERTAIN",
                            "WORKSPACE_UNAVAILABLE",
                            "JOB_OBSOLETE",
                        }
                        and time.time() < deadline
                    ):
                        await self._recover_result_binding(
                            result,
                            deadline,
                            force=result.error_code == "WORKSPACE_UNAVAILABLE",
                        )
                    return result
            if context is None and status is not None:
                context = await sandbox_result_store.get_result(job_id)
                if context and context.deadline_at is not None:
                    deadline = min(deadline, context.deadline_at)
            try:
                await check_scope(deadline)
                if context and context.session_id and context.binding:
                    binding = await sandbox_session_store.get_binding(
                        context.session_id
                    )
                    live = await sandbox_worker_registry.get(context.binding.worker_id)
                    if not context.binding.matches(binding) or not presence_matches(
                        context.binding, live
                    ):
                        current = (
                            await sandbox_result_store.get_result(job_id) or context
                        )
                        started = current.metadata.started_at is not None
                        code = "EXECUTION_UNCERTAIN" if started else "JOB_OBSOLETE"
                        current.metadata.mark_completed(datetime.now(UTC))
                        final = await sandbox_result_store.update_status(
                            job_id,
                            SandboxTaskStatus.FAILED,
                            metadata=current.metadata,
                            success=False,
                            error_code=code,
                            error="Sandbox worker/binding was lost; execution may have occurred. Do not replay the command blindly."
                            if started
                            else "Sandbox queued job belongs to an obsolete worker binding and was not replayed.",
                        )
                        await self._recover_result_binding(final, deadline)
                        return final
            except SandboxGuardLost as exc:
                existing = await sandbox_result_store.get_result(job_id)
                metadata = existing.metadata if existing else SandboxExecutionMetadata()
                metadata.mark_completed(datetime.now(UTC))
                return await sandbox_result_store.update_status(
                    job_id,
                    SandboxTaskStatus.CANCELLED
                    if exc.code == "CANCELLED"
                    else SandboxTaskStatus.FAILED,
                    metadata=metadata,
                    success=False,
                    error_code=exc.code,
                    error=str(exc)
                    if exc.code == "CANCELLED"
                    else "Sandbox job timed out while waiting for result",
                )
            remaining = deadline - time.time()
            await asyncio.sleep(min(current_poll_interval, max(0, remaining)))
            current_poll_interval = self._advance_poll_interval(current_poll_interval)

    async def submit_and_wait(
        self,
        job: SandboxJob,
        *,
        timeout_seconds: float | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ) -> SandboxResult:
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else job.limits.timeout_seconds + 5
        )
        deadline = bounded_deadline(time.time() + timeout)
        await self.submit(
            job,
            session_id=session_id,
            agent_id=agent_id,
            team_id=team_id,
            deadline_at=deadline,
        )
        return await self.await_result(
            job.job_id, timeout_seconds=max(0, deadline - time.time())
        )

    async def cancel(self, job_id: str, reason: str | None = None) -> SandboxResult:
        existing = await sandbox_result_store.get_result(job_id)
        metadata = existing.metadata if existing else SandboxExecutionMetadata()
        metadata.mark_completed(datetime.now(UTC))
        return await sandbox_result_store.update_status(
            job_id,
            SandboxTaskStatus.CANCELLED,
            metadata=metadata,
            success=False,
            error_code="CANCELLED",
            error=reason or t("workflow_run_cancelled"),
        )


sandbox_gateway = SandboxGateway()
