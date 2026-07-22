from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.models.notification import AutoNotificationType
from app.tasks import api_key as tasks


@pytest.mark.asyncio
async def test_expiration_check_sends_due_reminders_and_skips_other_days(monkeypatch):
    now = datetime(2026, 7, 22, 12, tzinfo=UTC)
    user = SimpleNamespace(id=uuid4(), locale="zh")

    def key(name, expires_at, *, owner=user):
        return SimpleNamespace(
            id=uuid4(),
            name=name,
            key_prefix=f"clou_{name}",
            expires_at=expires_at,
            user=owner,
        )

    expiring = [
        key("today", now + timedelta(hours=12)),
        key("later", now + timedelta(days=2)),
    ]
    expired = [
        key("expired", now - timedelta(hours=1), owner=SimpleNamespace(id=uuid4()))
    ]
    queries = []
    for result in (expiring, expired):
        query = MagicMock()
        query.prefetch_related = AsyncMock(return_value=result)
        queries.append(query)

    send = AsyncMock()
    translate = MagicMock(side_effect=lambda message, **_: message)
    monkeypatch.setattr(tasks, "now_utc", lambda: now)
    monkeypatch.setattr(tasks.APIKey, "filter", MagicMock(side_effect=queries))
    monkeypatch.setattr(tasks.AutoNotificationService, "send_to_user", send)
    monkeypatch.setattr(tasks, "t", translate)

    await tasks._check_api_key_expiration()

    assert [item.kwargs["notification_type"] for item in send.await_args_list] == [
        AutoNotificationType.APIKEY_EXPIRING,
        AutoNotificationType.APIKEY_EXPIRED,
    ]
    assert send.await_args_list[0].kwargs["data"]["days_remaining"] == 1
    assert translate.call_args_list == [
        call("notify_apikey_expiring_title", lang="zh"),
        call(
            "notify_apikey_expiring_content",
            lang="zh",
            key_name="today",
            key_prefix="clou_today",
            days=1,
        ),
        call("notify_apikey_expired_title", lang="en"),
        call(
            "notify_apikey_expired_content",
            lang="en",
            key_name="expired",
            key_prefix="clou_expired",
        ),
    ]
