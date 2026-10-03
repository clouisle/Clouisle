"""Redis-backed sandbox session store."""

from __future__ import annotations

from datetime import timedelta
from math import ceil
from typing import cast

from app.core.config import settings
from app.core.redis import get_redis
from app.core.timezone import now

from .models import SandboxSession

STANDALONE_ROUND = "standalone"


def _ttl_seconds(ttl_hours: int | None = None) -> int:
    hours = ttl_hours or settings.SANDBOX_SESSION_TTL_HOURS
    return int(timedelta(hours=hours).total_seconds())


def _redis_text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return value


class SandboxSessionStore:
    KEY_PREFIX = "sandbox:session:"
    CONVERSATION_KEY_PREFIX = "sandbox:conversation:"
    INDEX_KEY = "sandbox:sessions"
    WORKER_KEY_PREFIX = "sandbox:session-worker:"
    IDLE_INDEX_KEY = "sandbox:session-idle"

    def _active_round_key(self, session_id: str) -> str:
        return f"sandbox:session-round:{session_id}"

    def _workspace_round_key(self, session_id: str) -> str:
        return f"sandbox:workspace-round:{session_id}"

    async def get_workspace_round(self, session_id: str) -> str | None:
        redis = await get_redis()
        token = await redis.get(self._workspace_round_key(session_id))
        return _redis_text(token) if token is not None else None

    async def mark_workspace_round(self, session_id: str, round_id: str) -> None:
        redis = await get_redis()
        await redis.set(self._workspace_round_key(session_id), round_id)

    async def clear_workspace_round(self, session_id: str) -> None:
        redis = await get_redis()
        await redis.delete(self._workspace_round_key(session_id))

    async def begin_round(
        self, session_id: str, round_id: str, ttl_seconds: float
    ) -> None:
        if await self.get(session_id) is None:
            raise ValueError("Sandbox session not found or expired")
        redis = await get_redis()
        await redis.setex(
            self._active_round_key(session_id), max(1, ceil(ttl_seconds)), round_id
        )
        await self.touch(session_id)

    async def get_active_round(self, session_id: str) -> str | None:
        redis = await get_redis()
        token = await redis.get(self._active_round_key(session_id))
        return _redis_text(token) if token is not None else None

    async def finish_round(self, session_id: str, round_id: str) -> bool:
        redis = await get_redis()
        return bool(
            await redis.eval(
                """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                redis.call('DEL', KEYS[1])
                return 1
            end
            return 0
            """,
                1,
                self._active_round_key(session_id),
                round_id,
            )
        )

    async def idle_session_ids(self, cutoff: float) -> list[str]:
        redis = await get_redis()
        session_ids = await redis.zrangebyscore(
            self.IDLE_INDEX_KEY,
            min="-inf",
            max=cutoff,
            start=0,
            num=settings.SANDBOX_SESSION_CLEANUP_BATCH_SIZE,
        )
        return [_redis_text(session_id) for session_id in session_ids]

    async def mark_evicted(self, session_id: str) -> None:
        redis = await get_redis()
        await redis.zrem(self.IDLE_INDEX_KEY, session_id)

    def _worker_key(self, session_id: str) -> str:
        return f"{self.WORKER_KEY_PREFIX}{session_id}"

    async def get_worker(self, session_id: str) -> str | None:
        redis = await get_redis()
        worker = await redis.get(self._worker_key(session_id))
        return _redis_text(worker) if worker is not None else None

    async def claim_worker(self, session_id: str, worker_id: str) -> str:
        """First consumer wins; ownership survives metadata TTL until cleanup."""
        redis = await get_redis()
        worker = await redis.eval(
            """
            if redis.call('EXISTS', KEYS[1]) == 0 then return false end
            redis.call('SET', KEYS[2], ARGV[1], 'NX')
            return redis.call('GET', KEYS[2])
            """,
            2,
            self._key(session_id),
            self._worker_key(session_id),
            worker_id,
        )
        if worker is None:
            raise ValueError("Sandbox session not found or expired")
        return _redis_text(worker)

    def _key(self, session_id: str) -> str:
        return f"{self.KEY_PREFIX}{session_id}"

    def _conversation_key(self, conversation_id: str) -> str:
        return f"{self.CONVERSATION_KEY_PREFIX}{conversation_id}"

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
        expires_at = created_at + timedelta(seconds=_ttl_seconds(ttl_hours))
        session = SandboxSession(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            user_id=user_id,
            created_at=created_at,
            expires_at=expires_at,
            last_accessed_at=created_at,
            ttl_seconds=_ttl_seconds(ttl_hours),
        )
        await self.save(session, ttl_seconds=_ttl_seconds(ttl_hours))
        return session

    async def save(
        self, session: SandboxSession, *, ttl_seconds: int | None = None
    ) -> None:
        redis = await get_redis()
        ttl = ttl_seconds or max(1, int((session.expires_at - now()).total_seconds()))
        await redis.setex(self._key(session.session_id), ttl, session.model_dump_json())
        await redis.zadd(
            self.INDEX_KEY, {session.session_id: session.expires_at.timestamp()}
        )
        await redis.zadd(
            self.IDLE_INDEX_KEY,
            {session.session_id: session.last_accessed_at.timestamp()},
        )
        if session.conversation_id:
            await redis.setex(
                self._conversation_key(session.conversation_id),
                ttl,
                session.session_id,
            )

    async def get(self, session_id: str) -> SandboxSession | None:
        redis = await get_redis()
        payload = await redis.get(self._key(session_id))
        if not payload:
            return None
        return SandboxSession.model_validate_json(_redis_text(payload))

    async def get_by_conversation(self, conversation_id: str) -> SandboxSession | None:
        redis = await get_redis()
        session_id = await redis.get(self._conversation_key(conversation_id))
        if not session_id:
            return None
        session = await self.get(_redis_text(session_id))
        if session is None:
            await redis.delete(self._conversation_key(conversation_id))
            return None
        return session

    async def touch(
        self, session_id: str, *, disk_usage_bytes: int | None = None
    ) -> SandboxSession | None:
        session = await self.get(session_id)
        if session is None:
            return None
        session.last_accessed_at = now()
        session.expires_at = session.last_accessed_at + timedelta(
            seconds=session.ttl_seconds
        )
        if disk_usage_bytes is not None:
            session.disk_usage_bytes = disk_usage_bytes
        await self.save(session)
        return session

    async def delete(self, session_id: str) -> None:
        redis = await get_redis()
        session = await self.get(session_id)
        await redis.delete(
            self._key(session_id),
            self._worker_key(session_id),
            self._active_round_key(session_id),
            self._workspace_round_key(session_id),
        )
        await redis.zrem(self.INDEX_KEY, session_id)
        await redis.zrem(self.IDLE_INDEX_KEY, session_id)
        if session and session.conversation_id:
            await redis.delete(self._conversation_key(session.conversation_id))

    async def expired_session_ids(self, *, limit: int | None = None) -> list[str]:
        redis = await get_redis()
        batch_size = limit or settings.SANDBOX_SESSION_CLEANUP_BATCH_SIZE
        session_ids = cast(
            "list[bytes | str]",
            await redis.zrangebyscore(
                self.INDEX_KEY,
                min="-inf",
                max=now().timestamp(),
                start=0,
                num=batch_size,
            ),
        )
        return [_redis_text(session_id) for session_id in session_ids]

    async def cleanup_expired(self, *, limit: int | None = None) -> int:
        session_ids = await self.expired_session_ids(limit=limit)
        for session_id in session_ids:
            await self.delete(session_id)
        return len(session_ids)


sandbox_session_store = SandboxSessionStore()
