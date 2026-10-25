"""Feature-driven Feishu receiver supervision in existing Celery worker parents."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from tortoise.context import TortoiseContext

from app.core.config import settings
from app.models.integration import Integration
from app.services.integration_receiver_state import (
    RECEIVER_TTL_SECONDS,
    RECONCILE_SECONDS,
    RELEASE_SCRIPT,
    configured_receiver,
    receiver_fingerprint,
    receiver_key,
    receiver_redis,
)

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass
class ManagedReceiver:
    process: subprocess.Popen
    owner: str
    fingerprint: str
    key: str


class IntegrationReceiverManager:
    """No task-pool slots: one parent thread manages an optional child process."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="integration-receivers", daemon=True
        )
        self.child: ManagedReceiver | None = None
        self._retry_after = 0.0
        self._failures = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=12)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                asyncio.run(self._serve())
            except Exception:
                logger.warning("Integration receiver supervisor restarting")
                self._stop.wait(RECONCILE_SECONDS)

    async def _serve(self) -> None:
        client = receiver_redis()
        try:
            while not self._stop.is_set():
                try:
                    # This thread owns its ORM context, separate from task pools.
                    async with TortoiseContext() as context:
                        await asyncio.wait_for(
                            context.init(
                                db_url=settings.DATABASE_URL,
                                modules={"models": ["app.models"]},
                            ),
                            timeout=5,
                        )
                        while not self._stop.is_set():
                            integration = await asyncio.wait_for(
                                Integration.get_or_none(provider_type="feishu"),
                                timeout=3,
                            )
                            await self.reconcile(integration, client)
                            await asyncio.to_thread(self._stop.wait, RECONCILE_SECONDS)
                except Exception:
                    logger.warning(
                        "Integration receiver reconciliation failed; retrying"
                    )
                    await self._stop_child(client)
                    await asyncio.to_thread(self._stop.wait, RECONCILE_SECONDS)
        finally:
            await self._stop_child(client)
            await client.aclose()

    async def reconcile(self, integration: Integration | None, client) -> None:
        desired = configured_receiver(integration)
        fingerprint = receiver_fingerprint(integration) if desired else None
        child = self.child
        if child is not None:
            if child.process.poll() is not None:
                await self._stop_child(client)
                self._failures += 1
                self._retry_after = time.monotonic() + min(
                    30, 2 ** min(self._failures, 5)
                )
            elif not desired or fingerprint != child.fingerprint:
                await self._stop_child(client)
                self._failures = 0
                self._retry_after = 0
            else:
                value = await client.get(child.key)
                presence = json.loads(value) if value else {}
                if presence.get("owner") == child.owner:
                    return
                # An expired/replaced owner must stop before trying to reclaim.
                await self._stop_child(client)
                self._retry_after = time.monotonic() + RECONCILE_SECONDS
        if not desired or self._stop.is_set() or time.monotonic() < self._retry_after:
            return
        key = receiver_key(integration.id)
        owner = str(uuid4())
        presence = json.dumps(
            {"owner": owner, "fingerprint": fingerprint, "state": "starting"}
        )
        if not await client.set(key, presence, nx=True, ex=RECEIVER_TTL_SECONDS):
            return
        try:
            env = dict(os.environ)
            env.update(
                {
                    "CLOUISLE_RECEIVER_OWNER": owner,
                    "CLOUISLE_RECEIVER_PARENT": str(os.getpid()),
                    "CLOUISLE_RECEIVER_FINGERPRINT": fingerprint,
                }
            )
            process = subprocess.Popen(
                [sys.executable, "-m", "app.services.feishu_agent_receiver"],
                cwd=BACKEND_DIR,
                env=env,
                stdin=subprocess.DEVNULL,
            )
            self.child = ManagedReceiver(process, owner, fingerprint, key)
        except Exception:
            await client.eval(RELEASE_SCRIPT, 1, key, owner)
            raise

    async def _stop_child(self, client) -> None:
        child, self.child = self.child, None
        if child is None:
            return
        if child.process.poll() is None:
            try:
                child.process.terminate()
                try:
                    await asyncio.to_thread(child.process.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    child.process.kill()
                    await asyncio.to_thread(child.process.wait, timeout=2)
            except ProcessLookupError:
                await asyncio.to_thread(child.process.wait, timeout=2)
        try:
            await client.eval(RELEASE_SCRIPT, 1, child.key, child.owner)
        except Exception:
            logger.warning("Receiver ownership cleanup unavailable; lease will expire")


_manager: IntegrationReceiverManager | None = None


def start_integration_receivers(sender=None, **kwargs) -> None:
    """Only existing Agent consumers are eligible to host a receiver."""
    global _manager
    queues = getattr(getattr(sender, "task_consumer", None), "queues", ())
    if "agent" not in {queue.name for queue in queues} or _manager is not None:
        return
    _manager = IntegrationReceiverManager()
    _manager.start()


def stop_integration_receivers(**kwargs) -> None:
    global _manager
    if _manager is not None:
        _manager.stop()
        _manager = None
