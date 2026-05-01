"""Redis-backed sandbox session store."""

from __future__ import annotations

from datetime import timedelta

from app.core.config import settings
from app.core.redis import get_redis
from app.core.timezone import now

from .models import SandboxSession


def _ttl_seconds(ttl_hours: int | None = None) -> int:
    hours = ttl_hours or settings.SANDBOX_SESSION_TTL_HOURS
    return int(timedelta(hours=hours).total_seconds())


class SandboxSessionStore:
    KEY_PREFIX = "sandbox:session:"
    CONVERSATION_KEY_PREFIX = "sandbox:conversation:"
    INDEX_KEY = "sandbox:sessions"

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
        ttl_hours: int | None = None,
    ) -> SandboxSession:
        created_at = now()
        expires_at = created_at + timedelta(seconds=_ttl_seconds(ttl_hours))
        session = SandboxSession(
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            team_id=team_id,
            created_at=created_at,
            expires_at=expires_at,
            last_accessed_at=created_at,
        )
        await self.save(session, ttl_seconds=_ttl_seconds(ttl_hours))
        return session

    async def save(self, session: SandboxSession, *, ttl_seconds: int | None = None) -> None:
        redis = await get_redis()
        ttl = ttl_seconds or max(1, int((session.expires_at - now()).total_seconds()))
        await redis.setex(self._key(session.session_id), ttl, session.model_dump_json())
        await redis.zadd(self.INDEX_KEY, {session.session_id: session.expires_at.timestamp()})
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
            await redis.zrem(self.INDEX_KEY, session_id)
            return None
        return SandboxSession.model_validate_json(payload)

    async def get_by_conversation(self, conversation_id: str) -> SandboxSession | None:
        redis = await get_redis()
        session_id = await redis.get(self._conversation_key(conversation_id))
        if not session_id:
            return None
        session = await self.get(session_id)
        if session is None:
            await redis.delete(self._conversation_key(conversation_id))
            return None
        return session

    async def touch(self, session_id: str, *, disk_usage_bytes: int | None = None) -> SandboxSession | None:
        session = await self.get(session_id)
        if session is None:
            return None
        session.last_accessed_at = now()
        if disk_usage_bytes is not None:
            session.disk_usage_bytes = disk_usage_bytes
        await self.save(session)
        return session

    async def delete(self, session_id: str) -> None:
        redis = await get_redis()
        session = await self.get(session_id)
        await redis.delete(self._key(session_id))
        await redis.zrem(self.INDEX_KEY, session_id)
        if session and session.conversation_id:
            await redis.delete(self._conversation_key(session.conversation_id))

    async def expired_session_ids(self, *, limit: int | None = None) -> list[str]:
        redis = await get_redis()
        batch_size = limit or settings.SANDBOX_SESSION_CLEANUP_BATCH_SIZE
        return await redis.zrangebyscore(
            self.INDEX_KEY,
            min="-inf",
            max=now().timestamp(),
            start=0,
            num=batch_size,
        )

    async def cleanup_expired(self, *, limit: int | None = None) -> int:
        session_ids = await self.expired_session_ids(limit=limit)
        for session_id in session_ids:
            await self.delete(session_id)
        return len(session_ids)


sandbox_session_store = SandboxSessionStore()
