"""Worker identity and dedicated queues for local sandbox session workspaces."""

from __future__ import annotations

import hashlib
import socket

from app.core.config import settings


def sandbox_worker_id() -> str:
    """An identity must only be reused with the same retained workspace disk."""
    worker_id = settings.SANDBOX_WORKER_ID or socket.gethostname()
    if not worker_id.strip() or worker_id != worker_id.strip():
        raise ValueError(
            "SANDBOX_WORKER_ID must be non-empty and have no outer whitespace"
        )
    return worker_id


def sandbox_worker_queue(worker_id: str) -> str:
    return f"sandbox.worker.{hashlib.sha256(worker_id.encode()).hexdigest()}"
