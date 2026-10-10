"""Redis-backed sandbox results with immutable terminal states and execution claims."""

from __future__ import annotations

import time
from math import ceil
from typing import Any

from app.core.config import settings
from app.core.redis import get_redis

from .models import SandboxExecutionMetadata, SandboxResult, SandboxTaskStatus

TERMINAL_STATUSES = frozenset(
    {SandboxTaskStatus.COMPLETED, SandboxTaskStatus.FAILED, SandboxTaskStatus.CANCELLED}
)


class SandboxResultFenceError(RuntimeError):
    code = "EXECUTION_UNCERTAIN"

    def __init__(self, message: str, code: str = "EXECUTION_UNCERTAIN"):
        self.code = code
        super().__init__(message)


class SandboxResultStore:
    KEY_PREFIX = "sandbox:job:"
    STATUS_SUFFIX = ":status"

    def _key(self, job_id: str) -> str:
        return f"{self.KEY_PREFIX}{job_id}"

    def _status_key(self, job_id: str) -> str:
        return f"{self._key(job_id)}{self.STATUS_SUFFIX}"

    async def save_result(
        self,
        result: SandboxResult,
        ttl_seconds: int | None = None,
        *,
        enforce_binding: bool = True,
    ) -> SandboxResult:
        redis = await get_redis()
        result.metadata.status = result.status
        ttl = ttl_seconds or settings.SANDBOX_RESULT_TTL_SECONDS
        if result.status not in TERMINAL_STATUSES and result.deadline_at is not None:
            ttl = max(ttl, ceil(result.deadline_at - time.time()) + ttl)
        payload = await redis.eval(
            """
            local previous = redis.call('GET', KEYS[1])
            if previous then
                local p = cjson.decode(previous)
                if p.status == 'completed' or p.status == 'failed' or p.status == 'cancelled' then return previous end
                local rank = {queued=0, preparing=1, running=2, collecting=3, completed=4, failed=4, cancelled=4}
                if (rank[ARGV[3]] or 0) < (rank[p.status] or 0) then return previous end
            end
            local incoming = cjson.decode(ARGV[2])
            if incoming.deadline_at and incoming.deadline_at ~= cjson.null and ARGV[3] ~= 'failed' and ARGV[3] ~= 'cancelled' then
                local clock = redis.call('TIME')
                if tonumber(clock[1]) + tonumber(clock[2]) / 1000000 >= incoming.deadline_at then return '__DEADLINE__' end
            end
            if ARGV[4] ~= '' then
                local actual = redis.call('GET', KEYS[3])
                if not actual then return false end
                local a = cjson.decode(actual)
                local e = cjson.decode(ARGV[4])
                if a.epoch ~= e.epoch or a.generation ~= e.generation or a.workspace_id ~= e.workspace_id or
                   a.worker_id ~= e.worker_id or a.instance_id ~= e.instance_id or
                   a.node_id ~= e.node_id or a.storage_id ~= e.storage_id or a.status ~= 'READY' then
                    return false
                end
            end
            redis.call('SETEX', KEYS[1], ARGV[1], ARGV[2])
            redis.call('SETEX', KEYS[2], ARGV[1], ARGV[3])
            return ARGV[2]
            """,
            3,
            self._key(result.job_id),
            self._status_key(result.job_id),
            f"sandbox:session-binding:{result.session_id or ''}",
            ttl,
            result.model_dump_json(),
            result.status.value,
            result.binding.model_dump_json()
            if enforce_binding and result.binding and result.session_id
            else "",
        )
        if payload == "__DEADLINE__" or payload == b"__DEADLINE__":
            raise SandboxResultFenceError(
                "Sandbox job deadline expired before publication", "DEADLINE_EXCEEDED"
            )
        if not payload:
            raise SandboxResultFenceError(
                "Sandbox binding changed before result publication; execution may have occurred"
            )
        return SandboxResult.model_validate_json(payload)

    async def claim_execution(
        self, job_id: str, deadline_at: float | None = None
    ) -> bool:
        """A redelivered message cannot execute an uncertain or completed command twice."""
        redis = await get_redis()
        ttl = settings.SANDBOX_RESULT_TTL_SECONDS
        if deadline_at is not None:
            ttl = max(ttl, ceil(deadline_at - time.time()) + ttl)
        return bool(
            await redis.eval(
                """
            local status = redis.call('GET', KEYS[1])
            if status == 'completed' or status == 'failed' or status == 'cancelled' then return 0 end
            return redis.call('SET', KEYS[2], '1', 'NX', 'EX', ARGV[1]) and 1 or 0
            """,
                2,
                self._status_key(job_id),
                f"{self._key(job_id)}:execution",
                ttl,
            )
        )

    async def get_result(self, job_id: str) -> SandboxResult | None:
        redis = await get_redis()
        payload = await redis.get(self._key(job_id))
        return SandboxResult.model_validate_json(payload) if payload else None

    async def get_status(self, job_id: str) -> SandboxTaskStatus | None:
        redis = await get_redis()
        payload = await redis.get(self._status_key(job_id))
        if isinstance(payload, bytes):
            payload = payload.decode()
        return SandboxTaskStatus(payload) if payload else None

    async def create_queued_result(
        self,
        job_id: str,
        metadata: SandboxExecutionMetadata | None = None,
        **context: Any,
    ) -> SandboxResult:
        result = SandboxResult(
            job_id=job_id, metadata=metadata or SandboxExecutionMetadata(), **context
        )
        return await self.save_result(result)

    async def update_status(
        self,
        job_id: str,
        status: SandboxTaskStatus,
        *,
        metadata: SandboxExecutionMetadata | None = None,
        **updates: Any,
    ) -> SandboxResult:
        current = await self.get_result(job_id) or SandboxResult(job_id=job_id)
        current.status = status
        if metadata is not None:
            current.metadata = metadata
        for key, value in updates.items():
            setattr(current, key, value)
        return await self.save_result(current, enforce_binding=False)

    async def delete(self, job_id: str) -> None:
        redis = await get_redis()
        await redis.delete(
            self._key(job_id),
            self._status_key(job_id),
            f"{self._key(job_id)}:execution",
        )


sandbox_result_store = SandboxResultStore()
