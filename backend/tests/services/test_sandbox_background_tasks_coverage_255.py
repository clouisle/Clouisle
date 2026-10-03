"""Behavior coverage for sandbox Celery task boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from app.services.sandbox.models import SandboxJob, SandboxTaskStatus
from app.services.sandbox.policies import SandboxPolicyError
from app.tasks import sandbox as tasks


def sandbox_job() -> SandboxJob:
    return SandboxJob.model_validate(
        {
            "job_id": "job-255",
            "source": "debug",
            "command": ["python3", "-c", "print('ok')"],
        }
    )


def test_run_job_marks_invalid_payload_failed_without_retrying():
    payload = {"job_id": "job-invalid", "source": "debug"}
    store = SimpleNamespace(
        get_result=AsyncMock(return_value=None), update_status=AsyncMock()
    )

    with (
        patch.object(tasks, "sandbox_result_store", store),
        patch.object(tasks, "resolve_user_visible_error", return_value="safe error"),
    ):
        with pytest.raises(SandboxPolicyError):
            tasks.run_sandbox_job_task.run(payload)

    store.get_result.assert_awaited_once_with("job-invalid")
    store.update_status.assert_awaited_once()
    args, kwargs = store.update_status.await_args
    assert args == ("job-invalid", SandboxTaskStatus.FAILED)
    assert kwargs["error"] == "safe error"


def test_run_job_failure_records_storage_state_and_does_not_retry():
    payload = sandbox_job().model_dump(mode="json")
    execute = AsyncMock(side_effect=RuntimeError("broker unavailable"))
    store = SimpleNamespace(
        get_result=AsyncMock(return_value=None), update_status=AsyncMock()
    )

    with (
        patch.object(
            tasks, "SandboxManager", return_value=SimpleNamespace(execute=execute)
        ),
        patch.object(tasks, "sandbox_result_store", store),
        patch.object(tasks, "resolve_user_visible_error", return_value="safe error"),
    ):
        with pytest.raises(RuntimeError, match="broker unavailable"):
            tasks.run_sandbox_job_task.run(payload)

    assert execute.await_count == 1
    args, kwargs = store.update_status.await_args
    assert args == ("job-255", SandboxTaskStatus.FAILED)
    assert kwargs["metadata"].completed_at is not None
    assert kwargs["error"] == "safe error"
