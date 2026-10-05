"""Redis-backed logical sessions and canonical, fenced worker bindings."""

from __future__ import annotations

import time
from datetime import timedelta
from math import ceil

from app.core.config import settings
from app.core.redis import get_redis
from app.core.timezone import now

from .models import SandboxBinding, SandboxSession

STANDALONE_ROUND = "standalone"


def _ttl_seconds(ttl_hours: int | None = None) -> int:
    return int(
        timedelta(hours=ttl_hours or settings.SANDBOX_SESSION_TTL_HOURS).total_seconds()
    )


def _redis_text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


# Every metadata/lifecycle mutation checks the same canonical epoch. A missing
# binding is only valid for genuinely unbound sessions, never a stale caller.
_BINDING_GUARD = """
local actual = redis.call('GET', KEYS[2])
if ARGV[1] == '' then
    if actual then return 0 end
else
    if not actual then return 0 end
    local a = cjson.decode(actual)
    local e = cjson.decode(ARGV[1])
    if a.epoch ~= e.epoch or a.generation ~= e.generation or
       a.workspace_id ~= e.workspace_id or a.instance_id ~= e.instance_id or
       a.worker_id ~= e.worker_id or a.node_id ~= e.node_id or
       a.storage_id ~= e.storage_id or a.status ~= e.status then return 0 end
end
"""


