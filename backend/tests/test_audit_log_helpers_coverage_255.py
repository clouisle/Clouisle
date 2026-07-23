import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import Request

from app.core.audit import audit_log
from app.models.audit_log import AuditLog
from app.tasks import audit_log as audit_tasks


class _ArchiveQuery:
    def __init__(self, logs):
        self.logs = logs
        self.filters = []
        self.delete = AsyncMock(return_value=len(logs))

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    async def all(self):
        return self.logs


def test_audit_log_to_dict_serializes_identifiers_and_timestamps():
    user_id = uuid4()
    resource_id = uuid4()
    log = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        username="auditor",
        team_id=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
        action="update_setting",
        resource_type="setting",
        resource_id=resource_id,
        resource_name="retention",
        operation="update",
        status="success",
        error_message=None,
        changes={"after": {"enabled": True}},
        metadata={"source": "test"},
        auth_method="jwt",
        api_key_id=None,
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
    )

    data = AuditLog.to_dict(log)

    assert data["id"] == str(log.id)
    assert data["user_id"] == str(user_id)
    assert data["resource_id"] == str(resource_id)
    assert data["team_id"] is None
    assert data["created_at"] == "2026-01-02T03:04:00+00:00"
    assert data["changes"] == {"after": {"enabled": True}}


@pytest.mark.anyio
async def test_archive_groups_old_events_and_replaces_invalid_existing_archive(
    tmp_path,
):
    january_log = SimpleNamespace(
        created_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        to_dict=lambda: {"id": "jan"},
    )
    february_log = SimpleNamespace(
        created_at=datetime(2025, 2, 4, tzinfo=timezone.utc),
        to_dict=lambda: {"id": "feb"},
    )
    query = _ArchiveQuery([january_log, february_log])
    (tmp_path / "audit_logs_202501.json").write_text("not json", encoding="utf-8")

    with (
        patch.object(
            audit_tasks.SiteSetting,
            "get_value",
            new=AsyncMock(side_effect=[30, str(tmp_path)]),
        ),
        patch.object(audit_tasks.AuditLog, "filter", return_value=query) as filter_logs,
        patch.object(
            audit_tasks,
            "now_utc",
            return_value=datetime(2025, 3, 1, tzinfo=timezone.utc),
        ),
    ):
        result = await audit_tasks._archive_old_audit_logs()

    assert result["status"] == "success"
    assert result["archived_count"] == 2
    filter_logs.assert_called_with(
        created_at__lt=datetime(2025, 1, 30, tzinfo=timezone.utc)
    )
    query.delete.assert_awaited_once()
    assert json.loads((tmp_path / "audit_logs_202501.json").read_text()) == [
        {"id": "jan"}
    ]
    assert json.loads((tmp_path / "audit_logs_202502.json").read_text()) == [
        {"id": "feb"}
    ]


@pytest.mark.anyio
async def test_archive_failure_is_reported_without_deleting_persistence_records(
    tmp_path,
):
    log = SimpleNamespace(
        created_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        to_dict=lambda: {"id": "old"},
    )
    query = _ArchiveQuery([log])

    with (
        patch.object(
            audit_tasks.SiteSetting,
            "get_value",
            new=AsyncMock(side_effect=[30, str(tmp_path)]),
        ),
        patch.object(audit_tasks.AuditLog, "filter", return_value=query),
        patch.object(
            audit_tasks,
            "now_utc",
            return_value=datetime(2025, 3, 1, tzinfo=timezone.utc),
        ),
        patch("builtins.open", side_effect=OSError("disk full")),
    ):
        result = await audit_tasks._archive_old_audit_logs()

    assert result == {"status": "failed", "error": "disk full"}
    query.delete.assert_not_awaited()


@pytest.mark.anyio
async def test_async_audit_event_persistence_failure_returns_failed_status():
    with patch.object(
        audit_tasks.AuditLog,
        "create",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        result = await audit_tasks.create_audit_log_task({"action": "login_failed"})

    assert result == {"status": "failed", "error": "db down"}


@pytest.mark.anyio
async def test_audit_decorator_preserves_primary_failure_when_event_persistence_fails():
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 80)})

    @audit_log("delete_record", "record", "delete")
    async def delete_record(request):
        raise ValueError("primary failure")

    with patch(
        "app.core.audit.AuditLogService.log",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ) as log_event:
        with pytest.raises(ValueError, match="primary failure"):
            await delete_record(request=request)

    assert log_event.await_args.kwargs["status"] == "failed"
    assert log_event.await_args.kwargs["error_message"] == "primary failure"
