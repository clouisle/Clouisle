"""Parent-worker heartbeat independent of Celery's busy solo task loop."""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path
from tempfile import TemporaryFile

from redis import Redis

from app.core.config import settings

from .affinity import (
    sandbox_instance_id,
    sandbox_node_id,
    sandbox_storage_id,
    sandbox_worker_id,
)
from .worker_registry import WorkerPresence, sandbox_worker_registry

logger = logging.getLogger(__name__)


def heartbeat_redis() -> Redis:
    # Never share API async pools or Celery broker connections with this thread.
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=0,
        decode_responses=True,
        socket_connect_timeout=min(settings.SANDBOX_WORKER_HEARTBEAT_SECONDS, 2),
        socket_timeout=min(settings.SANDBOX_WORKER_HEARTBEAT_SECONDS, 2),
    )


def worker_presence() -> WorkerPresence:
    # A ready consumer without a writable retained disk is not usable capacity.
    workspace = Path(settings.SANDBOX_WORKSPACE_ROOT)
    checkpoint = (
        Path(settings.SANDBOX_CHECKPOINT_ROOT)
        if settings.SANDBOX_CHECKPOINT_ROOT
        else workspace.parent / "checkpoints"
    )
    for directory in (workspace, checkpoint):
        directory.mkdir(parents=True, exist_ok=True)
        with TemporaryFile(dir=directory) as probe:
            probe.write(b"ready")
            probe.flush()
            os.fsync(probe.fileno())
    return WorkerPresence(
        worker_id=sandbox_worker_id(),
        instance_id=sandbox_instance_id(),
        node_id=sandbox_node_id(),
        storage_id=sandbox_storage_id(),
        pid=os.getpid(),
    )


class SandboxWorkerHeartbeat:
    def __init__(self, presence: WorkerPresence, *, redis=None, on_conflict=None):
        self.presence = presence
        self.redis = redis if redis is not None else heartbeat_redis()
        self.on_conflict = on_conflict or self._shutdown_conflicting_worker
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="sandbox-heartbeat", daemon=True
        )

    @staticmethod
    def _shutdown_conflicting_worker() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    def refresh(self) -> bool:
        return sandbox_worker_registry.refresh(
            self.redis,
            self.presence,
            settings.SANDBOX_WORKER_HEARTBEAT_TTL_SECONDS,
        )

    def start(self) -> None:
        # worker_ready fires only after the consumer is ready. A connection error
        # never fabricates readiness; retry in the independent thread instead.
        try:
            if not self.refresh():
                self.on_conflict()
                return
        except Exception:
            logger.exception("Sandbox readiness registration unavailable")
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(settings.SANDBOX_WORKER_HEARTBEAT_SECONDS):
            try:
                if not self.refresh():
                    logger.error(
                        "Sandbox worker identity already owned by another instance"
                    )
                    self.on_conflict()
                    return
            except Exception:
                # Redis outage is UNKNOWN, not a reason to kill a healthy busy
                # solo worker. Task binding guards reject execution without lease.
                logger.exception("Sandbox readiness heartbeat unavailable")

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        try:
            sandbox_worker_registry.remove(self.redis, self.presence)
        except Exception:
            logger.exception("Sandbox readiness removal unavailable; lease will expire")
        finally:
            self.redis.close()


_heartbeat: SandboxWorkerHeartbeat | None = None


def start_worker_heartbeat(sender=None, **kwargs) -> None:
    global _heartbeat
    queues = getattr(getattr(sender, "task_consumer", None), "queues", ())
    names = {queue.name for queue in queues}
    if "sandbox" not in names and not any(
        name.startswith("sandbox.worker.") for name in names
    ):
        return
    if _heartbeat is not None:
        return
    try:
        presence = worker_presence()
    except Exception:
        logger.exception("Sandbox worker local disk is not ready")
        os.kill(os.getpid(), signal.SIGTERM)
        return
    _heartbeat = SandboxWorkerHeartbeat(presence)
    _heartbeat.start()


def stop_worker_heartbeat(**kwargs) -> None:
    global _heartbeat
    if _heartbeat is not None:
        _heartbeat.stop()
        _heartbeat = None
