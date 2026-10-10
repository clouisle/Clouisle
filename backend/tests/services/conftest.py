"""In-process Redis substitute and physical sandbox runtime for service regressions."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.sandbox import (
    audit,
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
from app.services.sandbox.process_launcher import SandboxProcessLauncher
from app.tasks import sandbox as tasks
from tests.services.fake_redis import AsyncFakeRedis, FakeRedis


@pytest.fixture
def sandbox_redis_clients():
    sync_client = FakeRedis()
    return sync_client, AsyncFakeRedis(sync_client)


@pytest.fixture
def sandbox_runtime(tmp_path, monkeypatch, sandbox_redis_clients):
    sync_client, client = sandbox_redis_clients
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
        audit_events=[],
        checkpoints=[],
        preparations=[],
        pending=[],
        prepare_gate=None,
    )

    async def capture_audit(**event):
        runtime.audit_events.append(event)
        return SimpleNamespace(**event)

    monkeypatch.setattr(audit, "sandbox_session_store", sessions)
    monkeypatch.setattr(audit.AuditLog, "create", capture_audit)
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

    # These unit tests exercise job mechanics without Linux namespaces. Dedicated
    # process-launcher and proxy tests cover network isolation and blocked hosts.
    class LocalProcessLauncher:
        def __init__(self, *args, **kwargs):
            self.delegate = SandboxProcessLauncher(filesystem_isolation_enabled=False)

        async def launch(self, command, **kwargs):
            kwargs.pop("network_proxy", None)
            return await self.delegate.launch(command, **kwargs)

    monkeypatch.setattr(manager, "SandboxProcessLauncher", LocalProcessLauncher)
    monkeypatch.setattr(settings, "SANDBOX_CHECKPOINT_ROOT", "")
    monkeypatch.setattr(settings, "SANDBOX_WORKER_RECOVERY_SECONDS", 0.3)
    monkeypatch.setattr(settings, "SANDBOX_RECOVERY_POLL_SECONDS", 0.005)
    monkeypatch.setattr(
        settings, "SANDBOX_WORKSPACE_ROOT", str(tmp_path / "caller" / "jobs")
    )
    monkeypatch.setattr(gateway.SandboxGateway, "_workspace_manager", None)
    monkeypatch.setattr(tasks, "_get_worker_loop", lambda: loop)
    monkeypatch.setattr(
        tasks,
        "sandbox_worker_id",
        lambda: runtime.current.worker_id if runtime.current else "stateless-worker",
    )
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
        lambda args, queue, **_kwargs: runtime.messages.append((queue, args)),
    )
    monkeypatch.setattr(
        tasks.evict_sandbox_session_task,
        "apply_async",
        lambda args, queue, **_kwargs: runtime.messages.append((queue, args)),
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
