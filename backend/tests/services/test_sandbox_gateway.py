"""Gateway authorization, deadline, recovery and terminal-result behavior."""

import asyncio
import sys
import time

import pytest

from app.services.sandbox import recovery
from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.services.sandbox.models import SandboxResult

from app.services.sandbox.affinity import sandbox_worker_queue
from app.tasks import sandbox as tasks


def test_create_session_reuses_only_same_authorized_conversation(sandbox_runtime):
    r = sandbox_runtime
    first = r.run(
        r.gateway.create_session(
            agent_id="agent",
            team_id="team",
            user_id="user",
            conversation_id="conversation",
        )
    )
    reused = r.run(
        r.gateway.create_session(
            agent_id="agent",
            team_id="team",
            user_id="user",
            conversation_id="conversation",
        )
    )
    assert reused == first
    other = r.run(
        r.gateway.create_session(
            agent_id="other",
            team_id="team",
            user_id="user",
            conversation_id="conversation",
        )
    )
    assert other != first


def test_session_without_conversation_gets_independent_identity(sandbox_runtime):
    r = sandbox_runtime
    first = r.run(r.gateway.create_session(team_id="team"))
    second = r.run(r.gateway.create_session(team_id="team"))
    assert first != second
    assert r.run(r.sessions.get(first)) is not None
    assert r.run(r.sessions.get(second)) is not None


def test_session_workspace_descriptor_authorizes_without_creating_caller_files(
    sandbox_runtime,
):
    r = sandbox_runtime
    r.run(
        r.sessions.create(
            session_id="session", agent_id="agent", team_id="team", user_id="user"
        )
    )
    assert r.run(r.gateway.get_session_workspace("session", agent_id="other")) is None
    assert r.run(r.gateway.get_session_workspace("session", team_id="other")) is None
    assert r.run(r.gateway.get_session_workspace("session", user_id="other")) is None
    descriptor = r.run(
        r.gateway.get_session_workspace(
            "session", agent_id="agent", team_id="team", user_id="user"
        )
    )
    assert descriptor.root.name == "session"
    assert not descriptor.root.exists()


def test_unauthorized_submit_cannot_bind_or_recover_session(sandbox_runtime):
    r = sandbox_runtime
    r.register()
    r.run(r.sessions.create(session_id="session", agent_id="owner", team_id="team"))
    with pytest.raises(ValueError, match="not found or expired"):
        r.run(
            r.gateway.submit(
                SandboxJob(command=[sys.executable, "-c", "print('bad')"]),
                session_id="session",
                agent_id="other",
            )
        )
    assert r.run(r.sessions.get_binding("session")) is None
    assert not r.preparations and not r.messages


def test_await_result_returns_real_worker_result(sandbox_runtime):
    r = sandbox_runtime
    r.bind_session()
    job = SandboxJob(command=[sys.executable, "-c", "print('finished')"])
    tasks.run_sandbox_job_task.run(r.submit_payload(job))
    result = r.run(
        r.gateway.await_result(job.job_id, timeout_seconds=1, poll_interval=0)
    )
    assert result.success and result.result == "finished"
    assert result.metadata.completed_at is not None
    assert result.metadata.total_ms is not None


def test_wait_timeout_is_terminal_and_rejects_late_queue_execution(sandbox_runtime):
    r = sandbox_runtime
    r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('late').write_text('bad')",
        ]
    )
    payload = r.submit_payload(job)
    result = r.run(
        r.gateway.await_result(job.job_id, timeout_seconds=0, poll_interval=0)
    )
    assert result.status == SandboxTaskStatus.FAILED
    assert result.metadata.completed_at is not None
    tasks.run_sandbox_job_task.run(payload)
    assert r.run(r.results.get_result(job.job_id)) == result
    binding = r.run(r.sessions.get_binding("session"))
    assert not (r.roots["a"] / "sessions" / binding.workspace_id / "late").exists()


def test_cancel_is_immutable_and_absolute_deadline_survives_serialization(
    sandbox_runtime,
):
    r = sandbox_runtime
    r.bind_session()
    deadline = time.time() + 2
    job = SandboxJob(
        command=[sys.executable, "-c", "raise RuntimeError('must not run')"]
    )
    with recovery.sandbox_execution_scope(deadline):
        r.run(r.gateway.submit(job, session_id="session"))
    payload = r.messages.pop()[1]
    assert payload["deadline_at"] == deadline
    cancelled = r.run(r.gateway.cancel(job.job_id, "stop"))
    tasks.run_sandbox_job_task.run(payload)
    assert (
        r.run(r.gateway.await_result(job.job_id)).status == SandboxTaskStatus.CANCELLED
    )
    assert r.run(r.results.get_result(job.job_id)) == cancelled


