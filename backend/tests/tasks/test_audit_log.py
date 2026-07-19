from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.audit_log import (
    _archive_old_audit_logs,
    _get_event_loop,
    archive_old_audit_logs,
    create_audit_log_task,
)


def test_get_event_loop_reuses_open_loop():
    loop = MagicMock()
    loop.is_closed.return_value = False

    with patch("asyncio.get_event_loop", return_value=loop):
        assert _get_event_loop() is loop


def test_get_event_loop_replaces_closed_loop():
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", return_value=closed_loop),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_get_event_loop_creates_loop_when_none_exists():
    new_loop = MagicMock()

    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=new_loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert _get_event_loop() is new_loop

    set_event_loop.assert_called_once_with(new_loop)


def test_archive_old_audit_logs_runs_coroutine():
    loop = MagicMock()
    expected = {"status": "success", "archived_count": 0}
    loop.run_until_complete.return_value = expected

    with (
        patch("app.tasks.audit_log._get_event_loop", return_value=loop),
        patch("app.tasks.audit_log._archive_old_audit_logs") as archive,
    ):
        result = archive_old_audit_logs.run()

    assert result == expected
    archive.assert_called_once_with()
    coroutine = loop.run_until_complete.call_args.args[0]
    coroutine.close()


def test_archive_old_audit_logs_propagates_failure():
    loop = MagicMock()

    def fail(coroutine):
        coroutine.close()
        raise RuntimeError("boom")

    loop.run_until_complete.side_effect = fail

    with (
        patch("app.tasks.audit_log._get_event_loop", return_value=loop),
        patch("app.tasks.audit_log._archive_old_audit_logs"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        archive_old_audit_logs.run()


@pytest.mark.asyncio
async def test_archive_old_audit_logs_returns_empty_result():
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    query = MagicMock()
    query.all = AsyncMock(return_value=[])

    with (
        patch(
            "app.tasks.audit_log.SiteSetting.get_value",
            new=AsyncMock(return_value=30),
        ),
        patch("app.tasks.audit_log.AuditLog.filter", return_value=query),
        patch("app.tasks.audit_log.now_utc", return_value=cutoff),
    ):
        result = await _archive_old_audit_logs()

    assert result == {
        "status": "success",
        "archived_count": 0,
        "retention_days": 30,
        "cutoff_date": (cutoff - timedelta(days=30)).isoformat(),
    }


@pytest.mark.asyncio
async def test_archive_old_audit_logs_archives_and_deletes(tmp_path):
    created_at = datetime(2025, 12, 5, tzinfo=timezone.utc)
    log = MagicMock(created_at=created_at)
    log.to_dict.return_value = {"id": "audit-1"}
    select_query = MagicMock()
    select_query.all = AsyncMock(return_value=[log])
    delete_query = MagicMock()
    delete_query.delete = AsyncMock()

    with (
        patch(
            "app.tasks.audit_log.SiteSetting.get_value",
            new=AsyncMock(side_effect=[365, str(tmp_path)]),
        ),
        patch(
            "app.tasks.audit_log.AuditLog.filter",
            side_effect=[select_query, delete_query],
        ),
    ):
        result = await _archive_old_audit_logs()

    assert result["status"] == "success"
    assert result["archived_count"] == 1
    assert (
        tmp_path / "audit_logs_202512.json"
    ).read_text() == '[\n  {\n    "id": "audit-1"\n  }\n]'
    delete_query.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_archive_old_audit_logs_converts_failure():
    with patch(
        "app.tasks.audit_log.SiteSetting.get_value",
        new=AsyncMock(side_effect=RuntimeError("database unavailable")),
    ):
        result = await _archive_old_audit_logs()

    assert result == {"status": "failed", "error": "database unavailable"}


@pytest.mark.asyncio
async def test_create_audit_log_task_returns_success():
    with patch("app.tasks.audit_log.AuditLog.create", new=AsyncMock()) as create:
        result = await create_audit_log_task.run({"action": "login"})

    assert result == {"status": "success"}
    create.assert_awaited_once_with(action="login")


@pytest.mark.asyncio
async def test_create_audit_log_task_converts_failure():
    with patch(
        "app.tasks.audit_log.AuditLog.create",
        new=AsyncMock(side_effect=RuntimeError("insert failed")),
    ):
        result = await create_audit_log_task.run({"action": "login"})

    assert result == {"status": "failed", "error": "insert failed"}
