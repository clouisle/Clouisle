import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import audit_log as audit_log_task


@pytest.mark.asyncio
async def test_archive_old_audit_logs_writes_monthly_archive_and_deletes_logs(tmp_path):
    archived_log = SimpleNamespace(
        created_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        to_dict=MagicMock(return_value={"id": "old-log"}),
    )
    selected_logs = MagicMock()
    selected_logs.all = AsyncMock(return_value=[archived_log])
    deleted_logs = MagicMock()
    deleted_logs.delete = AsyncMock()

    with (
        patch(
            "app.tasks.audit_log.SiteSetting.get_value",
            new=AsyncMock(side_effect=[30, str(tmp_path)]),
        ),
        patch(
            "app.tasks.audit_log.now_utc",
            return_value=datetime(2025, 2, 15, tzinfo=timezone.utc),
        ),
        patch(
            "app.tasks.audit_log.AuditLog.filter",
            side_effect=[selected_logs, deleted_logs],
        ) as mock_filter,
    ):
        result = await audit_log_task._archive_old_audit_logs()

    archive_file = tmp_path / "audit_logs_202501.json"
    assert json.loads(archive_file.read_text()) == [{"id": "old-log"}]
    assert result["status"] == "success"
    assert result["archived_count"] == 1
    assert result["retention_days"] == 30
    archived_log.to_dict.assert_called_once_with()
    assert mock_filter.call_count == 2
    deleted_logs.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_archive_old_audit_logs_is_noop_when_no_logs_are_expired():
    selected_logs = MagicMock()
    selected_logs.all = AsyncMock(return_value=[])

    with (
        patch(
            "app.tasks.audit_log.SiteSetting.get_value",
            new=AsyncMock(return_value=365),
        ),
        patch(
            "app.tasks.audit_log.AuditLog.filter", return_value=selected_logs
        ) as mock_filter,
    ):
        result = await audit_log_task._archive_old_audit_logs()

    assert result["status"] == "success"
    assert result["archived_count"] == 0
    assert result["retention_days"] == 365
    mock_filter.assert_called_once()


@pytest.mark.asyncio
async def test_archive_old_audit_logs_returns_failure_when_archive_write_fails(
    tmp_path,
):
    archived_log = SimpleNamespace(
        created_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        to_dict=MagicMock(return_value={"id": "old-log"}),
    )
    selected_logs = MagicMock()
    selected_logs.all = AsyncMock(return_value=[archived_log])

    with (
        patch(
            "app.tasks.audit_log.SiteSetting.get_value",
            new=AsyncMock(side_effect=[30, str(tmp_path)]),
        ),
        patch("app.tasks.audit_log.AuditLog.filter", return_value=selected_logs),
        patch("app.tasks.audit_log.json.dump", side_effect=OSError("disk full")),
    ):
        result = await audit_log_task._archive_old_audit_logs()

    assert result == {"status": "failed", "error": "disk full"}
