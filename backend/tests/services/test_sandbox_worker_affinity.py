"""Session-local files must stay on their owning worker's filesystem."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.services.sandbox import gateway, manager
from app.services.sandbox.affinity import sandbox_worker_queue
from app.services.sandbox.models import (
    SandboxJob,
    SandboxResult,
    SandboxSession,
    SandboxTaskStatus,
)
from app.tasks import sandbox as tasks


class Sessions:
    def __init__(self):
        self.sessions = {}
        self.owners = {}
        self.active_rounds = {}
        self.workspace_rounds = {}
        self.evicted = set()
        self.idle_sessions = []
        self.expired_sessions = []

    async def idle_session_ids(self, cutoff):
        return list(self.idle_sessions)

    async def expired_session_ids(self):
        return list(self.expired_sessions)

    async def create(self, session_id, **kwargs):
        self.sessions[session_id] = SandboxSession(
            session_id=session_id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            **{key: value for key, value in kwargs.items() if key != "ttl_hours"},
        )

    async def get(self, session_id):
        return self.sessions.get(session_id)

    async def get_worker(self, session_id):
        return self.owners.get(session_id)

    async def claim_worker(self, session_id, worker_id):
        if session_id not in self.sessions:
            raise ValueError("Sandbox session not found or expired")
        return self.owners.setdefault(session_id, worker_id)

    async def get_active_round(self, session_id):
        return self.active_rounds.get(session_id)

    async def get_workspace_round(self, session_id):
        return self.workspace_rounds.get(session_id)

    async def mark_workspace_round(self, session_id, round_id):
        self.workspace_rounds[session_id] = round_id

    async def clear_workspace_round(self, session_id):
        self.workspace_rounds.pop(session_id, None)

    async def begin_round(self, session_id, round_id, ttl_seconds):
        self.active_rounds[session_id] = round_id

    async def finish_round(self, session_id, round_id):
        if self.active_rounds.get(session_id) == round_id:
            del self.active_rounds[session_id]

    async def mark_evicted(self, session_id):
        self.evicted.add(session_id)

    async def touch(self, session_id, **kwargs):
        session = self.sessions.get(session_id)
        if session is not None:
            session.last_accessed_at = datetime.now(UTC)
            if "disk_usage_bytes" in kwargs:
                session.disk_usage_bytes = kwargs["disk_usage_bytes"]
        return session

    async def delete(self, session_id):
        self.sessions.pop(session_id, None)
        self.owners.pop(session_id, None)
        self.active_rounds.pop(session_id, None)
        self.workspace_rounds.pop(session_id, None)


class Results:
    def __init__(self):
        self.results = {}

    async def create_queued_result(self, job_id, metadata):
        self.results[job_id] = SandboxResult(job_id=job_id, metadata=metadata)

    async def save_result(self, result):
        self.results[result.job_id] = result

    async def get_result(self, job_id):
        return self.results.get(job_id)

    async def update_status(self, job_id, status, **kwargs):
        self.results[job_id] = SandboxResult(job_id=job_id, status=status, **kwargs)

    async def get_status(self, job_id):
        result = self.results.get(job_id)
        return result.status if result is not None else None


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    loop = asyncio.new_event_loop()
    sessions = Sessions()
    results = Results()
    messages = []
    for module in (gateway, manager, tasks):
        monkeypatch.setattr(module, "sandbox_session_store", sessions)
    for module in (gateway, manager, tasks):
        monkeypatch.setattr(module, "sandbox_result_store", results)
    monkeypatch.setattr(tasks, "_get_worker_loop", lambda: loop)
    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(gateway.SandboxGateway, "_workspace_manager", None)
    monkeypatch.setattr(settings, "SANDBOX_WORKSPACE_ROOT", str(tmp_path / "caller"))
    monkeypatch.setattr(
        tasks.run_sandbox_job_task,
        "apply_async",
        lambda args, queue: messages.append((queue, args[0])),
    )
    yield loop, sessions, results, messages
    loop.close()


def select_worker(worker, root, monkeypatch):
    monkeypatch.setattr(tasks, "sandbox_worker_id", lambda: worker)
    monkeypatch.setattr(settings, "SANDBOX_WORKSPACE_ROOT", str(root))


def test_concurrent_first_deliveries_forward_and_preserve_session_files(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, results, messages = runtime
    api = gateway.SandboxGateway()
    session_id = loop.run_until_complete(api.create_session(team_id=None))
    first = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof.txt').write_text('owner-a')\nreturn 'written'",
    )
    second = SandboxJob(
        language="python",
        code="from pathlib import Path\nreturn Path('proof.txt').read_text()",
    )
    # Both submissions precede the first claim and therefore use the shared queue.
    for job in (first, second):
        loop.run_until_complete(api.submit(job, session_id=session_id))
    assert not (tmp_path / "caller").exists()
    first_message = messages.pop(0)[1]
    second_message = messages.pop(0)[1]
    select_worker("a", tmp_path / "a", monkeypatch)
    tasks.run_sandbox_job_task.run(first_message)
    assert results.results[first.job_id].success
    select_worker("b", tmp_path / "b", monkeypatch)
    tasks.run_sandbox_job_task.run(second_message)
    assert not (tmp_path / "b").exists()
    queue, forwarded = messages.pop(0)
    assert queue == sandbox_worker_queue("a")
    select_worker("a", tmp_path / "a", monkeypatch)
    tasks.run_sandbox_job_task.run(forwarded)
    assert results.results[second.job_id].result == "owner-a"
    assert sessions.owners[session_id] == "a"
    # A later submission is addressed directly, without being consumed by b.
    loop.run_until_complete(api.submit(second, session_id=session_id))
    assert messages.pop(0)[0] == sandbox_worker_queue("a")


def test_cleanup_delivered_to_wrong_worker_does_not_delete_foreign_workspace(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, results, messages = runtime
    session_id = "cleanup-session"
    loop.run_until_complete(sessions.create(session_id))
    sessions.owners[session_id] = "a"
    owning_root = tmp_path / "a" / "sessions" / session_id
    owning_root.mkdir(parents=True)
    (owning_root / "proof").write_text("retained")
    foreign_root = tmp_path / "b" / "sessions" / session_id
    foreign_root.mkdir(parents=True)
    (foreign_root / "proof").write_text("foreign")
    monkeypatch.setattr(
        tasks.cleanup_sandbox_session_task,
        "apply_async",
        lambda args, queue: messages.append((queue, args[0])),
    )
    select_worker("b", tmp_path / "b", monkeypatch)
    tasks.cleanup_sandbox_session_task.run(session_id)
    assert (owning_root / "proof").read_text() == "retained"
    assert sessions.owners[session_id] == "a"
    queue, forwarded = messages.pop(0)
    assert queue == sandbox_worker_queue("a")
    select_worker("a", tmp_path / "a", monkeypatch)
    tasks.cleanup_sandbox_session_task.run(forwarded)
    assert not owning_root.exists()
    assert (foreign_root / "proof").read_text() == "foreign"
    assert session_id not in sessions.owners


def test_unauthorized_first_delivery_cannot_claim_session(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, results, messages = runtime
    loop.run_until_complete(sessions.create("private", agent_id="owner"))
    payload = SandboxJob(language="python", code="return 1").model_dump(mode="json")
    payload.update(session_id="private", session_agent_id="other")
    select_worker("b", tmp_path / "b", monkeypatch)
    with pytest.raises(ValueError, match="not found or expired"):
        tasks.run_sandbox_job_task.run(payload)
    assert "private" not in sessions.owners
    assert not (tmp_path / "b").exists()
    assert results.results[payload["job_id"]].status == SandboxTaskStatus.FAILED


def test_checkpoint_idle_eviction_and_next_round_restore(
    runtime, tmp_path, monkeypatch
):
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    loop, sessions, results, messages = runtime
    session_id = "recoverable"
    loop.run_until_complete(sessions.create(session_id))
    select_worker("a", tmp_path / "a", monkeypatch)
    loop.run_until_complete(sessions.begin_round(session_id, "round-1", 3600))
    write = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof').write_text('saved')\nreturn 'written'",
    )
    tasks.run_sandbox_job_task.run(
        write.model_dump(mode="json") | {"session_id": session_id}
    )
    workspace = SandboxWorkspaceManager()
    live = workspace.get_session_root(session_id)
    tasks.checkpoint_sandbox_session_task.run(session_id, "checkpoint-1", "round-1")
    checkpoint = workspace.checkpoints.checkpoint_path(session_id)
    assert live.exists() and checkpoint.exists()
    assert results.results["checkpoint-1"].success
    sessions.sessions[session_id].last_accessed_at = datetime.now(UTC) - timedelta(
        hours=1
    )
    tasks.evict_sandbox_session_task.run(session_id, datetime.now(UTC).timestamp())
    assert not live.exists()
    assert checkpoint.exists()
    assert sessions.owners[session_id] == "a"
    loop.run_until_complete(sessions.begin_round(session_id, "round-2", 3600))
    read = SandboxJob(
        language="python",
        code="from pathlib import Path\nreturn Path('proof').read_text()",
    )
    tasks.run_sandbox_job_task.run(
        read.model_dump(mode="json") | {"session_id": session_id}
    )
    assert results.results[read.job_id].result == "saved"
    assert (live / "proof").read_text() == "saved"


def test_failed_checkpoint_preserves_data_and_next_round_uses_committed_state(
    runtime, tmp_path, monkeypatch
):
    import hashlib
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    loop, sessions, results, messages = runtime
    session_id = "failed-save"
    loop.run_until_complete(sessions.create(session_id))
    select_worker("a", tmp_path / "a", monkeypatch)
    loop.run_until_complete(sessions.begin_round(session_id, "committed", 3600))
    write = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof').write_text('committed')\nreturn 1",
    )
    tasks.run_sandbox_job_task.run(
        write.model_dump(mode="json") | {"session_id": session_id}
    )
    tasks.checkpoint_sandbox_session_task.run(session_id, "good-save", "committed")
    workspace = SandboxWorkspaceManager()
    checkpoint = workspace.checkpoints.checkpoint_path(session_id)
    previous_hash = hashlib.sha256(checkpoint.read_bytes()).digest()
    live = workspace.get_session_root(session_id)
    loop.run_until_complete(sessions.begin_round(session_id, "interrupted", 3600))
    overwrite = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof').write_text('partial')\nreturn 1",
    )
    tasks.run_sandbox_job_task.run(
        overwrite.model_dump(mode="json") | {"session_id": session_id}
    )
    outside = tmp_path / "outside"
    outside.write_text("untouched")
    (live / "escape").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        tasks.checkpoint_sandbox_session_task.run(session_id, "bad-save", "interrupted")
    assert not results.results["bad-save"].success
    assert (live / "proof").read_text() == "partial"
    assert hashlib.sha256(checkpoint.read_bytes()).digest() == previous_hash
    assert sessions.active_rounds[session_id] == "interrupted"
    sessions.sessions[session_id].last_accessed_at = datetime.now(UTC) - timedelta(
        hours=1
    )
    tasks.evict_sandbox_session_task.run(session_id, datetime.now(UTC).timestamp())
    assert live.exists()
    loop.run_until_complete(sessions.begin_round(session_id, "next-round", 3600))
    read = SandboxJob(
        language="python",
        code="from pathlib import Path\nreturn Path('proof').read_text()",
    )
    tasks.run_sandbox_job_task.run(
        read.model_dump(mode="json") | {"session_id": session_id}
    )
    assert results.results[read.job_id].result == "committed"
    assert not (live / "escape").exists()
    assert outside.read_text() == "untouched"


def test_checkpoint_forwarded_to_owner_commits_the_owner_workspace(
    runtime, tmp_path, monkeypatch
):
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    loop, sessions, results, _messages = runtime
    session_id = "checkpoint-affinity"
    loop.run_until_complete(sessions.create(session_id))
    select_worker("a", tmp_path / "a", monkeypatch)
    loop.run_until_complete(sessions.begin_round(session_id, "round-a", 3600))
    job = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof').write_text('owner-a')\nreturn 1",
    )
    tasks.run_sandbox_job_task.run(
        job.model_dump(mode="json") | {"session_id": session_id}
    )
    owner_workspace = SandboxWorkspaceManager().get_session_root(session_id)
    dispatched = []
    monkeypatch.setattr(
        tasks.checkpoint_sandbox_session_task,
        "apply_async",
        lambda args, queue: dispatched.append((queue, args)),
    )

    select_worker("b", tmp_path / "b", monkeypatch)
    forwarded = tasks.checkpoint_sandbox_session_task.run(
        session_id, "checkpoint-affinity-job", "round-a"
    )
    assert forwarded == {"job_id": "checkpoint-affinity-job", "forwarded_to": "a"}
    assert not (tmp_path / "b").exists()

    queue, args = dispatched.pop()
    assert queue == sandbox_worker_queue("a")
    select_worker("a", tmp_path / "a", monkeypatch)
    completed = tasks.checkpoint_sandbox_session_task.run(*args)

    assert completed == {"job_id": "checkpoint-affinity-job", "checkpointed": True}
    assert results.results["checkpoint-affinity-job"].success
    assert SandboxWorkspaceManager().checkpoints.checkpoint_path(session_id).is_file()
    assert (owner_workspace / "proof").read_text() == "owner-a"
    assert loop.run_until_complete(sessions.get_active_round(session_id)) is None


def test_checkpoint_failure_does_not_clear_a_newer_round(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, results, _messages = runtime
    session_id = "stale-checkpoint"
    loop.run_until_complete(sessions.create(session_id))
    sessions.owners[session_id] = "a"
    sessions.active_rounds[session_id] = "new-round"
    select_worker("a", tmp_path / "a", monkeypatch)

    with pytest.raises(ValueError, match="superseded round"):
        tasks.checkpoint_sandbox_session_task.run(
            session_id, "old-checkpoint", "old-round"
        )

    assert results.results["old-checkpoint"].status == SandboxTaskStatus.FAILED
    assert sessions.active_rounds[session_id] == "new-round"
    assert not (tmp_path / "a" / "checkpoints" / f"{session_id}.tar").exists()


def test_cleanup_preserves_active_and_refreshed_sessions_then_deletes_expired(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, _results, _messages = runtime
    session_id = "cleanup-retention"
    loop.run_until_complete(sessions.create(session_id))
    sessions.owners[session_id] = "a"
    select_worker("a", tmp_path / "a", monkeypatch)
    root = tmp_path / "a" / "sessions" / session_id
    root.mkdir(parents=True)
    proof = root / "proof"
    proof.write_text("retain while active")

    sessions.active_rounds[session_id] = "running"
    assert tasks.cleanup_sandbox_session_task.run(session_id, True) == {
        "session_id": session_id,
        "skipped": "active_round",
    }
    assert proof.read_text() == "retain while active"

    sessions.active_rounds.pop(session_id)
    assert tasks.cleanup_sandbox_session_task.run(session_id, True) == {
        "session_id": session_id,
        "skipped": "retention_refreshed",
    }
    assert proof.read_text() == "retain while active"
    assert tasks.cleanup_sandbox_session_task.run(session_id) == {
        "session_id": session_id,
        "cleaned": True,
    }
    assert not root.exists()
    assert session_id not in sessions.sessions


def test_cleanup_without_owner_only_removes_session_metadata(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, _results, _messages = runtime
    session_id = "owner-lost"
    loop.run_until_complete(sessions.create(session_id))
    select_worker("b", tmp_path / "b", monkeypatch)
    unowned_data = tmp_path / "b" / "sessions" / session_id / "proof"
    unowned_data.parent.mkdir(parents=True)
    unowned_data.write_text("do not guess workspace ownership")

    assert tasks.cleanup_sandbox_session_task.run(session_id) == {
        "session_id": session_id,
        "cleaned": True,
    }

    assert session_id not in sessions.sessions
    assert unowned_data.read_text() == "do not guess workspace ownership"


def test_eviction_restores_last_checkpoint_before_removing_interrupted_workspace(
    runtime, tmp_path, monkeypatch
):
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    loop, sessions, _results, _messages = runtime
    session_id = "evict-interrupted"
    loop.run_until_complete(sessions.create(session_id))
    select_worker("a", tmp_path / "a", monkeypatch)
    loop.run_until_complete(sessions.begin_round(session_id, "committed", 3600))
    write = SandboxJob(
        language="python",
        code="from pathlib import Path\nPath('proof').write_text('committed')\nreturn 1",
    )
    tasks.run_sandbox_job_task.run(
        write.model_dump(mode="json") | {"session_id": session_id}
    )
    tasks.checkpoint_sandbox_session_task.run(session_id, "commit", "committed")
    workspace = SandboxWorkspaceManager()
    live = workspace.get_session_root(session_id)
    (live / "proof").write_text("interrupted")
    sessions.workspace_rounds[session_id] = "interrupted"
    sessions.sessions[session_id].last_accessed_at = datetime.now(UTC) - timedelta(
        hours=1
    )

    result = tasks.evict_sandbox_session_task.run(
        session_id, datetime.now(UTC).timestamp()
    )

    assert result == {"session_id": session_id, "evicted": True}
    assert not live.exists()
    assert sessions.evicted == {session_id}
    restored = workspace.restore_session(session_id, allow_empty=False)
    assert (restored.root / "proof").read_text() == "committed"


def test_checkpoint_task_rejects_missing_owner_and_expired_session(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, results, _messages = runtime
    loop.run_until_complete(sessions.create("ownerless-checkpoint"))
    select_worker("worker-a", tmp_path / "worker-a", monkeypatch)

    with pytest.raises(ValueError, match="no owning worker"):
        tasks.checkpoint_sandbox_session_task.run(
            "ownerless-checkpoint", "ownerless-job", "round-1"
        )
    assert results.results["ownerless-job"].status == SandboxTaskStatus.FAILED

    loop.run_until_complete(sessions.create("expired-checkpoint"))
    sessions.owners["expired-checkpoint"] = "worker-a"
    sessions.sessions.pop("expired-checkpoint")
    with pytest.raises(ValueError, match="not found or expired"):
        tasks.checkpoint_sandbox_session_task.run(
            "expired-checkpoint", "expired-job", "round-1"
        )
    assert results.results["expired-job"].status == SandboxTaskStatus.FAILED


def test_gateway_without_owner_releases_round_without_checkpoint(runtime):
    loop, sessions, results, _messages = runtime
    session_id = "unused-sandbox-round"
    loop.run_until_complete(sessions.create(session_id))
    sessions.active_rounds[session_id] = "round-1"
    api = gateway.SandboxGateway()

    loop.run_until_complete(api.finish_round(session_id, "round-1"))

    assert loop.run_until_complete(sessions.get_active_round(session_id)) is None
    assert results.results == {}


def test_gateway_session_workspace_rejects_a_different_user(runtime):
    loop, sessions, _results, _messages = runtime
    session_id = "user-owned-session"
    loop.run_until_complete(
        sessions.create(session_id, user_id="user-a", team_id="team-a")
    )

    workspace = loop.run_until_complete(
        gateway.SandboxGateway().get_session_workspace(session_id, user_id="user-b")
    )

    assert workspace is None


def test_gateway_cleanup_retains_live_unowned_sessions_and_routes_expired_owned_ones(
    runtime, monkeypatch
):
    loop, sessions, _results, _messages = runtime
    api = gateway.SandboxGateway()
    loop.run_until_complete(sessions.create("unowned-cleanup"))

    loop.run_until_complete(api.cleanup_session("unowned-cleanup", expired_only=True))
    assert "unowned-cleanup" in sessions.sessions
    loop.run_until_complete(api.cleanup_session("unowned-cleanup"))
    assert "unowned-cleanup" not in sessions.sessions

    loop.run_until_complete(sessions.create("owned-expired"))
    sessions.owners["owned-expired"] = "worker-a"
    sessions.expired_sessions = ["owned-expired"]
    dispatched = []
    monkeypatch.setattr(
        tasks.cleanup_sandbox_session_task,
        "apply_async",
        lambda args, queue: dispatched.append((queue, args)),
    )
    assert loop.run_until_complete(api.cleanup_expired_sessions()) == 1
    assert dispatched == [(sandbox_worker_queue("worker-a"), ["owned-expired", True])]
    sessions.expired_sessions = []
    assert loop.run_until_complete(api.cleanup_expired_sessions()) == 0

    loop.run_until_complete(sessions.create("unowned-round"))
    sessions.active_rounds["unowned-round"] = "round-1"
    loop.run_until_complete(api.finish_round("unowned-round", "round-1"))
    assert loop.run_until_complete(sessions.get_active_round("unowned-round")) is None

    loop.run_until_complete(sessions.create("private-user", user_id="user-a"))
    assert (
        loop.run_until_complete(
            api.get_session_workspace("private-user", user_id="user-b")
        )
        is None
    )


def test_gateway_idle_eviction_skips_active_and_lost_sessions_and_targets_owner(
    runtime, tmp_path, monkeypatch
):
    loop, sessions, _results, _messages = runtime
    api = gateway.SandboxGateway()
    for session_id in ("busy", "owner-lost", "owned-idle"):
        loop.run_until_complete(sessions.create(session_id))
        sessions.sessions[session_id].last_accessed_at = datetime.now(UTC) - timedelta(
            hours=2
        )
    sessions.owners.update({"busy": "worker-a", "owned-idle": "worker-a"})
    sessions.active_rounds["busy"] = "active"
    sessions.idle_sessions = ["busy", "owner-lost", "owned-idle"]
    dispatched = []
    monkeypatch.setattr(
        tasks.evict_sandbox_session_task,
        "apply_async",
        lambda args, queue: dispatched.append((queue, args)),
    )

    assert loop.run_until_complete(api.evict_idle_sessions()) == 1
    assert sessions.evicted == {"owner-lost"}
    assert len(dispatched) == 1
    queue, args = dispatched.pop()
    assert queue == sandbox_worker_queue("worker-a")
    assert args[0] == "owned-idle"

    select_worker("other-worker", tmp_path / "other", monkeypatch)
    forwarded = tasks.evict_sandbox_session_task.run(*args)
    assert forwarded == {"session_id": "owned-idle", "forwarded_to": "worker-a"}
    queue, owner_args = dispatched.pop()
    assert queue == sandbox_worker_queue("worker-a")
    select_worker("worker-a", tmp_path / "worker-a", monkeypatch)
    owner_lost = tasks.evict_sandbox_session_task.run(
        "owner-lost", datetime.now(UTC).timestamp()
    )
    assert owner_lost == {"session_id": "owner-lost", "evicted": False}

    sessions.sessions["owned-idle"].last_accessed_at = datetime.now(UTC)
    not_idle = tasks.evict_sandbox_session_task.run(*owner_args)
    assert not_idle == {"session_id": "owned-idle", "skipped": "not_idle"}
    sessions.sessions["owned-idle"].last_accessed_at = datetime.now(UTC) - timedelta(
        hours=2
    )
    evicted = tasks.evict_sandbox_session_task.run(*owner_args)
    assert evicted == {"session_id": "owned-idle", "evicted": False}
    assert sessions.evicted == {"owner-lost", "owned-idle"}


@pytest.mark.parametrize("unsafe_workspace", [False, True])
def test_gateway_finish_round_waits_for_owner_checkpoint_and_propagates_failure(
    runtime, tmp_path, monkeypatch, unsafe_workspace
):
    import threading

    from app.services.sandbox.workspace import SandboxWorkspaceManager

    loop, sessions, results, _messages = runtime
    session_id = "gateway-round-unsafe" if unsafe_workspace else "gateway-round"
    loop.run_until_complete(sessions.create(session_id))
    sessions.owners[session_id] = "worker-a"
    sessions.active_rounds[session_id] = "round-1"
    select_worker("worker-a", tmp_path / "worker-a", monkeypatch)
    workspace = SandboxWorkspaceManager().prepare_session(session_id)
    (workspace.root / "proof").write_text("checkpoint at round end")
    outside = tmp_path / "outside-workspace"
    if unsafe_workspace:
        outside.write_text("must remain untouched")
        (workspace.root / "escape").symlink_to(outside)

    dispatches = []
    worker_errors = []

    def dispatch(args, queue):
        dispatches.append((queue, args))

        def execute():
            worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(worker_loop)
            monkeypatch.setattr(tasks, "_get_worker_loop", lambda: worker_loop)
            try:
                tasks.checkpoint_sandbox_session_task.run(*args)
            except Exception as error:
                worker_errors.append(error)
            finally:
                worker_loop.close()
                asyncio.set_event_loop(None)

        worker = threading.Thread(target=execute)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()

    monkeypatch.setattr(tasks.checkpoint_sandbox_session_task, "apply_async", dispatch)
    api = gateway.SandboxGateway()

    if unsafe_workspace:
        with pytest.raises(RuntimeError):
            loop.run_until_complete(api.finish_round(session_id, "round-1"))
        assert results.results[dispatches[0][1][1]].status == SandboxTaskStatus.FAILED
        assert worker_errors
        assert (
            loop.run_until_complete(sessions.get_active_round(session_id)) == "round-1"
        )
        assert outside.read_text() == "must remain untouched"
    else:
        loop.run_until_complete(api.finish_round(session_id, "round-1"))
        job_id = dispatches[0][1][1]
        assert results.results[job_id].success
        assert not worker_errors
        assert loop.run_until_complete(sessions.get_active_round(session_id)) is None
        assert (
            SandboxWorkspaceManager().checkpoints.checkpoint_path(session_id).is_file()
        )

    assert dispatches[0][0] == sandbox_worker_queue("worker-a")
