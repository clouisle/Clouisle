"""Thin same-node child supervisor; no Docker/Kubernetes control-plane access."""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from app.core.config import settings

from .affinity import sandbox_data_root, sandbox_node_id, sandbox_worker_id
from .worker_heartbeat import heartbeat_redis, worker_presence
from .worker_registry import sandbox_worker_registry

logger = logging.getLogger(__name__)


def supervise_sandbox_worker(command: list[str], *, cwd: str) -> int:
    """Restart exited workers, never probe/kill a live child for task duration."""
    root = sandbox_data_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".worker-supervisor.lock").open("a") as disk_lock:
        try:
            fcntl.flock(disk_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "Another sandbox supervisor already owns this disk"
            ) from exc
        return _supervise(command, cwd=cwd)


def _supervise(command: list[str], *, cwd: str) -> int:
    stopping = threading.Event()
    child = None

    def forward_signal(signum, frame):
        stopping.set()
        if child is not None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    previous = {
        sig: signal.signal(sig, forward_signal)
        for sig in (signal.SIGTERM, signal.SIGINT)
    }
    restarts = 0
    try:
        while not stopping.is_set():
            instance_id = str(uuid4())
            env = dict(
                os.environ,
                SANDBOX_WORKER_INSTANCE_ID=instance_id,
                SANDBOX_WORKER_ID=sandbox_worker_id(),
                SANDBOX_NODE_ID=sandbox_node_id(),
                SANDBOX_WORKSPACE_ROOT=str(
                    Path(settings.SANDBOX_WORKSPACE_ROOT).resolve()
                ),
                SANDBOX_CHECKPOINT_ROOT=str(
                    Path(settings.SANDBOX_CHECKPOINT_ROOT).resolve()
                    if settings.SANDBOX_CHECKPOINT_ROOT
                    else sandbox_data_root() / "checkpoints"
                ),
            )
            child = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)
            if stopping.is_set():
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            while child.poll() is None:
                if stopping.wait(0.2):
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    break
            returncode = child.wait()
            # An exited parent must not leave a prefork task child executing
            # through a new instance lease. The child has its own process group.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                presence = worker_presence().model_copy(
                    update={"instance_id": instance_id}
                )
                redis = heartbeat_redis()
                try:
                    sandbox_worker_registry.remove(redis, presence)
                finally:
                    redis.close()
            except Exception:
                logger.exception("Exited sandbox child lease removal unavailable")
            child = None
            if stopping.is_set():
                return 0
            if restarts >= settings.SANDBOX_SUPERVISOR_MAX_RESTARTS:
                return returncode or 1
            restarts += 1
            logger.warning(
                "Restarting sandbox child on retained local disk (%s)", restarts
            )
            if stopping.wait(settings.SANDBOX_SUPERVISOR_RESTART_SECONDS):
                return 0
        return 0
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
