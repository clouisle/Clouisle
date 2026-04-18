import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.sandbox import _get_worker_loop, run_sandbox_job_task


class DummyResult:
    job_id = "job-123"
    status = "completed"
    success = True
    result = {"large": "payload"}
    stdout = "logs"
    stderr = ""
    artifacts = [{"path": "/workspace/output.txt"}]


class DummyManager:
    async def execute(self, job):
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


def test_run_sandbox_job_task_marks_result_failed_on_exception():
    payload = {
        "job_id": "job-456",
        "source": "debug",
        "command": ["python3", "-c", "print('ok')"],
    }

    class FailingManager:
        async def execute(self, job):
            raise RuntimeError("boom")

    with (
        patch("app.tasks.sandbox.SandboxManager", return_value=FailingManager()),
        patch("app.tasks.sandbox.sandbox_result_store.update_status", new=AsyncMock()) as mock_update,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_sandbox_job_task.run(payload)

    mock_update.assert_awaited_once()
    args, kwargs = mock_update.await_args
    assert args[0] == "job-456"
    assert args[1] == "failed"
    assert kwargs["error"] == "boom"


def test_get_worker_loop_reuses_current_event_loop():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        assert _get_worker_loop() is loop
    finally:
        loop.close()
        asyncio.set_event_loop(None)
