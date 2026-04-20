"""Sandbox submission gateway."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.i18n import t

from .models import SandboxExecutionMetadata, SandboxJob, SandboxResult, SandboxTaskStatus
from .policies import sandbox_policy_engine
from .result_store import sandbox_result_store


class SandboxGateway:
    MAX_POLL_INTERVAL = 0.25

    async def submit(self, job: SandboxJob) -> str:
        from app.tasks.sandbox import run_sandbox_job_task

        sandbox_policy_engine.validate(job)
        metadata = SandboxExecutionMetadata(queued_at=datetime.now(UTC))
        await sandbox_result_store.create_queued_result(job.job_id, metadata=metadata)
        run_sandbox_job_task.delay(job.model_dump(mode="json"))
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
                    error=t("request_timeout"),
                )
            await asyncio.sleep(min(current_poll_interval, remaining))
            current_poll_interval = self._advance_poll_interval(current_poll_interval)

    async def submit_and_wait(
        self,
        job: SandboxJob,
        *,
        timeout_seconds: float | None = None,
    ) -> SandboxResult:
        await self.submit(job)
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
