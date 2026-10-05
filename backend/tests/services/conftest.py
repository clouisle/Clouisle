"""Opt-in real Redis and physical sandbox runtime for service regressions."""

import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError

from app.core.config import settings
from app.services.sandbox import (
    gateway,
    manager,
    recovery,
    result_store,
    session_store,
    worker_registry,
)
from app.services.sandbox.result_store import SandboxResultStore
from app.services.sandbox.session_store import SandboxSessionStore
from app.services.sandbox.worker_registry import SandboxWorkerRegistry, WorkerPresence
from app.tasks import sandbox as tasks


@pytest.fixture
def sandbox_runtime(tmp_path, monkeypatch):
    external_url = os.environ.get("SANDBOX_TEST_REDIS_URL")
    process = None
    temporary = None
    if external_url:
        # Point only at an isolated, disposable Docker Redis for this test run.
        sync_client = Redis.from_url(external_url, decode_responses=True)
        try:
            sync_client.ping()
            sync_client.flushdb()
        except ConnectionError as exc:
            sync_client.close()
            pytest.fail(f"test Docker Redis is unavailable: {exc}")
        client = AsyncRedis.from_url(external_url, decode_responses=True)
    else:
        binary = shutil.which("redis-server")
        if binary is None:
            pytest.skip(
                "real Redis is required; set SANDBOX_TEST_REDIS_URL to an isolated Docker Redis"
            )
        temporary = TemporaryDirectory(prefix="sandbox-core-redis-", dir="/tmp")
        socket_path = str(Path(temporary.name) / "redis.sock")
        process = subprocess.Popen(
            [
                binary,
                "--port",
                "0",
                "--unixsocket",
                socket_path,
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        sync_client = Redis(unix_socket_path=socket_path, decode_responses=True)
        ready_deadline = time.monotonic() + 5
        while True:
            try:
                sync_client.ping()
                break
            except ConnectionError:
                if process.poll() is not None or time.monotonic() >= ready_deadline:
                    process.terminate()
                    process.wait(timeout=5)
                    temporary.cleanup()
                    pytest.fail("test Redis did not start")
                time.sleep(0.01)
        client = AsyncRedis(unix_socket_path=socket_path, decode_responses=True)
    loop = asyncio.new_event_loop()
    sessions, results, registry = (
        SandboxSessionStore(),
        SandboxResultStore(),
        SandboxWorkerRegistry(),
    )
    runtime = SimpleNamespace(
        loop=loop,
        run=loop.run_until_complete,
        client=client,
        redis=sync_client,
        sessions=sessions,
        results=results,
        registry=registry,
        current=None,
        workers={},
        roots={},
        messages=[],
        checkpoints=[],
        preparations=[],
        pending=[],
        prepare_gate=None,
    )
    for module in (session_store, result_store, worker_registry):
        monkeypatch.setattr(module, "get_redis", AsyncMock(return_value=client))
    for module in (gateway, manager, recovery, tasks):
        monkeypatch.setattr(module, "sandbox_session_store", sessions)
        monkeypatch.setattr(module, "sandbox_result_store", results)
        if hasattr(module, "sandbox_worker_registry"):
            monkeypatch.setattr(module, "sandbox_worker_registry", registry)
    # These tests exercise worker mechanics; command-policy behavior has separate contract tests.
    monkeypatch.setattr(manager.sandbox_policy_engine, "validate", lambda job: None)
    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(settings, "SANDBOX_CHECKPOINT_ROOT", "")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_RECOVERY_SECONDS", 0.3)
    monkeypatch.setattr(settings, "SANDBOX_RECOVERY_POLL_SECONDS", 0.005)
    monkeypatch.setattr(
        settings, "SANDBOX_WORKSPACE_ROOT", str(tmp_path / "caller" / "jobs")
    )
    monkeypatch.setattr(gateway.SandboxGateway, "_workspace_manager", None)
    monkeypatch.setattr(tasks, "_get_worker_loop", lambda: loop)
    monkeypatch.setattr(tasks, "sandbox_worker_id", lambda: runtime.current.worker_id)
    monkeypatch.setattr(
        tasks, "sandbox_instance_id", lambda: runtime.current.instance_id
    )
    monkeypatch.setattr(tasks, "sandbox_node_id", lambda: runtime.current.node_id)
    monkeypatch.setattr(tasks, "sandbox_storage_id", lambda: runtime.current.storage_id)

    def select(worker_id):
        runtime.current = runtime.workers[worker_id]
        monkeypatch.setattr(
            settings, "SANDBOX_WORKSPACE_ROOT", str(runtime.roots[worker_id])
        )

    def register(
        worker_id="a",
        *,
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
    ):
        presence = WorkerPresence(
            worker_id=worker_id,
            instance_id=instance_id,
            node_id=node_id,
            storage_id=storage_id,
        )
        assert registry.refresh(sync_client, presence, 60)
        runtime.workers[worker_id] = presence
        runtime.roots.setdefault(worker_id, tmp_path / worker_id / "jobs")
        return presence

    def dispatch_prepare(args, queue):
        runtime.preparations.append((queue, args))

        async def consume():
            if runtime.prepare_gate is not None:
                await runtime.prepare_gate.wait()
            select(args[4]["worker_id"])
            return await tasks.prepare_workspace(*args)

        runtime.pending.append(asyncio.create_task(consume()))

    def dispatch_checkpoint(args, queue):
        runtime.checkpoints.append((queue, args))

        async def consume():
            select(args[3]["worker_id"])
            return await tasks.checkpoint_session(*args)

        runtime.pending.append(asyncio.create_task(consume()))

    def bind_session(session_id="session", worker_id="a", **authorization):
        if worker_id not in runtime.workers:
            register(worker_id)
        runtime.run(sessions.create(session_id=session_id, **authorization))
        binding = runtime.run(recovery.ensure_ready(session_id, time.time() + 2))
        select(binding.worker_id)
        return binding

    def submit_payload(job, session_id="session", **authorization):
        runtime.run(runtime.gateway.submit(job, session_id=session_id, **authorization))
        return runtime.messages.pop(0)[1]

    runtime.select, runtime.register = select, register
    runtime.bind_session, runtime.submit_payload = bind_session, submit_payload
    runtime.gateway = gateway.SandboxGateway()
    monkeypatch.setattr(
        tasks.prepare_sandbox_workspace_task, "apply_async", dispatch_prepare
    )
    monkeypatch.setattr(
        tasks.run_sandbox_job_task,
        "apply_async",
        lambda args, queue: runtime.messages.append((queue, args[0])),
    )
    monkeypatch.setattr(
        tasks.checkpoint_sandbox_session_task, "apply_async", dispatch_checkpoint
    )
    monkeypatch.setattr(
        tasks.cleanup_sandbox_session_task,
        "apply_async",
        lambda args, queue: runtime.messages.append((queue, args)),
    )
    monkeypatch.setattr(
        tasks.evict_sandbox_session_task,
        "apply_async",
        lambda args, queue: runtime.messages.append((queue, args)),
    )
    try:
        yield runtime
    finally:

        async def close():
            for task in runtime.pending:
                if not task.done():
                    task.cancel()
            if runtime.pending:
                await asyncio.gather(*runtime.pending, return_exceptions=True)
            await client.aclose()

        loop.run_until_complete(close())
        loop.close()
        sync_client.close()
        if process is not None:
            process.terminate()
            process.wait(timeout=5)
        if temporary is not None:
            temporary.cleanup()
