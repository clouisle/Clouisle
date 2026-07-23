import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.sandbox import (
    _get_worker_loop,
    cleanup_expired_sandbox_sessions_task,
    run_sandbox_job_task,
)


class DummyResult:
    job_id = "job-123"
    status = "completed"
    success = True
    result = {"large": "payload"}
    stdout = "logs"
    stderr = ""
    artifacts = [{"path": "/workspace/output.txt"}]


class DummyManager:
    def __init__(self):
        self.execute_args = None

    async def execute(self, job, **kwargs):
        self.execute_args = (job, kwargs)
        return DummyResult()


def test_run_sandbox_job_task_returns_lightweight_ack():
    payload = {
        "job_id": "job-123",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
    }

    with patch("app.tasks.sandbox.SandboxManager", return_value=DummyManager()):
        result = run_sandbox_job_task.run(payload)

    assert result == {
        "job_id": "job-123",
        "status": "completed",
        "success": True,
    }
    assert payload == {
        "job_id": "job-123",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
    }


def test_run_sandbox_job_task_marks_result_failed_on_exception():
    payload = {
        "job_id": "job-456",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
    }

    class FailingManager:
        async def execute(self, job, **kwargs):
            raise RuntimeError("boom")

    with (
        patch("app.tasks.sandbox.SandboxManager", return_value=FailingManager()),
        patch(
            "app.tasks.sandbox.sandbox_result_store.get_result",
            new=AsyncMock(return_value=None),
        ) as mock_get,
        patch(
            "app.tasks.sandbox.sandbox_result_store.update_status", new=AsyncMock()
        ) as mock_update,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_sandbox_job_task.run(payload)

    mock_get.assert_awaited_once_with("job-456")
    mock_update.assert_awaited_once()
    args, kwargs = mock_update.await_args
    assert args[0] == "job-456"
    assert args[1] == "failed"
    assert kwargs["error"] == "boom"


def test_run_sandbox_job_task_forwards_and_removes_session_context():
    payload = {
        "job_id": "job-session",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
        "session_id": "session-123",
        "session_agent_id": "agent-123",
        "session_team_id": "team-123",
    }
    manager = DummyManager()

    with patch("app.tasks.sandbox.SandboxManager", return_value=manager):
        run_sandbox_job_task.run(payload)

    assert payload == {
        "job_id": "job-session",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
    }
    _, kwargs = manager.execute_args
    assert kwargs == {
        "session_id": "session-123",
        "session_agent_id": "agent-123",
        "session_team_id": "team-123",
    }


def test_cleanup_expired_sandbox_sessions_task_returns_cleaned_count():
    with patch(
        "app.tasks.sandbox.sandbox_gateway.cleanup_expired_sessions",
        new=AsyncMock(return_value=2),
    ) as mock_cleanup:
        result = cleanup_expired_sandbox_sessions_task.run()

    assert result == {"cleaned": 2}
    mock_cleanup.assert_awaited_once()


def test_cleanup_expired_sandbox_sessions_task_reraises_errors():
    with patch(
        "app.tasks.sandbox.sandbox_gateway.cleanup_expired_sessions",
        new=AsyncMock(side_effect=RuntimeError("cleanup failed")),
    ):
        with pytest.raises(RuntimeError, match="cleanup failed"):
            cleanup_expired_sandbox_sessions_task.run()


def test_get_worker_loop_reuses_current_event_loop():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        assert _get_worker_loop() is loop
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_get_worker_loop_replaces_closed_event_loop():
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()
    try:
        asyncio.set_event_loop(closed_loop)
        loop = _get_worker_loop()
        assert loop is not closed_loop
        assert not loop.is_closed()
    finally:
        loop.close()
        asyncio.set_event_loop(None)
