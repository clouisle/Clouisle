import asyncio
import sys
import time
from uuid import uuid4

from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.tasks import sandbox as tasks


def test_run_sandbox_job_task_returns_lightweight_real_execution_ack(sandbox_runtime):
    r = sandbox_runtime
    job = SandboxJob(
        command=[sys.executable, "-c", "print('ok')"], deadline_at=time.time() + 5
    )
    payload = job.model_dump(mode="json")
    r.run(r.results.create_queued_result(job.job_id, deadline_at=job.deadline_at))
    result = tasks.run_sandbox_job_task.run(payload)
    assert result == {
        "job_id": job.job_id,
        "status": SandboxTaskStatus.COMPLETED,
        "success": True,
    }
    assert r.run(r.results.get_result(job.job_id)).result == "ok"
    assert "stdout" not in result and "artifacts" not in result
    assert [event["action"] for event in r.audit_events] == [
        "sandbox_task_started",
        "sandbox_task_completed",
    ]
    assert all(event["resource_type"] == "sandbox_task" for event in r.audit_events)
    assert all(
        set(event["metadata"])
        == {"job_id", "session_id", "source", "worker_id", "error_code", "duration_ms"}
        for event in r.audit_events
    )
    assert "print('ok')" not in repr(r.audit_events)
    assert payload == job.model_dump(mode="json")
    duplicate = tasks.run_sandbox_job_task.run(payload)
    assert duplicate["success"]
    assert [event["action"] for event in r.audit_events] == [
        "sandbox_task_started",
        "sandbox_task_completed",
    ]


def test_session_task_audit_attributes_actor_and_team(sandbox_runtime):
    r = sandbox_runtime
    user_id, team_id = str(uuid4()), str(uuid4())
    r.bind_session(user_id=user_id, team_id=team_id)
    job = SandboxJob(command=[sys.executable, "-c", "print('session task')"])
    payload = r.submit_payload(job, team_id=team_id)

    tasks.run_sandbox_job_task.run(payload)

    events = [
        event for event in r.audit_events if event["metadata"]["job_id"] == job.job_id
    ]
    assert [event["action"] for event in events] == [
        "sandbox_task_started",
        "sandbox_task_completed",
    ]
    assert all(str(event["user_id"]) == user_id for event in events)
    assert all(str(event["team_id"]) == team_id for event in events)


def test_run_sandbox_job_task_records_process_failure(sandbox_runtime):
    r = sandbox_runtime
    job = SandboxJob(
        command=[
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('boom'); sys.exit(1)",
        ],
        deadline_at=time.time() + 5,
    )
    r.run(r.results.create_queued_result(job.job_id, deadline_at=job.deadline_at))
    ack = tasks.run_sandbox_job_task.run(job.model_dump(mode="json"))
    assert not ack["success"]
    result = r.run(r.results.get_result(job.job_id))
    assert result.status == SandboxTaskStatus.FAILED
    assert result.stderr == "boom"
    assert result.metadata.completed_at is not None
    assert [event["action"] for event in r.audit_events] == [
        "sandbox_task_started",
        "sandbox_task_failed",
    ]
    assert r.audit_events[-1]["status"] == "failed"
    assert "boom" not in repr(r.audit_events)


def test_old_message_without_absolute_deadline_cannot_execute(sandbox_runtime):
    r = sandbox_runtime
    job = SandboxJob(command=[sys.executable, "-c", "print('must not run')"])
    ack = tasks.run_sandbox_job_task.run(job.model_dump(mode="json"))
    assert not ack["success"]
    assert r.run(r.results.get_result(job.job_id)).error_code == "DEADLINE_EXCEEDED"
    assert [event["action"] for event in r.audit_events] == ["sandbox_task_failed"]


def test_get_worker_loop_reuses_current_event_loop():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        assert tasks._get_worker_loop() is loop
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_get_worker_loop_replaces_closed_event_loop():
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    loop = None
    try:
        asyncio.set_event_loop(closed_loop)
        loop = tasks._get_worker_loop()
        assert loop is not closed_loop and not loop.is_closed()
    finally:
        if loop is not None:
            loop.close()
        asyncio.set_event_loop(None)
