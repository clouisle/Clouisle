"""Failure, deadline, and cancellation boundaries for sandbox execution."""

import asyncio
import sys
import time
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.sandbox.models import SandboxJob, SandboxResult, SandboxTaskStatus
from app.services.sandbox.process_launcher import (
    SandboxIsolationError,
    SandboxProcessLauncher,
)


@pytest.mark.asyncio
async def test_launcher_rejects_network_proxy_without_filesystem_isolation():
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)

    with pytest.raises(SandboxIsolationError, match="requires filesystem isolation"):
        await launcher.launch([sys.executable, "-c", "pass"], network_proxy=Mock())


@pytest.mark.asyncio
async def test_launcher_rejects_unrestricted_network_with_egress_proxy():
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    with pytest.raises(SandboxIsolationError, match="unrestricted at once"):
        await launcher.launch(
            [sys.executable, "-c", "pass"],
            network_proxy=Mock(),
            network_unrestricted=True,
        )


@pytest.mark.asyncio
async def test_launcher_without_deadline_collects_complete_output():
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)

    result = await launcher.launch(
        [
            sys.executable,
            "-c",
            "import time; print('ready', flush=True); time.sleep(.02)",
        ],
        timeout_seconds=None,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "ready"
    assert not result.timed_out


@pytest.mark.asyncio
async def test_launcher_terminates_process_if_caller_is_cancelled(monkeypatch):
    process = Mock(pid=42, stdout=asyncio.StreamReader(), stderr=asyncio.StreamReader())
    process.wait = AsyncMock(side_effect=asyncio.CancelledError)
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    terminate = AsyncMock()
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(asyncio.CancelledError):
        await launcher.launch(["command"])

    terminate.assert_awaited_once_with(process)


def test_launcher_maps_cwd_outside_workspace_to_isolation_error(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which", lambda _: "/usr/bin/bwrap"
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    with pytest.raises(SandboxIsolationError, match="cwd escapes workspace"):
        launcher._isolated_launch(
            ["python"],
            cwd=str(tmp_path),
            env=None,
            workspace_root=str(workspace),
            cache_root=None,
            network_proxy=None,
            network_unrestricted=False,
            timeout_seconds=1,
        )


def test_gateway_records_recovery_failure_before_propagating(
    sandbox_runtime, monkeypatch
):
    runtime = sandbox_runtime
    binding = runtime.bind_session()
    job = SandboxJob(command=[sys.executable, "-c", "pass"])

    async def fail_recovery(*_args, **_kwargs):
        error = RuntimeError("worker recovery failed")
        error.code = "WORKER_UNAVAILABLE"
        raise error

    monkeypatch.setattr("app.services.sandbox.gateway.ensure_ready", fail_recovery)
    with pytest.raises(RuntimeError, match="worker recovery failed"):
        runtime.run(runtime.gateway.submit(job, session_id="session"))

    failed = [
        event
        for event in runtime.audit_events
        if event.get("action") == "sandbox_task_recovered"
    ]
    assert failed[-1]["status"] == "failed"
    assert failed[-1]["metadata"]["error_code"] == "WORKER_UNAVAILABLE"
    assert not runtime.messages
    assert binding.worker_id == "a"


def test_result_recovery_records_unexpected_failure_and_reraises(
    sandbox_runtime, monkeypatch
):
    runtime = sandbox_runtime
    binding = runtime.bind_session()
    result = SandboxResult(
        job_id="recovery-error",
        status=SandboxTaskStatus.FAILED,
        success=False,
        error_code="EXECUTION_UNCERTAIN",
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 5,
    )

    async def fail_recovery(*_args, **_kwargs):
        raise OSError("registry unavailable")

    monkeypatch.setattr("app.services.sandbox.gateway.ensure_ready", fail_recovery)
    with pytest.raises(OSError, match="registry unavailable"):
        runtime.run(runtime.gateway._recover_result_binding(result, time.time() + 5))

    event = [
        event
        for event in runtime.audit_events
        if event.get("action") == "sandbox_task_recovered"
    ][-1]
    assert event["status"] == "failed"
    assert event["metadata"]["error_code"] == "RECOVERY_FAILED"


def test_cancel_preserves_existing_terminal_result_without_duplicate_audit(
    sandbox_runtime,
):
    runtime = sandbox_runtime
    terminal = SandboxResult(
        job_id="already-done", status=SandboxTaskStatus.COMPLETED, success=True
    )
    runtime.run(runtime.results.save_result(terminal))

    result = runtime.run(runtime.gateway.cancel(terminal.job_id, reason="late cancel"))

    assert result.status == SandboxTaskStatus.COMPLETED
    assert not [
        event
        for event in runtime.audit_events
        if event.get("action") == "sandbox_task_cancelled"
    ]


def test_cancel_handles_missing_snapshot_and_uses_default_reason(sandbox_runtime):
    runtime = sandbox_runtime
    result = runtime.run(runtime.gateway.cancel("not-yet-created"))

    assert result.status == SandboxTaskStatus.CANCELLED
    assert result.error_code == "CANCELLED"
    assert result.error
    event = [
        event
        for event in runtime.audit_events
        if event.get("action") == "sandbox_task_cancelled"
    ][-1]
    assert event["metadata"]["session_id"] is None
    assert event["metadata"]["worker_id"] is None


def test_recovery_deadline_expires_before_session_lookup(sandbox_runtime):
    from app.services.sandbox.recovery import SandboxGuardLost, ensure_ready

    runtime = sandbox_runtime
    runtime.run(runtime.sessions.create(session_id="deadline-session"))

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(ensure_ready("deadline-session", time.time() - 1))

    assert error.value.code == "DEADLINE_EXCEEDED"
    assert not runtime.preparations


def test_recovery_stop_request_cancels_before_preparation(sandbox_runtime):
    from app.services.sandbox.recovery import (
        SandboxGuardLost,
        ensure_ready,
        sandbox_execution_scope,
    )

    runtime = sandbox_runtime
    runtime.register()
    runtime.run(runtime.sessions.create(session_id="cancel-session"))

    async def stop_requested():
        return True

    async def scenario():
        with sandbox_execution_scope(time.time() + 5, stop_requested):
            return await ensure_ready("cancel-session", time.time() + 5)

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(scenario())

    assert error.value.code == "CANCELLED"
    assert not runtime.preparations


def test_recovery_prepares_once_per_recovery_lease_and_reuses_canonical_binding(
    sandbox_runtime,
):
    """Concurrent callers inside one recovery lease coalesce into one preparation."""
    from app.services.sandbox import recovery

    runtime = sandbox_runtime
    runtime.register()
    runtime.run(runtime.sessions.create(session_id="coalesce"))
    prepared_before = len(runtime.preparations)

    async def scenario():
        runtime.prepare_gate = asyncio.Event()
        waiters = [
            asyncio.create_task(recovery.ensure_ready("coalesce", time.time() + 2))
            for _ in range(4)
        ]
        while len(runtime.preparations) == prepared_before:
            await asyncio.sleep(0)
        binding = await runtime.sessions.get_binding("coalesce")
        assert binding.status == "RECOVERING"
        runtime.prepare_gate.set()
        return [binding] + await asyncio.gather(*waiters)

    binding, *recovered = runtime.run(scenario())

    assert len(runtime.preparations) == prepared_before + 1
    assert all(item == recovered[0] for item in recovered)
    assert recovered[0].worker_id == "a"
    assert recovered[0].epoch > binding.epoch
    assert recovered[0].status == "READY"
    assert recovered[0].workspace_id == "coalesce"
    assert (runtime.roots["a"] / "sessions" / "coalesce" / "tmp").is_dir()


def test_recovery_without_session_raises_value_error(sandbox_runtime):
    from app.services.sandbox.recovery import ensure_ready

    runtime = sandbox_runtime
    runtime.run(runtime.sessions.create(session_id="gone"))
    runtime.run(runtime.sessions.delete("gone"))

    with pytest.raises(ValueError, match="not found or expired"):
        runtime.run(ensure_ready("gone", time.time() + 2))

    assert not runtime.preparations


def test_recovery_without_ready_workers_polls_until_deadline(sandbox_runtime):
    from app.services.sandbox.recovery import SandboxGuardLost, ensure_ready

    runtime = sandbox_runtime
    runtime.run(runtime.sessions.create(session_id="no-worker"))

    async def scenario():
        return await ensure_ready("no-worker", time.time() + 0.05)

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(scenario())

    assert error.value.code == "DEADLINE_EXCEEDED"
    assert not runtime.preparations


def test_lost_recovery_lease_returns_none_without_reset(sandbox_runtime):
    from app.services.sandbox import recovery
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    runtime = sandbox_runtime
    before = runtime.bind_session()
    workspace = SandboxWorkspaceManager(root=str(runtime.roots["a"]))
    prepared_before = len(runtime.preparations)

    async def scenario():
        runtime.prepare_gate = asyncio.Event()
        waiting = asyncio.create_task(
            recovery.ensure_ready("session", time.time() + 2, force=True)
        )
        while len(runtime.preparations) == prepared_before:
            await asyncio.sleep(0)

        owner = await runtime.sessions.get_binding("session")
        assert owner.recovery_id is not None
        runtime.redis.delete(runtime.sessions._recovery_key("session"))
        competing = await runtime.sessions.acquire_recovery(
            "session", owner, "competing-owner", 2
        )
        assert competing is not None
        winner = competing.model_copy(
            update={
                "epoch": competing.epoch + 1,
                "status": "READY",
                "recovery_id": None,
                "recovery_started_at": None,
            }
        )
        assert await runtime.sessions.commit_recovery(
            "session", competing, "competing-owner", winner
        )

        runtime.prepare_gate.set()
        return winner, await waiting

    winner, recovered = runtime.run(scenario())
    assert recovered == winner

    binding = runtime.run(runtime.sessions.get_binding("session"))
    assert binding == winner
    assert binding.generation == before.generation
    assert binding.reset_count == before.reset_count
    assert workspace.get_session_root(binding.workspace_id).is_dir()
    assert not [
        event
        for event in runtime.audit_events
        if event.get("action") == "sandbox_task_recovered"
    ]


def test_guard_job_rejects_expired_deadline_before_any_lookup(sandbox_runtime):
    from app.services.sandbox.recovery import SandboxGuardLost, guard_job

    runtime = sandbox_runtime
    runtime.bind_session()

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(guard_job("job-expired", "session", None, time.time() - 1))

    assert error.value.code == "DEADLINE_EXCEEDED"


def test_guard_job_rejects_already_terminal_job(sandbox_runtime):
    from app.services.sandbox.recovery import SandboxGuardLost, guard_job

    runtime = sandbox_runtime
    runtime.run(
        runtime.results.save_result(
            SandboxResult(
                job_id="already-terminal",
                status=SandboxTaskStatus.FAILED,
                success=False,
            )
        )
    )

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(guard_job("already-terminal", None, None, time.time() + 2))

    assert error.value.code == "CANCELLED"


def test_guard_job_rejects_lost_worker_lease_after_binding_check(sandbox_runtime):
    from app.services.sandbox.recovery import SandboxGuardLost, guard_job

    runtime = sandbox_runtime
    binding = runtime.bind_session()
    runtime.registry.remove(runtime.redis, runtime.workers["a"])

    with pytest.raises(SandboxGuardLost) as error:
        runtime.run(guard_job("job-lease", "session", binding, time.time() + 2))

    assert error.value.code == "EXECUTION_UNCERTAIN"


def test_presence_matches_requires_ready_worker_and_full_identity(sandbox_runtime):
    from app.services.sandbox import recovery

    runtime = sandbox_runtime
    binding = runtime.bind_session()
    presence = runtime.workers["a"]

    assert recovery.presence_matches(binding, presence)
    assert (
        recovery.presence_matches(
            binding, presence.model_copy(update={"instance_id": "other"})
        )
        is False
    )
    assert (
        recovery.presence_matches(
            binding,
            presence.model_copy(update={"instance_id": "other"}),
            instance=False,
        )
        is True
    )
    assert (
        recovery.presence_matches(binding, presence.model_copy(update={"ready": False}))
        is False
    )
    assert (
        recovery.presence_matches(
            binding, presence.model_copy(update={"node_id": "node-b"})
        )
        is False
    )
    assert recovery.presence_matches(binding, None) is False


def test_gateway_waiter_cancellation_remains_cancelled(sandbox_runtime, monkeypatch):
    runtime = sandbox_runtime
    runtime.run(
        runtime.results.save_result(
            SandboxResult(
                job_id="cancelled-waiter",
                status=SandboxTaskStatus.QUEUED,
                success=False,
            )
        )
    )
    entered = asyncio.Event()

    async def block_sleep(_seconds):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr("app.services.sandbox.gateway.asyncio.sleep", block_sleep)

    async def scenario():
        waiter = asyncio.create_task(
            runtime.gateway.await_result("cancelled-waiter", timeout_seconds=10)
        )
        await entered.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

    runtime.run(scenario())


def test_gateway_handles_task_enqueue_failure_by_propagating(
    sandbox_runtime, monkeypatch
):
    runtime = sandbox_runtime

    def reject_enqueue(*_args, **_kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(
        "app.tasks.sandbox.run_sandbox_job_task.apply_async", reject_enqueue
    )
    with pytest.raises(RuntimeError, match="broker unavailable"):
        runtime.run(
            runtime.gateway.submit(SandboxJob(command=[sys.executable, "-c", "pass"]))
        )
