import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import audit_log


def test_get_event_loop_reuses_open_loop_and_replaces_unavailable_loops():
    open_loop = MagicMock()
    open_loop.is_closed.return_value = False
    with patch("asyncio.get_event_loop", return_value=open_loop):
        assert audit_log._get_event_loop() is open_loop

    for unavailable in (MagicMock(), RuntimeError("no loop")):
        new_loop = MagicMock()
        if isinstance(unavailable, MagicMock):
            unavailable.is_closed.return_value = True
            get_loop = patch("asyncio.get_event_loop", return_value=unavailable)
        else:
            get_loop = patch("asyncio.get_event_loop", side_effect=unavailable)
        with (
            get_loop,
            patch("asyncio.new_event_loop", return_value=new_loop),
            patch("asyncio.set_event_loop") as set_loop,
        ):
            assert audit_log._get_event_loop() is new_loop
        set_loop.assert_called_once_with(new_loop)


def test_archive_task_runs_coroutine_and_propagates_failure():
    loop = MagicMock()
    loop.run_until_complete.return_value = {"status": "success"}
    with (
        patch.object(audit_log, "_get_event_loop", return_value=loop),
        patch.object(audit_log, "_archive_old_audit_logs") as archive,
    ):
        assert audit_log.archive_old_audit_logs.run() == {"status": "success"}
    archive.assert_called_once_with()
    loop.run_until_complete.call_args.args[0].close()

    def fail(coroutine):
        coroutine.close()
        raise RuntimeError("boom")

    loop.run_until_complete.side_effect = fail
    with (
        patch.object(audit_log, "_get_event_loop", return_value=loop),
        patch.object(audit_log, "_archive_old_audit_logs"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        audit_log.archive_old_audit_logs.run()


@pytest.mark.asyncio
async def test_archive_returns_without_writing_when_no_logs():
    now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    query = MagicMock(all=AsyncMock(return_value=[]))
    with (
        patch.object(
            audit_log.SiteSetting, "get_value", new=AsyncMock(return_value=30)
        ),
        patch.object(audit_log.AuditLog, "filter", return_value=query) as filter_logs,
        patch.object(audit_log, "now_utc", return_value=now),
    ):
        result = await audit_log._archive_old_audit_logs()

    cutoff = now - timedelta(days=30)
    assert result == {
        "status": "success",
        "archived_count": 0,
        "retention_days": 30,
        "cutoff_date": cutoff.isoformat(),
    }
    filter_logs.assert_called_once_with(created_at__lt=cutoff)


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [None, [{"id": "existing"}], "invalid json"])
async def test_archive_groups_merges_and_recovers_corrupt_files(tmp_path, existing):
    january = MagicMock(created_at=datetime(2025, 1, 2, tzinfo=timezone.utc))
    january.to_dict.return_value = {"id": "jan"}
    january_second = MagicMock(created_at=datetime(2025, 1, 3, tzinfo=timezone.utc))
    january_second.to_dict.return_value = {"id": "jan-2"}
    february = MagicMock(created_at=datetime(2025, 2, 3, tzinfo=timezone.utc))
    february.to_dict.return_value = {"id": "feb"}
    january_file = tmp_path / "audit_logs_202501.json"
    if existing == "invalid json":
        january_file.write_text(existing)
    elif existing is not None:
        january_file.write_text(json.dumps(existing))

    select_query = MagicMock(
        all=AsyncMock(return_value=[january, january_second, february])
    )
    delete_query = MagicMock(delete=AsyncMock())
    with (
        patch.object(
            audit_log.SiteSetting,
            "get_value",
            new=AsyncMock(side_effect=[365, str(tmp_path)]),
        ),
        patch.object(
            audit_log.AuditLog,
            "filter",
            side_effect=[select_query, delete_query],
        ),
    ):
        result = await audit_log._archive_old_audit_logs()

    expected_january = ([] if existing in (None, "invalid json") else existing) + [
        {"id": "jan"},
        {"id": "jan-2"},
    ]
    assert json.loads(january_file.read_text()) == expected_january
    assert json.loads((tmp_path / "audit_logs_202502.json").read_text()) == [
        {"id": "feb"}
    ]
    assert result["status"] == "success"
    assert result["archived_count"] == 3
    delete_query.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_archive_and_create_tasks_convert_boundary_failures():
    with patch.object(
        audit_log.SiteSetting,
        "get_value",
        new=AsyncMock(side_effect=RuntimeError("database unavailable")),
    ):
        assert await audit_log._archive_old_audit_logs() == {
            "status": "failed",
            "error": "database unavailable",
        }

    create = AsyncMock(side_effect=[None, RuntimeError("insert failed")])
    with patch.object(audit_log.AuditLog, "create", new=create):
        assert await audit_log.create_audit_log_task.run({"action": "login"}) == {
            "status": "success"
        }
        assert await audit_log.create_audit_log_task.run({"action": "logout"}) == {
            "status": "failed",
            "error": "insert failed",
        }
    assert create.await_args_list[0].kwargs == {"action": "login"}
