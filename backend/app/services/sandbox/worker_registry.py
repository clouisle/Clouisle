"""Readiness leases and persistent node-local sandbox placement in Redis."""

from __future__ import annotations

from pydantic import BaseModel

from app.core.redis import get_redis


class WorkerPresence(BaseModel):
    worker_id: str
    instance_id: str
    node_id: str
    pid: int = 0
    storage_id: str
    ready: bool = True


class SandboxWorkerRegistry:
    PLACEMENTS_KEY = "sandbox:workers:placements"
    LEASE_PREFIX = "sandbox:worker:lease:"

    # A restarted instance cannot overwrite a live owner's lease. Placement is
    # retained after expiry so recovery can prefer the original node and disk.
    REFRESH_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if current then
    local owner = cjson.decode(current)
    if owner.instance_id ~= ARGV[1] then return 0 end
    if owner.storage_id ~= ARGV[4] or owner.node_id ~= ARGV[5] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('HSET', KEYS[2], ARGV[6], ARGV[2])
return 1
"""
    DELETE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current or cjson.decode(current).instance_id ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1])
return 1
"""

    def lease_key(self, worker_id: str) -> str:
        return f"{self.LEASE_PREFIX}{worker_id}"

    def refresh(self, redis, presence: WorkerPresence, ttl_seconds: int) -> bool:
        """Use only with a dedicated synchronous heartbeat Redis client."""
        return bool(
            redis.eval(
                self.REFRESH_SCRIPT,
                2,
                self.lease_key(presence.worker_id),
                self.PLACEMENTS_KEY,
                presence.instance_id,
                presence.model_dump_json(),
                ttl_seconds,
                presence.storage_id,
                presence.node_id,
                presence.worker_id,
            )
        )

    def remove(self, redis, presence: WorkerPresence) -> bool:
        return bool(
            redis.eval(
                self.DELETE_SCRIPT,
                1,
                self.lease_key(presence.worker_id),
                presence.instance_id,
            )
        )

    async def get(self, worker_id: str) -> WorkerPresence | None:
        redis = await get_redis()
        payload = await redis.get(self.lease_key(worker_id))
        return WorkerPresence.model_validate_json(payload) if payload else None

    async def get_placement(self, worker_id: str) -> WorkerPresence | None:
        """Historical placement, not evidence of readiness or a live instance."""
        redis = await get_redis()
        payload = await redis.hget(self.PLACEMENTS_KEY, worker_id)
        return WorkerPresence.model_validate_json(payload) if payload else None

    async def list_ready(self) -> list[WorkerPresence]:
        redis = await get_redis()
        worker_ids = await redis.hkeys(self.PLACEMENTS_KEY)
        if not worker_ids:
            return []
        keys = [
            self.lease_key(
                worker_id.decode() if isinstance(worker_id, bytes) else worker_id
            )
            for worker_id in worker_ids
        ]
        payloads = await redis.mget(keys)
        workers = [
            WorkerPresence.model_validate_json(payload)
            for payload in payloads
            if payload
        ]
        return [worker for worker in workers if worker.ready]


sandbox_worker_registry = SandboxWorkerRegistry()
