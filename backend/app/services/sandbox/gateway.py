"""Sandbox submission gateway."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.i18n import t

from .models import SandboxExecutionMetadata, SandboxJob, SandboxResult, SandboxTaskStatus
from .policies import sandbox_policy_engine
from .result_store import sandbox_result_store
from .session_store import sandbox_session_store

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
        ttl_hours: int = 24,
        conversation_id: str | None = None,
    ) -> str:
        if conversation_id:
            existing = await sandbox_session_store.get_by_conversation(conversation_id)
            if existing is not None:
                workspace = self._get_workspace_manager().prepare_session(existing.session_id)
                await sandbox_session_store.touch(
                    existing.session_id,
                    disk_usage_bytes=self._get_workspace_manager().workspace_size_bytes(workspace),
                )
                return existing.session_id

        session_id = str(uuid4())
        workspace_manager = self._get_workspace_manager()
        workspace_manager.prepare_session(session_id)
        await sandbox_session_store.create(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            ttl_hours=ttl_hours,
        )
        return session_id

    async def get_session_workspace(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        team_id: str | None = None,
    ) -> "SandboxWorkspace | None":
        session = await sandbox_session_store.get(session_id)
        if session is None:
            return None
        if agent_id is not None and session.agent_id != agent_id:
            return None
        if team_id is not None and session.team_id != team_id:
            return None
        workspace_manager = self._get_workspace_manager()
        session_root = workspace_manager.get_session_root(session_id)
        if not session_root.exists():
            await sandbox_session_store.delete(session_id)
            return None
        workspace = workspace_manager.prepare_session(session_id)
        await sandbox_session_store.touch(
            session_id,
            disk_usage_bytes=workspace_manager.workspace_size_bytes(workspace),
        )
        return workspace

    async def cleanup_session(self, session_id: str) -> None:
        workspace_manager = self._get_workspace_manager()
        workspace_manager.cleanup_session(session_id)
        await sandbox_session_store.delete(session_id)

    async def cleanup_expired_sessions(self) -> int:
        workspace_manager = self._get_workspace_manager()
        session_ids = await sandbox_session_store.expired_session_ids()
        for session_id in session_ids:
            workspace_manager.cleanup_session(session_id)
            await sandbox_session_store.delete(session_id)
        return len(session_ids)

    async def submit(
        self,
        job: SandboxJob,
        session_id: str | None = None,
        *,
        agent_id: str | None = None,
        team_id: str | None = None,
    ) -> str:
        from app.tasks.sandbox import run_sandbox_job_task

        sandbox_policy_engine.validate(job)
        if session_id and await self.get_session_workspace(
            session_id,
            agent_id=agent_id,
            team_id=team_id,
        ) is None:
            raise ValueError("Sandbox session not found or expired")

        metadata = SandboxExecutionMetadata(queued_at=datetime.now(UTC))
        await sandbox_result_store.create_queued_result(job.job_id, metadata=metadata)

        job_data = job.model_dump(mode="json")
        if session_id:
            job_data["session_id"] = session_id
            job_data["session_agent_id"] = agent_id
            job_data["session_team_id"] = team_id
        run_sandbox_job_task.delay(job_data)
        return job.job_id

    def _advance_poll_interval(self, poll_interval: float) -> float:
        if poll_interval <= 0:
            return 0
        return min(self.MAX_POLL_INTERVAL, poll_interval * 2)

    async def get_result(self, job_id: str) -> SandboxResult | None:
        return await sandbox_result_store.get_result(job_id)

    async def await_result(
        self,
        job_id: str,
        *,
        timeout_seconds: float = 30.0,
        poll_interval: float = 0.02,
    ) -> SandboxResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        current_poll_interval = poll_interval
        while True:
            status = await sandbox_result_store.get_status(job_id)
            if status in {
                SandboxTaskStatus.COMPLETED,
                SandboxTaskStatus.FAILED,
                SandboxTaskStatus.CANCELLED,
            }:
                result = await sandbox_result_store.get_result(job_id)
                if result is not None:
                    return result
            remaining = deadline - loop.time()
            if remaining <= 0:
                result = await sandbox_result_store.get_result(job_id)
                metadata = result.metadata if result else SandboxExecutionMetadata()
                metadata.mark_completed(datetime.now(UTC))
                return await sandbox_result_store.update_status(
                    job_id,
                    SandboxTaskStatus.FAILED,
                    metadata=metadata,
                    error="Sandbox job timed out while waiting for result",
                )
            await asyncio.sleep(min(current_poll_interval, remaining))
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
        await self.submit(
            job,
            session_id=session_id,
            agent_id=agent_id,
            team_id=team_id,
        )
        return await self.await_result(
            job.job_id,
            timeout_seconds=timeout_seconds or job.limits.timeout_seconds + 5,
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
            error=reason or t("workflow_run_cancelled"),
        )


sandbox_gateway = SandboxGateway()
