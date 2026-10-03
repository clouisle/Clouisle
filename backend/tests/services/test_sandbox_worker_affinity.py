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