class SandboxSessionStore:
    KEY_PREFIX = "sandbox:session:"
    BINDING_PREFIX = "sandbox:session-binding:"
    CONVERSATION_KEY_PREFIX = "sandbox:conversation:"
    INDEX_KEY = "sandbox:sessions"
    IDLE_INDEX_KEY = "sandbox:session-idle"

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    def _binding_key(self, session_id: str) -> str:
        return f"{self.BINDING_PREFIX}{session_id}"

    def _recovery_key(self, session_id: str) -> str:
        return f"sandbox:session-recovery:{session_id}"

    def _conversation_key(self, conversation_id: str) -> str:
        return f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"

    def _active_round_key(self, session_id: str) -> str:
        return f"sandbox:session-round:{session_id}"

    def _workspace_round_key(self, session_id: str) -> str:
        return f"sandbox:workspace-round:{session_id}"

    async def get_binding(self, session_id: str) -> SandboxBinding | None:
        redis = await get_redis()
        payload = await redis.get(self._binding_key(session_id))
        return SandboxBinding.model_validate_json(payload) if payload else None

    async def get_worker(self, session_id: str) -> str | None:
        binding = await self.get_binding(session_id)
        return binding.worker_id if binding else None

    async def acquire_recovery(
        self,
        session_id: str,
        expected: SandboxBinding | None,
        token: str,
        ttl_seconds: float,
        initial: SandboxBinding | None = None,
    ) -> SandboxBinding | None:
        """Coalesce callers; expired holders can be replaced without losing fences."""
        redis = await get_redis()
        result = await redis.eval(
            _BINDING_GUARD
            + """
            if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
            if not redis.call('SET', KEYS[3], ARGV[2], 'NX', 'PX', ARGV[3]) then return 0 end
            local b = cjson.decode(ARGV[4])
            b.status = 'RECOVERING'
            b.recovery_id = ARGV[2]
            if b.recovery_started_at == cjson.null or not b.recovery_started_at then
                b.recovery_started_at = tonumber(ARGV[5])
            end
            local payload = cjson.encode(b)
            redis.call('SET', KEYS[2], payload)
            return payload
            """,
            3,
            self._key(session_id),
            self._binding_key(session_id),
            self._recovery_key(session_id),
            expected.model_dump_json() if expected else "",
            token,
            max(1, ceil(ttl_seconds * 1000)),
            (expected or initial).model_dump_json(),
            time.time(),
        )
        return SandboxBinding.model_validate_json(result) if result else None

    async def recovery_matches(
        self, session_id: str, binding: SandboxBinding, token: str
    ) -> bool:
        redis = await get_redis()
        current = await self.get_binding(session_id)
        lease = await redis.get(self._recovery_key(session_id))
        return bool(
            current
            and binding.matches(current, ready=False)
            and current.recovery_id == token
            and lease
            and _redis_text(lease) == token
        )

    async def commit_recovery(
        self,
        session_id: str,
        expected: SandboxBinding,
        token: str,
        replacement: SandboxBinding,
    ) -> bool:
        redis = await get_redis()
        return bool(
            await redis.eval(
                _BINDING_GUARD
                + """
            if redis.call('GET', KEYS[3]) ~= ARGV[2] then return 0 end
            if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
            redis.call('SET', KEYS[2], ARGV[3])
            redis.call('DEL', KEYS[3], KEYS[4])
            local s = cjson.decode(redis.call('GET', KEYS[1]))
            if ARGV[4] == '1' then s.disk_usage_bytes = 0 end
            s.revision = (s.revision or 0) + 1
            local ttl = redis.call('PTTL', KEYS[1])
            redis.call('SET', KEYS[1], cjson.encode(s), 'PX', math.max(1, ttl))
            return 1
            """,
                4,
                self._key(session_id),
                self._binding_key(session_id),
                self._recovery_key(session_id),
                self._workspace_round_key(session_id),
                expected.model_dump_json(),
                token,
                replacement.model_dump_json(),
                "1" if replacement.generation != expected.generation else "0",
            )
        )

    async def mark_resetting(
        self, session_id: str, expected: SandboxBinding, token: str
    ) -> SandboxBinding | None:
        redis = await get_redis()
        replacement = expected.model_copy(update={"status": "RESETTING"})
        changed = await redis.eval(
            _BINDING_GUARD
            + """
            if redis.call('GET', KEYS[3]) ~= ARGV[2] then return 0 end
            if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
            redis.call('SET', KEYS[2], ARGV[3]); return 1
            """,
            3,
            self._key(session_id),
            self._binding_key(session_id),
            self._recovery_key(session_id),
            expected.model_dump_json(),
            token,
            replacement.model_dump_json(),
        )
        return replacement if changed else None

    async def abandon_recovery(
        self, session_id: str, expected: SandboxBinding, token: str
    ) -> bool:
        current = await self.get_binding(session_id)
        if (
            current is None
            or not expected.matches(current, ready=False)
            or current.recovery_id != token
        ):
            return False
        replacement = current.model_copy(
            update={
                "status": "UNAVAILABLE",
                "epoch": current.epoch + 1,
                "recovery_id": None,
                "recovery_started_at": None,
            }
        )
        return await self.commit_recovery(session_id, current, token, replacement)

    async def get(self, session_id: str) -> SandboxSession | None:
        redis = await get_redis()
        payload = await redis.get(self._key(session_id))
        return SandboxSession.model_validate_json(payload) if payload else None

    async def create(
        self,
        *,
        session_id: str,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        ttl_hours: int | None = None,
    ) -> SandboxSession:
        created_at = now()
        session = SandboxSession(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            user_id=user_id,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=_ttl_seconds(ttl_hours)),
            last_accessed_at=created_at,
            ttl_seconds=_ttl_seconds(ttl_hours),
        )
        if not await self.save(session, ttl_seconds=session.ttl_seconds, create=True):
            raise ValueError("Sandbox session already exists")
        return session

    async def save(
        self,
        session: SandboxSession,
        *,
        ttl_seconds: int | None = None,
        expected_binding: SandboxBinding | None = None,
        create: bool = False,
    ) -> bool:
        redis = await get_redis()
        binding = (
            expected_binding
            if expected_binding is not None
            else await self.get_binding(session.session_id)
        )
        updated = session.model_copy(update={"revision": session.revision + 1})
        ttl = ttl_seconds or max(1, ceil((session.expires_at - now()).total_seconds()))
        saved = await redis.eval(
            _BINDING_GUARD
            + """
            local payload = redis.call('GET', KEYS[1])
            if ARGV[2] == '1' then
                if payload or redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
            else
                if not payload then return 0 end
                local s = cjson.decode(payload)
                if (s.revision or 0) ~= tonumber(ARGV[3]) then return 0 end
            end
            redis.call('SETEX', KEYS[1], ARGV[4], ARGV[5])
            redis.call('ZADD', KEYS[3], ARGV[6], ARGV[8])
            redis.call('ZADD', KEYS[4], ARGV[7], ARGV[8])
            if ARGV[9] ~= '' then redis.call('SETEX', KEYS[5], ARGV[4], ARGV[8]) end
            return 1
            """,
            5,
            self._key(session.session_id),
            self._binding_key(session.session_id),
            self.INDEX_KEY,
            self.IDLE_INDEX_KEY,
            self._conversation_key(session.conversation_id or ""),
            binding.model_dump_json() if binding else "",
            "1" if create else "0",
            session.revision,
            ttl,
            updated.model_dump_json(),
            session.expires_at.timestamp(),
            session.last_accessed_at.timestamp(),
            session.session_id,
            session.conversation_id or "",
        )
        if saved:
            session.revision = updated.revision
        return bool(saved)

    async def touch(
        self,
        session_id: str,
        *,
        disk_usage_bytes: int | None = None,
        expected_binding: SandboxBinding | None = None,
    ) -> SandboxSession | None:
        binding = (
            expected_binding
            if expected_binding is not None
            else await self.get_binding(session_id)
        )
        for _ in range(3):
            session = await self.get(session_id)
            if session is None:
                return None
            session.last_accessed_at = now()
            session.expires_at = session.last_accessed_at + timedelta(
                seconds=session.ttl_seconds
            )
            if disk_usage_bytes is not None:
                session.disk_usage_bytes = disk_usage_bytes
            if await self.save(session, expected_binding=binding):
                return session
        return None

    async def get_by_conversation(self, conversation_id: str) -> SandboxSession | None:
        redis = await get_redis()
        session_id = await redis.get(self._conversation_key(conversation_id))
        return await self.get(_redis_text(session_id)) if session_id else None

    async def _round_mutation(
        self,
        session_id: str,
        round_id: str | None,
        *,
        workspace: bool,
        expected_binding: SandboxBinding | None = None,
        ttl_seconds: float | None = None,
        compare: bool = False,
    ) -> bool:
        redis = await get_redis()
        binding = (
            expected_binding
            if expected_binding is not None
            else await self.get_binding(session_id)
        )
        return bool(
            await redis.eval(
                _BINDING_GUARD
                + """
            if ARGV[2] == 'compare' then
                if redis.call('GET', KEYS[1]) ~= ARGV[3] then return 0 end
                redis.call('DEL', KEYS[1])
            elseif ARGV[2] == 'delete' then redis.call('DEL', KEYS[1])
            elseif ARGV[4] ~= '' then redis.call('SETEX', KEYS[1], ARGV[4], ARGV[3])
            else redis.call('SET', KEYS[1], ARGV[3]) end
            return 1
            """,
                2,
                self._workspace_round_key(session_id)
                if workspace
                else self._active_round_key(session_id),
                self._binding_key(session_id),
                binding.model_dump_json() if binding else "",
                "compare" if compare else ("delete" if round_id is None else "set"),
                round_id or "",
                max(1, ceil(ttl_seconds)) if ttl_seconds is not None else "",
            )
        )

    async def get_workspace_round(self, session_id: str) -> str | None:
        redis = await get_redis()
        token = await redis.get(self._workspace_round_key(session_id))
        return _redis_text(token) if token else None

    async def mark_workspace_round(
        self,
        session_id: str,
        round_id: str,
        *,
        expected_binding: SandboxBinding | None = None,
    ) -> bool:
        return await self._round_mutation(
            session_id, round_id, workspace=True, expected_binding=expected_binding
        )

    async def clear_workspace_round(
        self, session_id: str, *, expected_binding: SandboxBinding | None = None
    ) -> bool:
        return await self._round_mutation(
            session_id, None, workspace=True, expected_binding=expected_binding
        )

    async def begin_round(
        self, session_id: str, round_id: str, ttl_seconds: float
    ) -> None:
        if await self.get(session_id) is None:
            raise ValueError("Sandbox session not found or expired")
        await self._round_mutation(
            session_id, round_id, workspace=False, ttl_seconds=ttl_seconds
        )
        await self.touch(session_id)

    async def get_active_round(self, session_id: str) -> str | None:
        redis = await get_redis()
        token = await redis.get(self._active_round_key(session_id))
        return _redis_text(token) if token else None

    async def finish_round(
        self,
        session_id: str,
        round_id: str,
        *,
        expected_binding: SandboxBinding | None = None,
    ) -> bool:
        return await self._round_mutation(
            session_id,
            round_id,
            workspace=False,
            compare=True,
            expected_binding=expected_binding,
        )

    async def mark_evicted(
        self, session_id: str, *, expected_binding: SandboxBinding | None = None
    ) -> bool:
        redis = await get_redis()
        binding = (
            expected_binding
            if expected_binding is not None
            else await self.get_binding(session_id)
        )
        return bool(
            await redis.eval(
                _BINDING_GUARD + "redis.call('ZREM', KEYS[1], ARGV[2]); return 1",
                2,
                self.IDLE_INDEX_KEY,
                self._binding_key(session_id),
                binding.model_dump_json() if binding else "",
                session_id,
            )
        )

    async def delete(
        self,
        session_id: str,
        *,
        expected_binding: SandboxBinding | None = None,
        expired_only: bool = False,
    ) -> bool:
        redis = await get_redis()
        binding = (
            expected_binding
            if expected_binding is not None
            else await self.get_binding(session_id)
        )
        tombstone = (
            binding.model_copy(
                update={
                    "epoch": binding.epoch + 1,
                    "status": "UNAVAILABLE",
                    "recovery_id": None,
                    "recovery_started_at": None,
                }
            )
            if binding
            else None
        )
        return bool(
            await redis.eval(
                _BINDING_GUARD
                + """
            local payload = redis.call('GET', KEYS[1])
            if ARGV[2] == '1' and payload then return 0 end
            if payload then
                local s = cjson.decode(payload)
                if s.conversation_id and s.conversation_id ~= cjson.null then
                    local k = ARGV[4] .. s.conversation_id
                    if redis.call('GET', k) == ARGV[5] then redis.call('DEL', k) end
                end
            end
            if ARGV[3] ~= '' then redis.call('SET', KEYS[2], ARGV[3]) end
            redis.call('DEL', KEYS[1], KEYS[3], KEYS[4], KEYS[7])
            redis.call('ZREM', KEYS[5], ARGV[5]); redis.call('ZREM', KEYS[6], ARGV[5])
            return 1
            """,
                7,
                self._key(session_id),
                self._binding_key(session_id),
                self._active_round_key(session_id),
                self._workspace_round_key(session_id),
                self.INDEX_KEY,
                self.IDLE_INDEX_KEY,
                self._recovery_key(session_id),
                binding.model_dump_json() if binding else "",
                "1" if expired_only else "0",
                tombstone.model_dump_json() if tombstone else "",
                self.CONVERSATION_KEY_PREFIX,
                session_id,
            )
        )

    async def expired_session_ids(self, *, limit: int | None = None) -> list[str]:
        redis = await get_redis()
        values = await redis.zrangebyscore(
            self.INDEX_KEY,
            min="-inf",
            max=now().timestamp(),
            start=0,
            num=limit or settings.SANDBOX_SESSION_CLEANUP_BATCH_SIZE,
        )
        return [_redis_text(v) for v in values]

    async def idle_session_ids(self, cutoff: float) -> list[str]:
        redis = await get_redis()
        values = await redis.zrangebyscore(
            self.IDLE_INDEX_KEY,
            min="-inf",
            max=cutoff,
            start=0,
            num=settings.SANDBOX_SESSION_CLEANUP_BATCH_SIZE,
        )
        return [_redis_text(v) for v in values]

    async def cleanup_expired(self, *, limit: int | None = None) -> int:
        ids = await self.expired_session_ids(limit=limit)
        for session_id in ids:
            await self.delete(session_id, expired_only=True)
        return len(ids)


sandbox_session_store = SandboxSessionStore()
