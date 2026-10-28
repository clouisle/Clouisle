"""Explicit ownership and terminal cleanup for live MCP sessions.

A live MCP session (JSON-RPC stream + optional stdio subprocess) cannot be
serialized into PostgreSQL. This module keeps only a *process-local* handle so
that one execution owns at most one session while a server-initiated callback
is pending, and makes every way a session can end terminal:

* the owning ``run_with_mcp_callbacks`` scope exits (normal or exception),
* the process performs an explicit worker shutdown close,
* the session exceeds its maximum lifetime (swept on the next acquire).

When a session closes, every still-pending interaction for that session key is
marked ``connection_lost`` exactly once. Nothing here replays the outer tool
call, restarts a stdio server, or pretends a JSON-RPC request survived.

Deployment role: there is no new daemon. Callbacks run inside the existing
Celery ``agent`` / ``workflow`` / ``knowledge`` worker roles that already own
the durable run; desktop/API processes only respond to rows.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.timezone import now_utc
from app.models.tool_interaction import InteractionStatus
from app.services import tool_interactions

logger = logging.getLogger(__name__)

MAX_SESSION_KEY_LENGTH = 120


class McpSessionState(str, Enum):
    """Lifecycle of one managed session handle."""

    OPEN = "open"
    CLOSED = "closed"


class McpSessionTerminalReason(str, Enum):
    """Why a managed session stopped being able to answer callbacks."""

    SESSION_CLOSED = "session_closed"
    CONNECTION_LOST = "connection_lost"
    MAX_LIFETIME = "max_lifetime"
    WORKER_SHUTDOWN = "worker_shutdown"


@dataclass
class ManagedMcpSession:
    """One explicitly owned live-session handle.

    The handle is not the transport itself. It is the ownership token the
    callback bridge checks before every wait iteration and the key used to
    terminate pending interaction rows when the session ends.
    """

    key: str
    owner: str
    execution_id: UUID | None
    opened_at: datetime
    expires_at: datetime
    refs: int = 1
    interactions_created: int = 0
    state: McpSessionState = McpSessionState.OPEN
    terminal_reason: McpSessionTerminalReason | None = None
    closed_at: datetime | None = None
    _closed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @property
    def is_closed(self) -> bool:
        return self.state != McpSessionState.OPEN

    def terminal_interaction_status(self) -> InteractionStatus | None:
        """Terminal status pending rows must adopt when the session is gone."""
        if not self.is_closed:
            return None
        return InteractionStatus.CONNECTION_LOST

    async def wait_closed(self, timeout: float | None = None) -> bool:
        if self.is_closed:
            return True
        try:
            await asyncio.wait_for(self._closed.wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True


_sessions: dict[str, ManagedMcpSession] = {}
_sessions_lock = asyncio.Lock()


def _session_key(execution_id: UUID | None) -> str:
    if execution_id is not None:
        return f"exec:{execution_id}"[:MAX_SESSION_KEY_LENGTH]
    return f"tmp:{uuid4().hex}"[:MAX_SESSION_KEY_LENGTH]


def _lifetime_seconds() -> float:
    return float(settings.MCP_INTERACTION_TTL_SECONDS)


async def _sweep_expired_locked() -> None:
    """Close handles older than the interaction TTL (caller holds the lock)."""
    now = now_utc()
    stale = [handle for handle in _sessions.values() if handle.expires_at <= now]
    for handle in stale:
        handle.state = McpSessionState.CLOSED
        handle.terminal_reason = McpSessionTerminalReason.MAX_LIFETIME
        handle.closed_at = now
        handle._closed.set()
        _sessions.pop(handle.key, None)
        if not handle.interactions_created:
            continue
        logger.warning(
            "Managed MCP session %s exceeded its lifetime; marking pending "
            "interactions connection_lost",
            handle.key,
        )
        try:
            await tool_interactions.close_pending_for_session(handle.key)
        except Exception:  # pragma: no cover - database/shutdown safety
            logger.exception(
                "Failed to close pending interactions for expired session %s",
                handle.key,
            )


async def acquire_session(
    *,
    owner: str,
    execution_id: UUID | None = None,
    max_lifetime_seconds: float | None = None,
) -> ManagedMcpSession:
    """Acquire the process-local session for one execution.

    Idempotent per execution id: concurrent callbacks inside the same tool
    call share one handle and one reference count. Callers MUST pair this with
    :func:`release_session`; the implicit expiry sweep is a leak backstop, not
    the normal cleanup path.
    """
    async with _sessions_lock:
        await _sweep_expired_locked()
        key = _session_key(execution_id)
        existing = _sessions.get(key)
        if existing is not None and not existing.is_closed:
            existing.refs += 1
            return existing
        now = now_utc()
        lifetime = (
            float(max_lifetime_seconds)
            if max_lifetime_seconds is not None
            else _lifetime_seconds()
        )
        handle = ManagedMcpSession(
            key=key,
            owner=owner,
            execution_id=execution_id,
            opened_at=now,
            expires_at=now + timedelta(seconds=max(lifetime, 1.0)),
        )
        _sessions[key] = handle
        logger.debug(
            "Opened managed MCP session %s for owner=%s execution=%s",
            handle.key,
            owner,
            execution_id,
        )
        return handle


async def release_session(
    session: ManagedMcpSession,
    reason: McpSessionTerminalReason = McpSessionTerminalReason.SESSION_CLOSED,
) -> None:
    """Release one reference; the last release closes the session terminally."""
    if session.is_closed:
        return
    session.refs = max(session.refs - 1, 0)
    if session.refs > 0:
        return
    await _close(session, reason)


async def _close(session: ManagedMcpSession, reason: McpSessionTerminalReason) -> None:
    async with _sessions_lock:
        if session.is_closed:
            return
        session.state = McpSessionState.CLOSED
        session.terminal_reason = reason
        session.closed_at = now_utc()
        session._closed.set()
        if _sessions.get(session.key) is session:
            _sessions.pop(session.key, None)
    logger.debug(
        "Closed managed MCP session %s (%s); no pending RPC is replayed",
        session.key,
        reason.value,
    )
    if not session.interactions_created:
        return
    try:
        await tool_interactions.close_pending_for_session(session.key)
    except Exception:  # pragma: no cover - database/shutdown safety
        logger.exception(
            "Failed to mark pending interactions connection_lost for %s",
            session.key,
        )


async def close_all_sessions(
    reason: McpSessionTerminalReason = McpSessionTerminalReason.WORKER_SHUTDOWN,
) -> int:
    """Close every handle owned by this process (worker shutdown path)."""
    async with _sessions_lock:
        handles = list(_sessions.values())
        _sessions.clear()
    for handle in handles:
        handle.state = McpSessionState.CLOSED
        handle.terminal_reason = reason
        handle.closed_at = now_utc()
        handle.refs = 0
        handle._closed.set()
        if not handle.interactions_created:
            continue
        try:
            await tool_interactions.close_pending_for_session(handle.key)
        except Exception:  # pragma: no cover - shutdown safety
            logger.exception(
                "Failed to close pending interactions for session %s", handle.key
            )
    if handles:
        logger.warning(
            "Closed %s managed MCP session(s) on %s", len(handles), reason.value
        )
    return len(handles)


def active_session_count() -> int:
    return sum(1 for handle in _sessions.values() if not handle.is_closed)


def session_for_execution(execution_id: UUID) -> ManagedMcpSession | None:
    return _sessions.get(_session_key(execution_id))


def note_interaction_created(session_key: str) -> None:
    """Record that a durable row belongs to a live managed session."""
    handle = _sessions.get(session_key)
    if handle is not None and not handle.is_closed:
        handle.interactions_created += 1


__all__ = [
    "ManagedMcpSession",
    "McpSessionState",
    "McpSessionTerminalReason",
    "acquire_session",
    "active_session_count",
    "close_all_sessions",
    "release_session",
    "note_interaction_created",
    "session_for_execution",
]
