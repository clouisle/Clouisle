"""Real Redis/Lua, physical workspaces and subprocess recovery regressions."""

import asyncio
import sys
import time
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError

from app.services.sandbox import manager, recovery
from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.services.sandbox.workspace import SandboxWorkspaceManager


def test_first_binding_is_not_ready_until_physical_preparation_ack(sandbox_runtime):
    r = sandbox_runtime
    r.register()
    r.run(r.sessions.create(session_id="session"))

    async def scenario():
        r.prepare_gate = asyncio.Event()
        waiter = asyncio.create_task(recovery.ensure_ready("session", time.time() + 2))
        while not r.preparations:
            await asyncio.sleep(0)
        binding = await r.sessions.get_binding("session")
        assert binding.status == "RECOVERING"
        assert not (r.roots["a"] / "sessions" / "session").exists()
        r.prepare_gate.set()
        ready = await waiter
        assert ready.status == "READY"
        assert (r.roots["a"] / "sessions" / ready.workspace_id / "tmp").is_dir()

    r.run(scenario())


def test_same_storage_worker_restart_preserves_physical_files(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    proof = r.roots["a"] / "sessions" / before.workspace_id / "proof"
    proof.write_text("retained")
    r.registry.remove(r.redis, r.workers["a"])
    r.register(instance_id="instance-restarted")
    after = r.run(recovery.ensure_ready("session", time.time() + 2))
    assert after.instance_id == "instance-restarted"
    assert after.epoch > before.epoch
    assert after.generation == before.generation
    assert after.workspace_id == before.workspace_id
    assert proof.read_text() == "retained"


def test_worker_guard_rejects_session_job_without_binding(sandbox_runtime):
    r = sandbox_runtime
    r.bind_session()

    with pytest.raises(recovery.SandboxGuardLost) as error:
        r.run(recovery.guard_job("job", "session", None, time.time() + 2))

    assert error.value.code == "EXECUTION_UNCERTAIN"


def test_concurrent_recovery_prepares_once_and_atomic_rebind_loses_old_aliases(
    sandbox_runtime,
):
    r = sandbox_runtime
    before = r.bind_session()
    old = r.roots["a"] / "sessions" / before.workspace_id
    (old / "proof").write_text("old data")
    r.registry.remove(r.redis, r.workers["a"])
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")
    count = len(r.preparations)

    async def scenario():
        return await asyncio.gather(
            *(recovery.ensure_ready("session", time.time() + 2) for _ in range(6))
        )

    recovered = r.run(scenario())
    assert len(r.preparations) == count + 1
    assert all(b == recovered[0] for b in recovered)
    after = recovered[0]
    assert after.worker_id == "b" and after.generation == before.generation + 1
    assert after.workspace_id != before.workspace_id and after.reset_count == 1
    assert (r.roots["b"] / "sessions" / after.workspace_id / "tmp").is_dir()
    assert not (r.roots["b"] / "sessions" / after.workspace_id / "proof").exists()
    assert (old / "proof").read_text() == "old data"
    assert r.run(r.sessions.get_worker("session")) == "b"


def test_reset_producing_submit_reports_notice_and_does_not_replay(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    r.registry.remove(r.redis, r.workers["a"])
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")
    job = SandboxJob(
        command=[sys.executable, "-c", "raise RuntimeError('must not run')"]
    )
    with recovery.capture_workspace_resets() as notices:
        with pytest.raises(recovery.WorkspaceReset):
            r.run(r.gateway.submit(job, session_id="session"))
        assert notices[0]["code"] == "WORKSPACE_RESET"
        assert notices[0]["previous_worker_id"] == before.worker_id
        assert notices[0]["generation"] == before.generation + 1
        assert "authorized assets" in notices[0]["message"]
    assert not r.messages
    assert r.run(r.results.get_result(job.job_id)) is None
    current = r.run(r.sessions.get_binding("session"))
    descriptor = r.run(r.gateway.get_session_workspace("session"))
    assert descriptor.root.name == current.workspace_id
    recovery_events = [
        event for event in r.audit_events if event["action"] == "sandbox_task_recovered"
    ]
    assert len(recovery_events) == 1
    assert (
        recovery_events[0]["metadata"]["recovery"]["generation"] == current.generation
    )


def test_redis_unknown_does_not_reset_or_publish_new_placement(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    before = r.bind_session()
    monkeypatch.setattr(
        r.registry, "get", AsyncMock(side_effect=ConnectionError("unknown"))
    )
    with pytest.raises(ConnectionError):
        r.run(recovery.ensure_ready("session", time.time() + 2))
    assert r.run(r.sessions.get_binding("session")) == before


def test_lost_running_execution_is_uncertain_and_never_redispatched(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(command=[sys.executable, "-c", "print('side effect')"])
    r.submit_payload(job)
    existing = r.run(r.results.get_result(job.job_id))
    existing.metadata.mark_started()
    existing.status = SandboxTaskStatus.RUNNING
    r.run(r.results.save_result(existing))
    r.registry.remove(r.redis, r.workers["a"])
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")
    with recovery.capture_workspace_resets() as notices:
        final = r.run(r.gateway.await_result(job.job_id, timeout_seconds=2))
    assert final.error_code == "EXECUTION_UNCERTAIN"
    assert not r.messages
    assert notices and notices[0]["generation"] == binding.generation + 1
    assert r.run(r.results.get_result(job.job_id)).error_code == "EXECUTION_UNCERTAIN"
    assert any(event["action"] == "sandbox_task_failed" for event in r.audit_events)
    assert any(event["action"] == "sandbox_task_recovered" for event in r.audit_events)


def test_original_deadline_and_cancellation_bound_recovery(sandbox_runtime):
    r = sandbox_runtime

    async def cancelled():
        return True

    r.run(r.sessions.create(session_id="session"))
    with recovery.sandbox_execution_scope(time.time() + 0.03):
        with pytest.raises(recovery.SandboxGuardLost) as error:
            r.run(recovery.ensure_ready("session", time.time() + 20))
    assert error.value.code == "DEADLINE_EXCEEDED"
    with recovery.sandbox_execution_scope(stop_requested=cancelled):
        with pytest.raises(recovery.SandboxGuardLost) as error:
            r.run(recovery.ensure_ready("session", time.time() + 20))
    assert error.value.code == "CANCELLED"
    assert r.run(r.sessions.get_binding("session")) is None


def test_nested_recovery_scope_preserves_deadline_and_cancellation(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.sessions.create(session_id="expired"))
    r.run(r.sessions.delete("expired"))
    with pytest.raises(ValueError, match="not found or expired"):
        r.run(recovery.ensure_ready("expired", time.time() + 2))

    async def cancelled():
        return True

    outer_deadline = time.time() + 5
    with recovery.sandbox_execution_scope(outer_deadline, stop_requested=cancelled):
        with recovery.sandbox_execution_scope(time.time() + 10):
            assert recovery.bounded_deadline(time.time() + 20) == outer_deadline
            with pytest.raises(recovery.SandboxGuardLost) as error:
                r.run(recovery.check_scope(time.time() + 20))
    assert error.value.code == "CANCELLED"


def test_manager_cancellation_stops_real_background_writer(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "import pathlib,time\np=pathlib.Path('proof')\nwhile True:\n p.write_text(str(time.time_ns()))\n time.sleep(.01)",
        ],
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 5,
    )
    r.run(
        r.results.create_queued_result(
            job.job_id,
            session_id="session",
            binding=binding,
            deadline_at=job.deadline_at,
        )
    )
    service = manager.SandboxManager(cleanup_workspaces=False)
    proof = r.roots["a"] / "sessions" / binding.workspace_id / "proof"

    async def scenario():
        running = asyncio.create_task(service.execute(job))
        until = time.monotonic() + 3
        while not proof.exists():
            assert time.monotonic() < until
            await asyncio.sleep(0.01)
        await r.gateway.cancel(job.job_id)
        with pytest.raises(recovery.SandboxGuardLost):
            await running
        last = proof.read_text()
        await asyncio.sleep(0.15)
        assert proof.read_text() == last

    r.run(scenario())
    assert r.run(r.results.get_status(job.job_id)) == SandboxTaskStatus.CANCELLED


def test_failed_local_restore_resets_once_then_honors_reset_limit(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    workspace = SandboxWorkspaceManager(root=str(r.roots["a"]))
    r.run(r.sessions.touch("session", disk_usage_bytes=100, expected_binding=before))
    workspace.cleanup_session(before.workspace_id)
    after = r.run(recovery.ensure_ready("session", time.time() + 2, force=True))
    assert after.generation == before.generation + 1 and after.reset_count == 1
    assert after.workspace_id != before.workspace_id
    stale_force = r.run(
        recovery.ensure_ready(
            "session", time.time() + 2, force=True, expected_binding=before
        )
    )
    assert stale_force == after
    same_worker_recovery = r.run(
        recovery.ensure_ready(
            "session", time.time() + 2, force=True, expected_binding=after
        )
    )
    assert same_worker_recovery.epoch > after.epoch
    assert same_worker_recovery.generation == after.generation
    assert same_worker_recovery.workspace_id == after.workspace_id
    after = same_worker_recovery
    assert workspace.get_session_root(after.workspace_id).is_dir()
    r.run(r.sessions.touch("session", disk_usage_bytes=100, expected_binding=after))
    workspace.cleanup_session(after.workspace_id)
    with pytest.raises(recovery.SandboxUnavailable):
        r.run(recovery.ensure_ready("session", time.time() + 2, force=True))
    unavailable = r.run(r.sessions.get_binding("session"))
    assert unavailable.status == "UNAVAILABLE" and unavailable.reset_count == 1
    assert unavailable.generation == after.generation


def test_waiters_crossing_reset_all_reject_old_prepared_commands(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    r.registry.remove(r.redis, r.workers["a"])
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")

    async def scenario():
        await r.gateway.get_session_workspace("session")
        return await asyncio.gather(
            *(
                r.gateway.submit(
                    SandboxJob(command=[sys.executable, "-c", "print('must not run')"]),
                    session_id="session",
                )
                for _ in range(6)
            ),
            return_exceptions=True,
        )

    with recovery.capture_workspace_resets() as notices:
        errors = r.run(scenario())
    assert all(isinstance(error, recovery.WorkspaceReset) for error in errors)
    assert len(notices) == 1 and notices[0]["generation"] == before.generation + 1
    assert not r.messages


def test_worker_lease_loss_stops_real_writer_and_cannot_publish_success(
    sandbox_runtime,
):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "import pathlib,time\np=pathlib.Path('proof')\nwhile True:\n p.write_text(str(time.time_ns()))\n time.sleep(.01)",
        ],
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 5,
    )
    r.run(
        r.results.create_queued_result(
            job.job_id,
            session_id="session",
            binding=binding,
            deadline_at=job.deadline_at,
        )
    )
    service = manager.SandboxManager(cleanup_workspaces=False)
    proof = r.roots["a"] / "sessions" / binding.workspace_id / "proof"

    async def scenario():
        running = asyncio.create_task(service.execute(job))
        until = time.monotonic() + 3
        while not proof.exists():
            assert time.monotonic() < until
            await asyncio.sleep(0.01)
        r.registry.remove(r.redis, r.workers["a"])
        with pytest.raises(recovery.SandboxGuardLost) as error:
            await running
        assert error.value.code == "EXECUTION_UNCERTAIN"
        final_contents = proof.read_text()
        await asyncio.sleep(0.15)
        assert proof.read_text() == final_contents

    r.run(scenario())
    assert r.run(r.results.get_status(job.job_id)) != SandboxTaskStatus.COMPLETED


def test_preparation_waiting_on_busy_workspace_obeys_original_deadline(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    workspace = SandboxWorkspaceManager(root=str(r.roots["a"]))

    async def scenario():
        async with workspace.session_lock(binding.workspace_id):
            with recovery.sandbox_execution_scope(time.time() + 0.03):
                with pytest.raises(recovery.SandboxGuardLost) as error:
                    await recovery.ensure_ready("session", time.time() + 20, force=True)
            assert error.value.code == "DEADLINE_EXCEEDED"
            # The worker-side coroutine must also exit while the lock is still
            # held, not linger forever after its caller has timed out.
            await asyncio.wait_for(
                asyncio.gather(*r.pending, return_exceptions=True), 0.3
            )
        assert (
            await r.sessions.get_binding("session")
        ).generation == binding.generation

    r.run(scenario())


def test_initial_binding_fails_closed_when_worker_lease_disappears_before_ack(
    sandbox_runtime,
):
    r = sandbox_runtime
    worker = r.register()
    r.run(r.sessions.create(session_id="session"))

    async def scenario():
        r.prepare_gate = asyncio.Event()
        waiting = asyncio.create_task(
            recovery.ensure_ready("session", time.time() + 0.12)
        )
        while not r.preparations:
            await asyncio.sleep(0)
        r.registry.remove(r.redis, worker)
        with pytest.raises(recovery.SandboxGuardLost):
            await waiting

    r.run(scenario())
    binding = r.run(r.sessions.get_binding("session"))
    assert binding.status != "READY"
    assert not (r.roots[worker.worker_id] / "sessions" / "session").exists()

    r.prepare_gate.set()
    r.register(
        "worker-b", instance_id="instance-b", node_id="node-b", storage_id="storage-b"
    )
    recovered = r.run(recovery.ensure_ready("session", time.time() + 2))
    assert recovered.status == "READY"
    assert recovered.worker_id == "worker-b"
    assert recovered.generation == binding.generation + 1
    assert (r.roots["worker-b"] / "sessions" / recovered.workspace_id).is_dir()


def test_same_worker_with_replaced_storage_gets_a_fresh_generation(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    old_root = r.roots[before.worker_id] / "sessions" / before.workspace_id
    (old_root / "proof").write_text("must stay on old storage")
    r.registry.remove(r.redis, r.workers[before.worker_id])
    replacement = r.register(
        before.worker_id,
        instance_id="replacement-instance",
        node_id=before.node_id,
        storage_id="replacement-storage",
    )

    after = r.run(recovery.ensure_ready("session", time.time() + 2))

    assert after.worker_id == before.worker_id
    assert after.storage_id == replacement.storage_id
    assert after.generation == before.generation + 1
    assert after.workspace_id != before.workspace_id
    assert (old_root / "proof").read_text() == "must stay on old storage"
    assert not (
        r.roots[before.worker_id] / "sessions" / after.workspace_id / "proof"
    ).exists()


def test_restart_during_checkpoint_restore_retries_on_new_instance(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    workspace = SandboxWorkspaceManager(root=str(r.roots[before.worker_id]))
    proof = workspace.get_session_root(before.workspace_id) / "proof"
    proof.write_text("committed")
    assert workspace.save_checkpoint(before.workspace_id)
    r.run(
        r.sessions.mark_workspace_round(
            "session", "interrupted-round", expected_binding=before
        )
    )
    proof.write_text("uncommitted")
    prepared_before = len(r.preparations)

    async def scenario():
        r.prepare_gate = asyncio.Event()
        waiting = asyncio.create_task(
            recovery.ensure_ready("session", time.time() + 2, force=True)
        )
        while len(r.preparations) == prepared_before:
            await asyncio.sleep(0)
        r.registry.remove(r.redis, r.workers[before.worker_id])
        restarted = r.register(
            before.worker_id,
            instance_id="restarted-instance",
            node_id=before.node_id,
            storage_id=before.storage_id,
        )
        r.prepare_gate.set()
        return restarted, await waiting

    restarted, after = r.run(scenario())

    assert after.instance_id == restarted.instance_id
    assert after.epoch > before.epoch
    assert after.generation == before.generation
    assert after.workspace_id == before.workspace_id
    assert proof.read_text() == "committed"
