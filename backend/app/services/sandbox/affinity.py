"""Persistent worker/disk identity and dedicated local sandbox queues."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
from pathlib import Path
from uuid import uuid4

from app.core.config import settings

_PROCESS_INSTANCE_ID = str(uuid4())


def sandbox_data_root() -> Path:
    """Persist this entire directory, including checkpoints, locks and caches."""
    return Path(settings.SANDBOX_WORKSPACE_ROOT).resolve().parent


def _identity() -> dict[str, str]:
    root = sandbox_data_root()
    root.mkdir(parents=True, exist_ok=True)
    identity_path = root / ".worker-identity.json"
    with (root / ".worker-identity.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if identity_path.exists():
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            if not all(
                isinstance(identity.get(key), str) and identity[key].strip()
                for key in ("worker_id", "storage_id")
            ):
                raise ValueError("Invalid sandbox disk identity")
        else:
            worker_id = settings.SANDBOX_WORKER_ID or f"sandbox-{uuid4()}"
            _validate_identity(worker_id, "SANDBOX_WORKER_ID")
            identity = {"worker_id": worker_id, "storage_id": str(uuid4())}
            temporary = root / f".worker-identity.{uuid4()}.tmp"
            try:
                with temporary.open("x", encoding="utf-8") as stream:
                    json.dump(identity, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(identity_path)
            finally:
                temporary.unlink(missing_ok=True)
        if (
            settings.SANDBOX_WORKER_ID
            and settings.SANDBOX_WORKER_ID != identity["worker_id"]
        ):
            raise ValueError(
                "SANDBOX_WORKER_ID disagrees with retained sandbox disk identity"
            )
        return identity


def _validate_identity(value: str, name: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be non-empty and have no outer whitespace")
    return value


def sandbox_worker_id() -> str:
    return _identity()["worker_id"]


def sandbox_storage_id() -> str:
    return _identity()["storage_id"]


def sandbox_instance_id() -> str:
    return _validate_identity(
        settings.SANDBOX_WORKER_INSTANCE_ID or _PROCESS_INSTANCE_ID,
        "SANDBOX_WORKER_INSTANCE_ID",
    )


def sandbox_node_id() -> str:
    return _validate_identity(
        settings.SANDBOX_NODE_ID or socket.gethostname(), "SANDBOX_NODE_ID"
    )


def sandbox_worker_queue(worker_id: str) -> str:
    return f"sandbox.worker.{hashlib.sha256(worker_id.encode()).hexdigest()}"