def test_poll_backoff_caps_without_changing_zero_polling(sandbox_runtime):
    api = sandbox_runtime.gateway
    assert api._advance_poll_interval(0) == 0
    assert api._advance_poll_interval(0.02) == 0.04
    assert api._advance_poll_interval(0.2) == 0.25


def test_cancelled_waiter_fences_queued_execution(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('cancelled').write_text('bad')",
        ]
    )
    payload = r.submit_payload(job)

    async def scenario():
        waiter = asyncio.create_task(
            r.gateway.await_result(job.job_id, timeout_seconds=10)
        )
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert await r.results.get_status(job.job_id) == SandboxTaskStatus.CANCELLED

    r.run(scenario())
    tasks.run_sandbox_job_task.run(payload)
    assert not (r.roots["a"] / "sessions" / binding.workspace_id / "cancelled").exists()


def test_cleanup_and_eviction_dispatch_to_owner_and_preserve_active_session(
    sandbox_runtime,
):
    r = sandbox_runtime
    live = r.bind_session(session_id="live")
    r.run(r.gateway.cleanup_session("live"))
    assert r.messages[0][0] == sandbox_worker_queue(live.worker_id)
    r.messages.clear()

    stale = r.bind_session(session_id="stale")
    r.run(r.sessions.begin_round("stale", "active-round", ttl_seconds=60))
    r.registry.remove(r.redis, r.workers[stale.worker_id])
    r.run(r.gateway.cleanup_session("stale"))
    assert r.run(r.sessions.get("stale")) is not None
    assert not r.messages


def test_idle_eviction_routes_only_inactive_bound_sessions(sandbox_runtime):
    r = sandbox_runtime
    idle = r.bind_session(session_id="idle")
    r.bind_session(session_id="active")
    r.run(r.sessions.create(session_id="unbound"))
    r.run(r.sessions.begin_round("active", "active-round", ttl_seconds=60))
    for session_id in ("idle", "active", "unbound"):
        r.redis.zadd(r.sessions.IDLE_INDEX_KEY, {session_id: 0})

    scheduled = r.run(r.gateway.evict_idle_sessions())

    assert scheduled == 1
    assert len(r.messages) == 1
    assert r.messages[0][0] == sandbox_worker_queue(idle.worker_id)
    assert r.redis.zscore(r.sessions.IDLE_INDEX_KEY, "unbound") is None
    assert r.redis.zscore(r.sessions.IDLE_INDEX_KEY, "active") == 0


def test_unbound_round_finishes_without_worker_dispatch(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.sessions.create(session_id="unbound-round"))
    r.run(r.gateway.begin_round("unbound-round", "round", ttl_seconds=60))

    r.run(r.gateway.finish_round("unbound-round", "round"))

    assert r.run(r.sessions.get_active_round("unbound-round")) is None
    assert not r.checkpoints


def test_cleanup_deletes_unbound_and_stale_inactive_sessions(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.sessions.create(session_id="unbound"))
    r.run(r.gateway.cleanup_session("unbound"))
    assert r.run(r.sessions.get("unbound")) is None

    binding = r.bind_session(session_id="stale")
    r.registry.remove(r.redis, r.workers[binding.worker_id])
    r.run(r.gateway.cleanup_session("stale"))
    assert r.run(r.sessions.get("stale")) is None
    assert not r.messages


