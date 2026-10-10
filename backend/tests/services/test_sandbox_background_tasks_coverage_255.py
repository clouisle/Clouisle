"""Fail-closed task boundaries and no blind command replay."""

import sys
import time
from unittest.mock import AsyncMock
import pytest


from app.schemas.response import BusinessError, ResponseCode
from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.tasks import sandbox as tasks

from app.services.sandbox.workspace import SandboxWorkspaceManager


def test_invalid_payload_records_terminal_failure_without_execution(sandbox_runtime):
    r = sandbox_runtime
    payload = {
        "job_id": "invalid",
        "source": "invalid-source",
        "deadline_at": time.time() + 2,
    }
    ack = tasks.run_sandbox_job_task.run(payload)
    assert not ack["success"]
    result = r.run(r.results.get_result("invalid"))
    assert result.status == SandboxTaskStatus.FAILED
    assert result.metadata.completed_at is not None
    assert result.metadata.started_at is None


def test_failure_persists_business_error_enum_code_as_string(sandbox_runtime):
    r = sandbox_runtime
    result = r.run(
        tasks._failure(
            "business-error",
            BusinessError(code=ResponseCode.UNKNOWN_ERROR, msg="business failure"),
        )
    )

    persisted = r.run(r.results.get_result("business-error"))
    assert persisted == result
    assert persisted.status == SandboxTaskStatus.FAILED
    assert persisted.error_code == str(ResponseCode.UNKNOWN_ERROR.value)


def test_failed_command_is_not_replayed_on_redelivery(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    command = "from pathlib import Path; p=Path('count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); raise RuntimeError('failed after effect')"
    job = SandboxJob(command=[sys.executable, "-c", command])
    payload = r.submit_payload(job)
    tasks.run_sandbox_job_task.run(payload)
    first = r.run(r.results.get_result(job.job_id))
    assert first.status == SandboxTaskStatus.FAILED
    tasks.run_sandbox_job_task.run(payload)
    assert r.run(r.results.get_result(job.job_id)) == first
    assert (
        r.roots["a"] / "sessions" / binding.workspace_id / "count"
    ).read_text() == "1"


def test_missing_executable_does_not_trigger_workspace_loss_reset(sandbox_runtime):
    r = sandbox_runtime
    before = r.bind_session()
    job = SandboxJob(command=["certainly-not-a-real-sandbox-executable"])
    tasks.run_sandbox_job_task.run(r.submit_payload(job))
    result = r.run(r.gateway.await_result(job.job_id, timeout_seconds=1))
    assert result.status == SandboxTaskStatus.FAILED
    assert result.error_code != "WORKSPACE_UNAVAILABLE"
    assert r.run(r.sessions.get_binding("session")) == before


def test_expired_session_job_fails_before_command_execution(sandbox_runtime, tmp_path):
    r = sandbox_runtime
    marker = tmp_path / "ran"
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        session_id="expired-session",
        deadline_at=time.time() + 2,
    )

    ack = tasks.run_sandbox_job_task.run(job.model_dump(mode="json"))

    result = r.run(r.results.get_result(job.job_id))
    assert not ack["success"]
    assert result.status == SandboxTaskStatus.FAILED
    assert "session not found or expired" in result.error
    assert not marker.exists()


