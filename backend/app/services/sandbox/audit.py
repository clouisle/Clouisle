"""Audit sandbox task lifecycle events without recording execution contents."""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from app.models.audit_log import AuditLog

from .session_store import sandbox_session_store

logger = logging.getLogger(__name__)

SandboxTaskAuditEvent = Literal[
    "started", "completed", "failed", "cancelled", "recovered"
]

_ACTIONS: dict[SandboxTaskAuditEvent, str] = {
    "started": "sandbox_task_started",
    "completed": "sandbox_task_completed",
    "failed": "sandbox_task_failed",
    "cancelled": "sandbox_task_cancelled",
    "recovered": "sandbox_task_recovered",
}


def _uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


async def log_sandbox_task_event(
    *,
    job_id: str,
    event: SandboxTaskAuditEvent,
    session_id: str | None = None,
    source: str | None = None,
    team_id: str | None = None,
    worker_id: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    outcome: Literal["success", "failed"] = "success",
    recovery: dict[str, str | int | None] | None = None,
) -> None:
    """Persist one lifecycle event; never include code, arguments, output, or raw errors."""
    try:
        session = await sandbox_session_store.get(session_id) if session_id else None
        actor_id = _uuid(session.user_id) if session else None
        resolved_team_id = team_id or (session.team_id if session else None)
        audit_status = (
            "failed"
            if event == "failed" or (event == "recovered" and outcome == "failed")
            else "success"
        )
        metadata: dict[str, Any] = {
            "job_id": job_id,
            "session_id": session_id,
            "source": source,
            "worker_id": worker_id,
            "error_code": error_code,
            "duration_ms": duration_ms,
        }
        if recovery:
            metadata["recovery"] = recovery

        await AuditLog.create(
            user_id=actor_id,
            username=None,
            team_id=_uuid(resolved_team_id),
            ip_address="system",
            user_agent="sandbox-worker",
            action=_ACTIONS[event],
            resource_type="sandbox_task",
            resource_id=_uuid(job_id),
            resource_name=job_id[:255],
            operation="recover" if event == "recovered" else "execute",
            status=audit_status,
            error_message=error_code if audit_status == "failed" else None,
            changes=None,
            metadata=metadata,
            auth_method=None,
            api_key_id=None,
        )
    except Exception:
        # Audit storage failure must not convert a sandbox result into a different result.
        logger.exception("Failed to persist sandbox task audit event %s", event)
