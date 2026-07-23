from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.tasks import api_key as api_key_tasks


class Query:
    def __init__(self, rows):
        self.rows = rows

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def make_key(now, *, days=None, hours=None, locale="en"):
    return SimpleNamespace(
        id=uuid4(),
        name="automation",
        key_prefix="clou_test",
        expires_at=now + timedelta(days=days or 0, hours=hours or 0),
        user=SimpleNamespace(id=uuid4(), locale=locale),
    )


@pytest.mark.asyncio
async def test_expiration_check_notifies_due_and_expired_keys(monkeypatch):
    now = datetime(2026, 7, 20, 12, 0, tzinfo=api_key_tasks.now_utc().tzinfo)
    seven_days = make_key(now, days=7, locale="zh")
    under_one_day = make_key(now, hours=12)
    skipped = make_key(now, days=5)
    expired = make_key(now, hours=-1)
    queries = iter([Query([seven_days, under_one_day, skipped]), Query([expired])])
    notify = AsyncMock()

    monkeypatch.setattr(api_key_tasks, "now_utc", lambda: now)
    monkeypatch.setattr(
        api_key_tasks.APIKey,
        "filter",
        MagicMock(side_effect=lambda **_kwargs: next(queries)),
    )
    monkeypatch.setattr(api_key_tasks.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(api_key_tasks, "t", lambda key, **_kwargs: key)

    await api_key_tasks._check_api_key_expiration()

    assert notify.await_count == 3
    assert [
        call.kwargs["data"].get("days_remaining") for call in notify.await_args_list
    ] == [
        7,
        1,
        None,
    ]
    assert notify.await_args_list[0].kwargs["title"] == "notify_apikey_expiring_title"
    assert notify.await_args_list[2].kwargs["title"] == "notify_apikey_expired_title"


def test_task_runs_async_check_and_propagates_errors(monkeypatch):
    loop = MagicMock()
    loop.run_until_complete.side_effect = RuntimeError("database unavailable")
    coroutine = AsyncMock()()
    coroutine.close()

    monkeypatch.setattr(api_key_tasks, "_get_event_loop", lambda: loop)
    monkeypatch.setattr(api_key_tasks, "_check_api_key_expiration", lambda: coroutine)

    with pytest.raises(RuntimeError, match="database unavailable"):
        api_key_tasks.check_api_key_expiration_task.run()


def test_get_event_loop_reuses_open_loop(monkeypatch):
    loop = MagicMock()
    loop.is_closed.return_value = False
    monkeypatch.setattr("asyncio.get_event_loop", lambda: loop)

    assert api_key_tasks._get_event_loop() is loop


def test_get_event_loop_replaces_closed_loop_and_runtime_failure(monkeypatch):
    closed_loop = MagicMock()
    closed_loop.is_closed.return_value = True
    replacement = MagicMock()
    set_loop = MagicMock()
    monkeypatch.setattr("asyncio.get_event_loop", lambda: closed_loop)
    monkeypatch.setattr("asyncio.new_event_loop", lambda: replacement)
    monkeypatch.setattr("asyncio.set_event_loop", set_loop)

    assert api_key_tasks._get_event_loop() is replacement
    set_loop.assert_called_once_with(replacement)

    monkeypatch.setattr(
        "asyncio.get_event_loop", MagicMock(side_effect=RuntimeError("no loop"))
    )
    assert api_key_tasks._get_event_loop() is replacement