def test_cleanup_waits_for_active_round_then_applies_retention(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    expected = binding.model_dump(mode="json")
    workspace = r.roots["a"] / "sessions" / binding.workspace_id
    r.run(r.sessions.begin_round("session", "round", ttl_seconds=60))

    active = tasks.cleanup_sandbox_session_task.run(
        "session", False, expected, time.time() + 2
    )
    assert active["skipped"] == "active_round"
    assert workspace.is_dir()

    r.run(r.sessions.finish_round("session", "round", expected_binding=binding))
    retained = tasks.cleanup_sandbox_session_task.run(
        "session", True, expected, time.time() + 2
    )
    assert retained["skipped"] == "retention_refreshed"

    cleaned = tasks.cleanup_sandbox_session_task.run(
        "session", False, expected, time.time() + 2
    )
    assert cleaned["cleaned"] is True
    assert r.run(r.sessions.get("session")) is None
    assert not workspace.exists()


def test_checkpoint_task_rejects_superseded_round(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    expected = binding.model_dump(mode="json")
    deadline = time.time() + 2
    r.run(r.sessions.begin_round("session", "current-round", ttl_seconds=60))
    r.run(
        r.results.create_queued_result(
            "stale-checkpoint",
            session_id="session",
            binding=binding,
            deadline_at=deadline,
        )
    )

    ack = tasks.checkpoint_sandbox_session_task.run(
        "session", "stale-checkpoint", "old-round", expected, deadline
    )

    result = r.run(r.results.get_result("stale-checkpoint"))
    assert not ack["success"]
    assert result.status == SandboxTaskStatus.FAILED
    assert r.run(r.sessions.get_active_round("session")) == "current-round"
    assert (
        not SandboxWorkspaceManager(root=str(r.roots["a"]))
        .checkpoints.checkpoint_path(binding.workspace_id)
        .exists()
    )


def test_eviction_skips_recent_and_active_work_then_restores_last_commit(
    sandbox_runtime,
):
    r = sandbox_runtime
    binding = r.bind_session()
    expected = binding.model_dump(mode="json")
    workspace = SandboxWorkspaceManager(root=str(r.roots["a"]))
    recent = tasks.evict_sandbox_session_task.run(
        "session", time.time() - 1, expected, time.time() + 2
    )
    assert recent["skipped"] == "not_idle"

    r.run(r.sessions.begin_round("session", "active-round", ttl_seconds=60))
    active = tasks.evict_sandbox_session_task.run(
        "session", time.time() + 1, expected, time.time() + 2
    )
    assert active["skipped"] == "active_round"
    r.run(r.sessions.finish_round("session", "active-round", expected_binding=binding))

    assert workspace.save_checkpoint(binding.workspace_id)
    r.run(
        r.sessions.mark_workspace_round(
            "session", "interrupted-round", expected_binding=binding
        )
    )
    evicted = tasks.evict_sandbox_session_task.run(
        "session", time.time() + 1, expected, time.time() + 2
    )
    assert evicted["evicted"] is True
    assert not workspace.get_session_root(binding.workspace_id).exists()
    assert workspace.checkpoints.checkpoint_path(binding.workspace_id).is_file()


def test_duplicate_claim_does_not_execute_or_change_queued_result(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[sys.executable, "-c", "from pathlib import Path; Path('ran').touch()"]
    )
    payload = r.submit_payload(job)
    monkeypatch.setattr(r.results, "claim_execution", AsyncMock(return_value=False))

    ack = tasks.run_sandbox_job_task.run(payload)

    assert ack["skipped"] == "duplicate_or_terminal"
    assert r.run(r.results.get_status(job.job_id)) == SandboxTaskStatus.QUEUED
    assert not (r.roots["a"] / "sessions" / binding.workspace_id / "ran").exists()


def test_lost_queued_job_is_obsolete_and_not_replayed(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[sys.executable, "-c", "from pathlib import Path; Path('ran').touch()"]
    )
    payload = r.submit_payload(job)
    r.registry.remove(r.redis, r.workers[binding.worker_id])

    ack = tasks.run_sandbox_job_task.run(payload)

    result = r.run(r.results.get_result(job.job_id))
    assert not ack["success"]
    assert result.error_code == "JOB_OBSOLETE"
    assert result.metadata.started_at is None
    assert not (r.roots["a"] / "sessions" / binding.workspace_id / "ran").exists()


def test_lost_started_job_preserves_uncertain_completion_warning(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(command=[sys.executable, "-c", "print('may have run')"])
    payload = r.submit_payload(job)
    existing = r.run(r.results.get_result(job.job_id))
    existing.metadata.mark_started()
    existing.status = SandboxTaskStatus.RUNNING
    r.run(r.results.save_result(existing))
    r.registry.remove(r.redis, r.workers[binding.worker_id])

    ack = tasks.run_sandbox_job_task.run(payload)

    result = r.run(r.results.get_result(job.job_id))
    assert not ack["success"]
    assert result.error_code == "EXECUTION_UNCERTAIN"
    assert "do not blindly replay" in result.error.lower()


def test_lifecycle_binding_rejects_missing_stale_and_expired_session_descriptors(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    expected = binding.model_dump(mode="json")

    assert r.run(tasks._lifecycle_binding("session", expected, deadline)) == binding
    assert r.run(tasks._lifecycle_binding("session", None, deadline)) is None
    stale = binding.model_copy(update={"generation": binding.generation + 1})
    assert (
        r.run(
            tasks._lifecycle_binding("session", stale.model_dump(mode="json"), deadline)
        )
        is None
    )
    monkeypatch.setattr(r.sessions, "get", AsyncMock(return_value=None))
    assert r.run(tasks._lifecycle_binding("session", expected, deadline)) is None


def test_workspace_preparation_rejects_a_different_worker_identity(sandbox_runtime):
    from app.services.sandbox.worker_registry import WorkerPresence

    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    job_id = "wrong-worker-prepare"
    r.run(r.results.create_queued_result(job_id, deadline_at=deadline))
    candidate = WorkerPresence(
        worker_id="worker-b",
        instance_id="instance-b",
        node_id="node-b",
        storage_id="storage-b",
    )

    ack = tasks.prepare_sandbox_workspace_task.run(
        "session",
        job_id,
        binding.model_dump(mode="json"),
        "recovery-token",
        candidate.model_dump(mode="json"),
        "other-workspace",
        False,
        deadline,
    )

    result = r.run(r.results.get_result(job_id))
    assert not ack["success"]
    assert result.error_code == "JOB_OBSOLETE"
    assert not (r.roots["a"] / "sessions" / "other-workspace").exists()


def test_workspace_preparation_aborts_when_recovery_lease_expires(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    job_id = "expired-recovery-lease"
    r.run(r.results.create_queued_result(job_id, deadline_at=deadline))
    monkeypatch.setattr(r.sessions, "recovery_matches", AsyncMock(return_value=False))

    ack = tasks.prepare_sandbox_workspace_task.run(
        "session",
        job_id,
        binding.model_dump(mode="json"),
        "expired-token",
        r.workers[binding.worker_id].model_dump(mode="json"),
        "other-workspace",
        False,
        deadline,
    )

    result = r.run(r.results.get_result(job_id))
    assert not ack["success"]
    assert result.error_code == "JOB_OBSOLETE"
    assert not (r.roots["a"] / "sessions" / "other-workspace").exists()


def test_cleanup_rechecks_binding_after_lock_and_keeps_workspace_on_store_conflict(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    expected = binding.model_dump(mode="json")
    original = tasks._lifecycle_binding
    checks = 0

    async def lose_binding_after_lock(
        session_id, descriptor, deadline_at, *, allow_expired=False
    ):
        nonlocal checks
        checks += 1
        return binding if checks == 1 else None

    monkeypatch.setattr(tasks, "_lifecycle_binding", lose_binding_after_lock)
    stale = tasks.cleanup_sandbox_session_task.run(
        "session", False, expected, time.time() + 2
    )
    assert stale["skipped"] == "obsolete_binding"
    assert r.run(r.sessions.get("session")) is not None
    monkeypatch.setattr(tasks, "_lifecycle_binding", original)

    monkeypatch.setattr(r.sessions, "delete", AsyncMock(return_value=False))
    conflict = tasks.cleanup_sandbox_session_task.run(
        "session", False, expected, time.time() + 2
    )
    assert conflict["skipped"] == "retention_refreshed"
    assert (r.roots["a"] / "sessions" / binding.workspace_id).is_dir()


def test_checkpoint_claim_and_empty_workspace_paths(sandbox_runtime, monkeypatch):
    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    expected = binding.model_dump(mode="json")
    r.run(
        r.results.create_queued_result(
            "duplicate-checkpoint",
            session_id="session",
            binding=binding,
            deadline_at=deadline,
        )
    )
    r.run(
        r.results.create_queued_result(
            "empty-checkpoint",
            session_id="session",
            binding=binding,
            deadline_at=deadline,
        )
    )
    monkeypatch.setattr(
        r.results, "claim_execution", AsyncMock(side_effect=[False, True])
    )

    duplicate = tasks.checkpoint_sandbox_session_task.run(
        "session", "duplicate-checkpoint", "round-a", expected, deadline
    )
    saved = tasks.checkpoint_sandbox_session_task.run(
        "session", "empty-checkpoint", "round-b", expected, deadline
    )

    assert duplicate["skipped"] == "duplicate_or_terminal"
    assert saved["success"] is True
    result = r.run(r.results.get_result("empty-checkpoint"))
    assert result.result["checkpointed"] is True


def test_eviction_rechecks_binding_before_deleting_workspace(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    expected = binding.model_dump(mode="json")
    checks = 0

    async def lose_binding_after_checkpoint(
        session_id, descriptor, deadline_at, *, allow_expired=False
    ):
        nonlocal checks
        checks += 1
        return binding if checks <= 2 else None

    monkeypatch.setattr(tasks, "_lifecycle_binding", lose_binding_after_checkpoint)
    result = tasks.evict_sandbox_session_task.run(
        "session", time.time() + 1, expected, time.time() + 2
    )

    assert result["evicted"] is False
    assert (r.roots["a"] / "sessions" / binding.workspace_id).is_dir()


def test_workspace_preparation_fences_worker_lease_and_session_changes(
    sandbox_runtime, monkeypatch
):
    from app.services.sandbox.worker_registry import WorkerPresence

    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    candidate = r.workers[binding.worker_id]
    other = WorkerPresence(
        worker_id="worker-b",
        instance_id="instance-b",
        node_id="node-b",
        storage_id="storage-b",
    )
    for job_id in ("wrong-worker", "expired-lease", "lost-worker", "expired-session"):
        r.run(r.results.create_queued_result(job_id, deadline_at=deadline))

    wrong = tasks.prepare_sandbox_workspace_task.run(
        "session",
        "wrong-worker",
        binding.model_dump(mode="json"),
        "token",
        other.model_dump(mode="json"),
        "foreign",
        False,
        deadline,
    )
    assert not wrong["success"]
    monkeypatch.setattr(r.sessions, "recovery_matches", AsyncMock(return_value=False))
    expired_lease = tasks.prepare_sandbox_workspace_task.run(
        "session",
        "expired-lease",
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "expired-lease-workspace",
        False,
        deadline,
    )
    assert not expired_lease["success"]

    monkeypatch.setattr(r.sessions, "recovery_matches", AsyncMock(return_value=True))
    original_registry_get = r.registry.get
    monkeypatch.setattr(r.registry, "get", AsyncMock(return_value=None))
    lost_worker = tasks.prepare_sandbox_workspace_task.run(
        "session",
        "lost-worker",
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "lost-worker-workspace",
        False,
        deadline,
    )
    assert not lost_worker["success"]

    monkeypatch.setattr(r.registry, "get", original_registry_get)
    original_session_get = r.sessions.get
    monkeypatch.setattr(r.sessions, "get", AsyncMock(return_value=None))
    expired_session = tasks.prepare_sandbox_workspace_task.run(
        "session",
        "expired-session",
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "expired-session-workspace",
        False,
        deadline,
    )
    assert not expired_session["success"]
    monkeypatch.setattr(r.sessions, "get", original_session_get)
    assert r.run(r.sessions.get_binding("session")) == binding
    for workspace_id in (
        "foreign",
        "expired-lease-workspace",
        "lost-worker-workspace",
        "expired-session-workspace",
    ):
        assert not (r.roots["a"] / "sessions" / workspace_id).exists()


def test_workspace_preparation_rejects_duplicate_and_reused_namespaces(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    candidate = r.workers[binding.worker_id]
    deadline = time.time() + 2
    ids = ("duplicate-prepare", "wrong-restore", "occupied-workspace")
    for job_id in ids:
        r.run(r.results.create_queued_result(job_id, deadline_at=deadline))
    monkeypatch.setattr(r.sessions, "recovery_matches", AsyncMock(return_value=True))
    monkeypatch.setattr(
        r.results, "claim_execution", AsyncMock(side_effect=[False, True, True])
    )

    duplicate = tasks.prepare_sandbox_workspace_task.run(
        "session",
        ids[0],
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "unused",
        False,
        deadline,
    )
    wrong_restore = tasks.prepare_sandbox_workspace_task.run(
        "session",
        ids[1],
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "different-workspace",
        True,
        deadline,
    )
    occupied_root = r.roots["a"] / "sessions" / "occupied"
    occupied_root.mkdir()
    occupied = tasks.prepare_sandbox_workspace_task.run(
        "session",
        ids[2],
        binding.model_dump(mode="json"),
        "token",
        candidate.model_dump(mode="json"),
        "occupied",
        False,
        deadline,
    )

    assert duplicate["skipped"] == "duplicate_or_terminal"
    assert not wrong_restore["success"]
    assert not occupied["success"]
    assert occupied_root.is_dir()


def test_checkpoint_fails_if_session_expires_before_locked_save(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    deadline = time.time() + 2
    r.run(
        r.results.create_queued_result(
            "expired-checkpoint",
            session_id="session",
            binding=binding,
            deadline_at=deadline,
        )
    )
    original_get = r.sessions.get
    calls = 0

    async def expire_after_validation(session_id):
        nonlocal calls
        calls += 1
        return await original_get(session_id) if calls == 1 else None

    monkeypatch.setattr(r.sessions, "get", expire_after_validation)
    ack = tasks.checkpoint_sandbox_session_task.run(
        "session",
        "expired-checkpoint",
        "round",
        binding.model_dump(mode="json"),
        deadline,
    )

    assert not ack["success"]
    assert r.run(r.results.get_status("expired-checkpoint")) == SandboxTaskStatus.FAILED
    assert (
        not SandboxWorkspaceManager(root=str(r.roots["a"]))
        .checkpoints.checkpoint_path(binding.workspace_id)
        .exists()
    )


def test_eviction_keeps_workspace_when_checkpoint_cannot_be_saved(
    sandbox_runtime, monkeypatch
):
    r = sandbox_runtime
    binding = r.bind_session()
    monkeypatch.setattr(
        SandboxWorkspaceManager, "save_checkpoint", lambda self, workspace_id: False
    )

    result = tasks.evict_sandbox_session_task.run(
        "session", time.time() + 1, binding.model_dump(mode="json"), time.time() + 2
    )

    assert result["evicted"] is False
    assert (r.roots["a"] / "sessions" / binding.workspace_id).is_dir()


def test_manager_fences_missing_binding_expired_deadline_and_wrong_scope(
    sandbox_runtime,
):
    from app.services.sandbox.manager import SandboxManager
    from app.services.sandbox.recovery import SandboxGuardLost

    r = sandbox_runtime
    binding = r.bind_session(
        agent_id="agent", team_id="00000000-0000-0000-0000-000000000001"
    )
    service = SandboxManager(cleanup_workspaces=False)
    unbound = SandboxJob(
        command=[sys.executable, "-c", "print('must not run')"], session_id="session"
    )
    with pytest.raises(SandboxGuardLost) as error:
        r.run(service._execute(unbound, session_id="session"))
    assert error.value.code == "JOB_OBSOLETE"

    with pytest.raises(SandboxGuardLost) as error:
        r.run(service.execute(unbound, session_id="session"))
    assert error.value.code == "EXECUTION_UNCERTAIN"

    expired = SandboxJob(
        command=[sys.executable, "-c", "print('must not run')"],
        deadline_at=time.time() - 1,
    )
    with pytest.raises(SandboxGuardLost) as error:
        r.run(service.execute(expired))
    assert error.value.code == "DEADLINE_EXCEEDED"

    stale = binding.model_copy(update={"generation": binding.generation + 1})
    stale_job = SandboxJob(
        command=[sys.executable, "-c", "print('must not run')"],
        session_id="session",
        binding=stale,
        deadline_at=time.time() + 2,
    )
    with pytest.raises(SandboxGuardLost):
        r.run(service.execute(stale_job))

    for scope in (
        {"session_agent_id": "other-agent"},
        {"session_team_id": "other-team"},
    ):
        job = SandboxJob(
            command=[sys.executable, "-c", "print('must not run')"],
            session_id="session",
            binding=binding,
            deadline_at=time.time() + 2,
        )
        with pytest.raises(ValueError, match="Sandbox session not found or expired"):
            r.run(service.execute(job, **scope))


def test_manager_does_not_start_command_if_round_binding_changes(
    sandbox_runtime, monkeypatch
):
    from app.services.sandbox.manager import SandboxManager
    from app.services.sandbox.recovery import SandboxGuardLost

    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('must-not-run').touch()",
        ],
        session_id="session",
        binding=binding,
        deadline_at=time.time() + 2,
    )
    monkeypatch.setattr(
        r.sessions, "mark_workspace_round", AsyncMock(return_value=False)
    )

    with pytest.raises(SandboxGuardLost, match="round binding changed"):
        r.run(SandboxManager(cleanup_workspaces=False).execute(job))

    assert not (
        r.roots["a"] / "sessions" / binding.workspace_id / "must-not-run"
    ).exists()
