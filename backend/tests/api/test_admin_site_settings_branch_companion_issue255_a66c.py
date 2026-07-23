from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import site_settings
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, *, count=0):
        self.count_value = count

    async def count(self):
        return self.count_value


@pytest.mark.anyio
async def test_superadmin_sso_guard_accepts_bound_and_rejects_unbound():
    with patch.object(
        site_settings.UserSSOConnection,
        "filter",
        side_effect=[_Query(count=1), _Query(count=0)],
    ):
        await site_settings._ensure_superadmin_sso_bound()
        with pytest.raises(BusinessError) as exc:
            await site_settings._ensure_superadmin_sso_bound()

    assert exc.value.code == ResponseCode.FORBIDDEN


@pytest.mark.anyio
async def test_storage_validation_skips_non_storage_and_local_updates():
    get_settings = AsyncMock(return_value={"upload_storage_backend": "local"})
    with patch.object(site_settings.SiteSetting, "get_all_by_category", get_settings):
        await site_settings._validate_storage_settings_update({"site_name": "Test"})
        get_settings.assert_not_awaited()

        await site_settings._validate_storage_settings_update(
            {"object_storage_bucket": "unused"}
        )
        get_settings.assert_awaited_once_with(category="storage")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("PENDING", {"message": "Task is waiting to be executed"}),
        ("STARTED", {"message": "Task is running"}),
        (
            "SUCCESS",
            {"result": {"archived": 4}, "message": "Task completed successfully"},
        ),
        ("FAILURE", {"error": "worker failed", "message": "Task failed"}),
        ("RETRY", {"message": "Task state: RETRY"}),
    ],
)
async def test_archive_task_status_serializes_each_state(state, expected):
    task = SimpleNamespace(
        state=state,
        result={"archived": 4},
        info=RuntimeError("worker failed"),
    )
    with patch("celery.result.AsyncResult", return_value=task) as async_result:
        response = await site_settings.get_archive_task_status(
            "task-branch", current_user=SimpleNamespace(id=uuid4())
        )

    async_result.assert_called_once_with(
        "task-branch", app=site_settings.archive_old_audit_logs.app
    )
    assert response["data"] == {
        "task_id": "task-branch",
        "status": state,
        **expected,
    }


@pytest.mark.anyio
async def test_archive_dispatch_failure_audits_before_business_error():
    audit = AsyncMock()
    with (
        patch.object(
            site_settings.archive_old_audit_logs,
            "delay",
            MagicMock(side_effect=RuntimeError("broker down")),
        ),
        patch.object(site_settings.AuditLogService, "log", audit),
        pytest.raises(BusinessError) as exc,
    ):
        await site_settings.trigger_archive_audit_logs(
            MagicMock(), current_user=SimpleNamespace(id=uuid4())
        )

    assert exc.value.code == ResponseCode.INTERNAL_ERROR
    assert audit.await_args.kwargs["status"] == "failed"
