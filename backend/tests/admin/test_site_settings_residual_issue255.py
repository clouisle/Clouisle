import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.v1.admin.endpoints import site_settings
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.site_setting import AutoNotificationConfigUpdate


class Query:
    def __init__(self, *, exists=False, count=0):
        self.exists_value = exists
        self.count_value = count

    async def exists(self):
        return self.exists_value

    async def count(self):
        return self.count_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "valid_value", "invalid_value"),
    [
        ("terms_url", "https://example.com/terms", "ftp://example.com/terms"),
        ("default_team_role", "admin", "owner"),
        ("upload_storage_backend", "S3", "azure"),
        ("object_storage_endpoint", "https://s3.example.com", 123),
        ("object_storage_secure", True, "true"),
        ("kb_document_max_upload_size_mb", 50, True),
        (
            "model_endpoint_allowlist",
            ["https://API.example.com/v1"],
            ["ftp://api.example.com"],
        ),
    ],
)
async def test_validate_setting_value_residual_admin_branches(
    monkeypatch, key, valid_value, invalid_value
):
    monkeypatch.setattr(
        site_settings.Team,
        "filter",
        lambda **_kwargs: Query(exists=True),
    )

    await site_settings._validate_setting_value(key, valid_value)
    with pytest.raises(BusinessError) as exc_info:
        await site_settings._validate_setting_value(key, invalid_value)
    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_endpoint_allowlist_validation_canonicalizes_in_place():
    value = [
        "https://API.example.com:443/v1",
        "https://api.example.com/models",
        "http://ollama:11434/api/tags",
    ]

    await site_settings._validate_setting_value("model_endpoint_allowlist", value)

    assert value == ["https://api.example.com", "http://ollama:11434"]


@pytest.mark.asyncio
async def test_validate_storage_update_requires_object_storage_credentials(monkeypatch):
    get_all = AsyncMock(
        return_value={"object_storage_endpoint": "https://s3.example.com"}
    )
    monkeypatch.setattr(site_settings.SiteSetting, "get_all_by_category", get_all)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings._validate_storage_settings_update(
            {"upload_storage_backend": "object"}
        )
    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR

    await site_settings._validate_storage_settings_update(
        {
            "upload_storage_backend": "s3",
            "object_storage_bucket": "bucket",
            "object_storage_access_key": "key",
            "object_storage_secret_key": "secret",
        }
    )
    get_all.assert_awaited()


@pytest.mark.asyncio
async def test_update_auto_notification_rejects_unknown_type_before_persist(
    monkeypatch,
):
    monkeypatch.setattr(
        site_settings.SiteSetting, "get_value", AsyncMock(return_value={})
    )
    set_value = AsyncMock()
    monkeypatch.setattr(site_settings.SiteSetting, "set_value", set_value)

    with pytest.raises(BusinessError) as exc_info:
        await site_settings.update_auto_notification_config(
            SimpleNamespace(),
            AutoNotificationConfigUpdate(channels=[], enabled_types=["missing"]),
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    set_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_archive_audit_logs_records_success_and_failure(monkeypatch):
    audit = AsyncMock()
    monkeypatch.setattr(site_settings.AuditLogService, "log", audit)
    monkeypatch.setattr(
        site_settings.archive_old_audit_logs,
        "delay",
        Mock(return_value=SimpleNamespace(id="task-1")),
    )

    response = await site_settings.trigger_archive_audit_logs(SimpleNamespace())

    assert response["data"] == {"task_id": "task-1", "status": "pending"}
    assert audit.await_args.kwargs["status"] == "pending"

    audit.reset_mock()
    monkeypatch.setattr(
        site_settings.archive_old_audit_logs,
        "delay",
        Mock(side_effect=RuntimeError("broker down")),
    )
    with pytest.raises(BusinessError) as exc_info:
        await site_settings.trigger_archive_audit_logs(SimpleNamespace())

    assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
    assert audit.await_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "extra_key", "message"),
    [
        ("PENDING", None, "Task is waiting to be executed"),
        ("STARTED", None, "Task is running"),
        ("SUCCESS", "result", "Task completed successfully"),
        ("FAILURE", "error", "Task failed"),
        ("RETRY", None, "Task state: RETRY"),
    ],
)
async def test_get_archive_task_status_maps_celery_states(
    monkeypatch, state, extra_key, message
):
    result_module = ModuleType("celery.result")

    class FakeAsyncResult:
        def __init__(self, task_id, app):
            self.task_id = task_id
            self.app = app
            self.state = state
            self.result = {"archived": 3}
            self.info = RuntimeError("boom")

    result_module.AsyncResult = FakeAsyncResult
    monkeypatch.setitem(sys.modules, "celery", ModuleType("celery"))
    monkeypatch.setitem(sys.modules, "celery.result", result_module)
    monkeypatch.setattr(
        site_settings.archive_old_audit_logs,
        "app",
        SimpleNamespace(main="tests"),
        raising=False,
    )

    response = await site_settings.get_archive_task_status("task-1")
    data = response["data"]

    assert data["status"] == state
    assert data["message"] == message
    if extra_key == "result":
        assert data["result"] == {"archived": 3}
    elif extra_key == "error":
        assert data["error"] == "boom"
