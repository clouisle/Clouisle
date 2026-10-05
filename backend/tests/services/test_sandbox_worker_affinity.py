"""Versioned placement, stale lifecycle delivery and actual checkpoint recovery."""

import asyncio
import sys
import time

from app.services.sandbox import recovery
from app.services.sandbox.affinity import sandbox_worker_queue
from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.services.sandbox.workspace import SandboxWorkspaceManager
from app.tasks import sandbox as tasks


def test_first_submissions_are_prepared_and_addressed_to_one_ready_owner(
    sandbox_runtime,
):
    r = sandbox_runtime
    binding = r.bind_session()
    write = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('proof').write_text('owner-a')",
        ]
    )
    read = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('proof').read_text())",
        ]
    )
    r.run(r.gateway.submit(write, session_id="session"))
    r.run(r.gateway.submit(read, session_id="session"))
    assert all(
        queue == sandbox_worker_queue(binding.worker_id) for queue, _ in r.messages
    )
    first, second = r.messages[0][1], r.messages[1][1]
    r.messages.clear()
    assert tasks.run_sandbox_job_task.run(first)["success"]
    assert tasks.run_sandbox_job_task.run(second)["success"]
    assert r.run(r.results.get_result(read.job_id)).result == "owner-a"


def test_wrong_worker_rejects_message_without_forwarding_or_foreign_file_effect(
    sandbox_runtime,
):
    r = sandbox_runtime
    binding = r.bind_session()
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; Path('must-not-exist').write_text('bad')",
        ]
    )
    payload = r.submit_payload(job)
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")
    r.select("b")
    ack = tasks.run_sandbox_job_task.run(payload)
    assert not ack["success"]
    assert r.run(r.results.get_result(job.job_id)).error_code == "JOB_OBSOLETE"
    assert not (r.roots["b"] / "sessions" / binding.workspace_id).exists()
    assert not (
        r.roots["a"] / "sessions" / binding.workspace_id / "must-not-exist"
    ).exists()
    assert not r.messages


def test_stale_generation_execution_and_lifecycle_tasks_cannot_mutate_new_workspace(
    sandbox_runtime,
):
    r = sandbox_runtime
    before = r.bind_session()
    payload = r.submit_payload(
        SandboxJob(
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; Path('stale').write_text('bad')",
            ]
        )
    )
    r.registry.remove(r.redis, r.workers["a"])
    r.register("b", instance_id="instance-b", node_id="node-b", storage_id="storage-b")
    current = r.run(recovery.ensure_ready("session", time.time() + 2))
    r.select("b")
    tasks.run_sandbox_job_task.run(payload)
    new_root = r.roots["b"] / "sessions" / current.workspace_id
    (new_root / "proof").write_text("new data")
    expected = before.model_dump(mode="json")
    assert (
        tasks.cleanup_sandbox_session_task.run(
            "session", False, expected, time.time() + 2
        )["skipped"]
        == "obsolete_binding"
    )
    assert (
        tasks.evict_sandbox_session_task.run(
            "session", time.time() + 1, expected, time.time() + 2
        )["skipped"]
        == "obsolete_binding"
    )
    tasks.checkpoint_sandbox_session_task.run(
        "session", "stale-checkpoint", "round", expected, time.time() + 2
    )
    assert r.run(r.results.get_result("stale-checkpoint")).error_code == "JOB_OBSOLETE"
    assert (new_root / "proof").read_text() == "new data"
    assert not (new_root / "stale").exists()
    assert r.run(r.sessions.get_binding("session")) == current
    assert not r.messages


def test_checkpoint_idle_eviction_and_next_round_restore(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    r.run(r.gateway.begin_round("session", "round-1", ttl_seconds=60))
    payload = r.submit_payload(
        SandboxJob(
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; Path('proof').write_text('saved')",
            ]
        )
    )
    tasks.run_sandbox_job_task.run(payload)
    r.run(r.gateway.finish_round("session", "round-1"))
    workspace = SandboxWorkspaceManager(root=str(r.roots["a"]))
    archive = workspace.checkpoints.checkpoint_path(binding.workspace_id)
    assert archive.is_file()
    ack = tasks.evict_sandbox_session_task.run(
        "session", time.time() + 1, binding.model_dump(mode="json"), time.time() + 2
    )
    assert ack["evicted"]
    assert not workspace.get_session_root(binding.workspace_id).exists()
    r.run(r.gateway.begin_round("session", "round-2", ttl_seconds=60))
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('proof').read_text())",
        ]
    )
    tasks.run_sandbox_job_task.run(r.submit_payload(job))
    assert r.run(r.results.get_result(job.job_id)).result == "saved"
    assert archive.is_file()


def test_interrupted_round_reuses_only_last_committed_checkpoint(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    r.run(r.gateway.begin_round("session", "committed", ttl_seconds=60))
    tasks.run_sandbox_job_task.run(
        r.submit_payload(
            SandboxJob(
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('proof').write_text('committed')",
                ]
            )
        )
    )
    r.run(r.gateway.finish_round("session", "committed"))
    r.run(r.gateway.begin_round("session", "abandoned", ttl_seconds=60))
    tasks.run_sandbox_job_task.run(
        r.submit_payload(
            SandboxJob(
                command=[
                    sys.executable,
                    "-c",
                    "from pathlib import Path; Path('proof').write_text('dirty')",
                ]
            )
        )
    )
    r.run(r.gateway.begin_round("session", "next", ttl_seconds=60))
    read = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('proof').read_text())",
        ]
    )
    tasks.run_sandbox_job_task.run(r.submit_payload(read))
    assert r.run(r.results.get_result(read.job_id)).result == "committed"
    assert (
        r.roots["a"] / "sessions" / binding.workspace_id / "proof"
    ).read_text() == "committed"


def test_round_finish_crossing_reset_does_not_claim_old_checkpoint_or_fail_round(
    sandbox_runtime,
):
    r = sandbox_runtime
    before = r.bind_session()
    r.run(r.gateway.begin_round("session", "round", ttl_seconds=60))
    workspace = SandboxWorkspaceManager(root=str(r.roots["a"]))

    async def scenario():
        async with workspace.session_lock(before.workspace_id):
            finishing = asyncio.create_task(r.gateway.finish_round("session", "round"))
            while not r.checkpoints:
                await asyncio.sleep(0)
            r.registry.remove(r.redis, r.workers["a"])
            r.register(
                "b", instance_id="instance-b", node_id="node-b", storage_id="storage-b"
            )
            await finishing
        await asyncio.gather(*r.pending, return_exceptions=True)

    with recovery.capture_workspace_resets() as notices:
        r.run(scenario())
    assert notices and notices[0]["generation"] == before.generation + 1
    current = r.run(r.sessions.get_binding("session"))
    assert current.worker_id == "b"
    assert r.run(r.sessions.get_active_round("session")) is None
    assert not workspace.checkpoints.checkpoint_path(before.workspace_id).exists()
    checkpoint_id = r.checkpoints[0][1][1]
    assert r.run(r.results.get_status(checkpoint_id)) == SandboxTaskStatus.FAILED