def test_expired_cleanup_schedules_bound_owner_and_handles_empty_index(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session(session_id="expired")
    r.redis.zadd(r.sessions.INDEX_KEY, {"expired": 0})

    count = r.run(r.gateway.cleanup_expired_sessions())
    assert count == 1
    assert r.messages[0][0] == sandbox_worker_queue(binding.worker_id)
    r.redis.zrem(r.sessions.INDEX_KEY, "expired")
    assert r.run(r.gateway.cleanup_expired_sessions()) == 0


def test_obsolete_checkpoint_ack_finishes_round_without_replaying(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    r.run(r.gateway.begin_round("session", "round", ttl_seconds=60))

    async def obsolete(job_id, *, timeout_seconds):
        return SandboxResult(
            job_id=job_id,
            status=SandboxTaskStatus.FAILED,
            success=False,
            error_code="JOB_OBSOLETE",
        )

    monkeypatch.setattr(r.gateway, "await_result", obsolete)
    r.run(r.gateway.finish_round("session", "round"))

    assert r.run(r.sessions.get_active_round("session")) is None
    assert r.run(r.sessions.get_binding("session")) == binding


def test_submit_never_extends_a_precomputed_job_deadline(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 3
    job = SandboxJob(
        command=[sys.executable, "-c", "print('bounded')"], deadline_at=deadline
    )

    r.run(r.gateway.submit(job, session_id="session"))

    queue, payload = r.messages.pop()
    assert queue == sandbox_worker_queue(binding.worker_id)
    assert payload["deadline_at"] == deadline


def test_checkpoint_failure_propagates_and_keeps_round_open(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    r.bind_session()
    r.run(r.gateway.begin_round("session", "round", ttl_seconds=60))

    async def failed(job_id, *, timeout_seconds):
        return SandboxResult(
            job_id=job_id,
            status=SandboxTaskStatus.FAILED,
            success=False,
            error_code="CHECKPOINT_FAILED",
            error="checkpoint failed",
        )

    monkeypatch.setattr(r.gateway, "await_result", failed)
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        r.run(r.gateway.finish_round("session", "round"))
    assert r.run(r.sessions.get_active_round("session")) == "round"


def test_result_recovery_skips_stateless_expired_and_unchanged_bindings(
    sandbox_runtime,
):
    r = sandbox_runtime
    stateless = SandboxResult(
        job_id="stateless-error",
        status=SandboxTaskStatus.FAILED,
        success=False,
        error_code="WORKSPACE_UNAVAILABLE",
    )
    r.run(r.results.save_result(stateless))
    returned = r.run(r.gateway.await_result("stateless-error", timeout_seconds=2))
    assert returned.recovery is None

    binding = r.bind_session()
    expired = SandboxResult(
        job_id="expired-recovery",
        status=SandboxTaskStatus.FAILED,
        success=False,
        error_code="WORKSPACE_UNAVAILABLE",
        session_id="session",
        binding=binding,
        deadline_at=time.time() - 1,
    )
    r.run(r.gateway._recover_result_binding(expired, time.time() - 1))
    assert expired.recovery is None

    unchanged = SandboxResult(
        job_id="unchanged-recovery",
        status=SandboxTaskStatus.FAILED,
        success=False,
        error_code="EXECUTION_UNCERTAIN",
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 2,
    )
    r.run(r.gateway._recover_result_binding(unchanged, time.time() + 2))
    assert unchanged.recovery is None


def test_terminal_nonrecovery_error_returns_without_resetting_session(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    terminal = SandboxResult(
        job_id="terminal-error",
        status=SandboxTaskStatus.FAILED,
        success=False,
        error_code="POLICY_DENIED",
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 2,
    )
    r.run(r.results.save_result(terminal))

    result = r.run(r.gateway.await_result("terminal-error", timeout_seconds=2))

    assert result.error_code == "POLICY_DENIED"
    assert result.recovery is None
    assert r.run(r.sessions.get_binding("session")) == binding


def test_waiter_fails_cleanly_when_terminal_status_has_no_snapshot(
    sandbox_runtime, monkeypatch
):
    from unittest.mock import AsyncMock

    r = sandbox_runtime
    monkeypatch.setattr(
        r.results, "get_status", AsyncMock(return_value=SandboxTaskStatus.COMPLETED)
    )
    monkeypatch.setattr(r.results, "get_result", AsyncMock(return_value=None))

    async def fail_update(job_id, status, **kwargs):
        return SandboxResult(
            job_id=job_id,
            status=status,
            success=False,
            error_code=kwargs["error_code"],
            error=kwargs["error"],
        )

    monkeypatch.setattr(r.results, "update_status", fail_update)
    result = r.run(r.gateway.await_result("missing-snapshot", timeout_seconds=0))

    assert result.error_code == "DEADLINE_EXCEEDED"
    assert "timed out" in result.error


def test_waiter_times_out_for_unbound_result_without_absolute_deadline(sandbox_runtime):
    r = sandbox_runtime
    pending = SandboxResult(
        job_id="no-absolute-deadline", status=SandboxTaskStatus.QUEUED, success=False
    )
    r.run(r.results.save_result(pending))

    result = r.run(r.gateway.await_result(pending.job_id, timeout_seconds=0))

    assert result.status == SandboxTaskStatus.FAILED
    assert result.error_code == "DEADLINE_EXCEEDED"
    assert result.session_id is None and result.binding is None


def test_waiter_polls_stateless_context_until_timeout_without_recovery(sandbox_runtime):
    r = sandbox_runtime
    pending = SandboxResult(
        job_id="stateless-pending", status=SandboxTaskStatus.QUEUED, success=False
    )
    r.run(r.results.save_result(pending))

    result = r.run(r.gateway.await_result(pending.job_id, timeout_seconds=0.05))

    assert result.status == SandboxTaskStatus.FAILED
    assert result.error_code == "DEADLINE_EXCEEDED"
    assert result.session_id is None and result.binding is None
