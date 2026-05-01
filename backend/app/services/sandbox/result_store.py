"""Redis-backed sandbox task/result store."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.redis import get_redis

from .models import SandboxExecutionMetadata, SandboxResult, SandboxTaskStatus


class SandboxResultStore:
    KEY_PREFIX = "sandbox:job:"
    STATUS_SUFFIX = ":status"

    def _key(self, job_id: str) -> str:
        return f"{self.KEY_PREFIX}{job_id}"

    def _status_key(self, job_id: str) -> str:
        return f"{self._key(job_id)}{self.STATUS_SUFFIX}"

    async def save_result(self, result: SandboxResult, ttl_seconds: int | None = None) -> None:
        redis = await get_redis()
        if result.metadata is not None:
            result.metadata.status = result.status
        ttl = ttl_seconds or settings.SANDBOX_RESULT_TTL_SECONDS
        await redis.setex(self._key(result.job_id), ttl, result.model_dump_json())
        await redis.setex(self._status_key(result.job_id), ttl, result.status.value)

    async def get_result(self, job_id: str) -> SandboxResult | None:
        redis = await get_redis()
        payload = await redis.get(self._key(job_id))
        if not payload:
            return None
        return SandboxResult.model_validate_json(payload)

    async def get_status(self, job_id: str) -> SandboxTaskStatus | None:
        redis = await get_redis()
        payload = await redis.get(self._status_key(job_id))
        if not payload:
            return None
        return SandboxTaskStatus(payload)

    async def create_queued_result(
        self,
        job_id: str,
        metadata: SandboxExecutionMetadata | None = None,
    ) -> SandboxResult:
        result = SandboxResult(job_id=job_id, metadata=metadata or SandboxExecutionMetadata())
        await self.save_result(result)
        return result

    async def update_status(
        self,
        job_id: str,
        status: SandboxTaskStatus,
        *,
        metadata: SandboxExecutionMetadata | None = None,
        **updates: Any,
    ) -> SandboxResult:
        current = await self.get_result(job_id)
        if current is None:
            current = SandboxResult(job_id=job_id)

        current.status = status
        if metadata is not None:
            metadata.status = status
            current.metadata = metadata
        elif current.metadata is not None:
            current.metadata.status = status
        for key, value in updates.items():
            setattr(current, key, value)
        await self.save_result(current)
        return current

    async def delete(self, job_id: str) -> None:
        redis = await get_redis()
        await redis.delete(self._key(job_id), self._status_key(job_id))


sandbox_result_store = SandboxResultStore()
