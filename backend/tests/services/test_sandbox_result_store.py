"""Atomic result publication is observable under real Redis concurrency."""

import asyncio
import time

import pytest

from app.services.sandbox.models import SandboxResult, SandboxTaskStatus
from app.services.sandbox.result_store import SandboxResultFenceError


def test_save_and_load_result_with_explicit_ttl(sandbox_runtime):
    r = sandbox_runtime
    result = SandboxResult(
        job_id="job", status=SandboxTaskStatus.COMPLETED, success=True
    )
    stored = r.run(r.results.save_result(result, ttl_seconds=60))
    assert stored == result
    assert r.run(r.results.get_result("job")) == result
    assert r.run(r.results.get_status("job")) == SandboxTaskStatus.COMPLETED
    assert 0 < r.redis.ttl("sandbox:job:job") <= 60
    assert 0 < r.redis.ttl("sandbox:job:job:status") <= 60
    assert r.run(r.results.get_result("missing")) is None


def test_terminal_results_are_immutable_under_racing_writers(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.results.create_queued_result("job"))

    async def race():
        return await asyncio.gather(
            r.results.update_status(
                "job", SandboxTaskStatus.CANCELLED, error="cancelled"
            ),
            r.results.update_status(
                "job", SandboxTaskStatus.COMPLETED, success=True, result="done"
            ),
            r.results.update_status("job", SandboxTaskStatus.FAILED, error="late"),
        )

    published = r.run(race())
    winner = r.run(r.results.get_result("job"))
    assert all(result == winner for result in published)
    assert (
        r.run(
            r.results.save_result(
                SandboxResult(job_id="job", status=SandboxTaskStatus.RUNNING)
            )
        )
        == winner
    )
    assert r.run(r.results.get_status("job")) == winner.status


def test_claim_execution_rejects_duplicates_and_terminal_messages(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.results.create_queued_result("job"))
    assert r.run(r.results.claim_execution("job"))
    assert not r.run(r.results.claim_execution("job"))
    r.run(r.results.update_status("job", SandboxTaskStatus.FAILED, error="lost"))
    assert not r.run(r.results.claim_execution("job"))
    r.run(r.results.delete("job"))
    assert r.run(r.results.get_result("job")) is None
    assert r.run(r.results.get_status("job")) is None
    assert not r.redis.exists("sandbox:job:job:execution")


def test_queued_republication_cannot_erase_started_execution(sandbox_runtime):
    r = sandbox_runtime
    running = SandboxResult(job_id="job", status=SandboxTaskStatus.RUNNING)
    running.metadata.mark_started()
    r.run(r.results.save_result(running))
    republished = r.run(r.results.create_queued_result("job"))
    assert republished.status == SandboxTaskStatus.RUNNING
    assert republished.metadata.started_at == running.metadata.started_at


def test_late_binding_and_deadline_writes_cannot_publish_success(sandbox_runtime):
    r = sandbox_runtime
    binding = r.bind_session()
    r.run(r.results.create_queued_result("job", session_id="session", binding=binding))
    owned = r.run(r.sessions.acquire_recovery("session", binding, "recovery", 1))
    with pytest.raises(SandboxResultFenceError):
        r.run(
            r.results.save_result(
                SandboxResult(
                    job_id="job",
                    status=SandboxTaskStatus.COMPLETED,
                    success=True,
                    session_id="session",
                    binding=binding,
                )
            )
        )
    assert r.run(r.results.get_status("job")) == SandboxTaskStatus.QUEUED
    with pytest.raises(SandboxResultFenceError) as error:
        r.run(
            r.results.save_result(
                SandboxResult(
                    job_id="expired",
                    status=SandboxTaskStatus.COMPLETED,
                    success=True,
                    deadline_at=time.time() - 1,
                )
            )
        )
    assert error.value.code == "DEADLINE_EXCEEDED"
    assert r.run(r.results.get_result("expired")) is None
    assert owned.status == "RECOVERING"


def test_short_result_ttl_cannot_allow_duplicate_before_original_deadline(
    sandbox_runtime, monkeypatch
):
    from app.core.config import settings

    r = sandbox_runtime
    monkeypatch.setattr(settings, "SANDBOX_RESULT_TTL_SECONDS", 1)
    deadline = time.time() + 5
    r.run(r.results.create_queued_result("job", deadline_at=deadline))
    assert r.run(r.results.claim_execution("job", deadline))
    time.sleep(1.1)
    assert r.run(r.results.get_result("job")) is not None
    assert not r.run(r.results.claim_execution("job", deadline))
