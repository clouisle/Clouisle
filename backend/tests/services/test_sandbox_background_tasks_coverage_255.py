"""Behavior coverage for sandbox Celery task boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.sandbox.gateway import SandboxGateway
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


@pytest.mark.anyio
async def test_submit_queues_valid_job_after_persisting_queued_result():
    job = sandbox_job()
    queued = AsyncMock()
    dispatch = MagicMock()

    with (
        patch(
            "app.services.sandbox.gateway.sandbox_policy_engine.validate"
        ) as validate,
        patch(
            "app.services.sandbox.gateway.sandbox_result_store.create_queued_result",
            new=queued,
        ),
        patch.object(tasks.run_sandbox_job_task, "delay", dispatch),
    ):
        result = await SandboxGateway().submit(job)

    assert result == job.job_id
    validate.assert_called_once_with(job)
    queued.assert_awaited_once()
    assert queued.await_args.args[0] == job.job_id
    dispatch.assert_called_once_with(job.model_dump(mode="json"))


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


def test_cleanup_task_returns_cleaned_count_from_gateway():
    cleanup = AsyncMock(return_value=2)

    with patch.object(tasks.sandbox_gateway, "cleanup_expired_sessions", cleanup):
        result = tasks.cleanup_expired_sandbox_sessions_task.run()

    assert result == {"cleaned": 2}
    cleanup.assert_awaited_once()
