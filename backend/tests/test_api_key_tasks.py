import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.notification import AutoNotificationType, NotificationLevel
from app.tasks import api_key


class Query:
    def __init__(self, rows):
        self.rows = rows

    def prefetch_related(self, *args):
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def make_key(*, expires_at, locale="en"):
    return SimpleNamespace(
        id=uuid4(),
        name="Deploy key",
        key_prefix="ck_test",
        expires_at=expires_at,
        user=SimpleNamespace(id=uuid4(), locale=locale),
    )


def test_check_api_key_expiration_sends_due_notifications_and_skips_other_days(
    monkeypatch,
):
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    expiring_due = make_key(expires_at=now + timedelta(days=3), locale="zh")
    expiring_skipped = make_key(expires_at=now + timedelta(days=2))
    expired = make_key(expires_at=now - timedelta(hours=2))
    queries = [Query([expiring_due, expiring_skipped]), Query([expired])]
    sent = []

    def fake_filter(**kwargs):
        sent.append({"filter": kwargs})
        return queries.pop(0)

    async def fake_send_to_user(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(api_key, "now_utc", lambda: now)
    monkeypatch.setattr(api_key.APIKey, "filter", fake_filter)
    monkeypatch.setattr(
        api_key.AutoNotificationService, "send_to_user", fake_send_to_user
    )
    monkeypatch.setattr(api_key, "t", lambda key, **kwargs: key)

    asyncio.run(api_key._check_api_key_expiration())

    notifications = [item for item in sent if "notification_type" in item]
    assert [item["notification_type"] for item in notifications] == [
        AutoNotificationType.APIKEY_EXPIRING,
        AutoNotificationType.APIKEY_EXPIRED,
    ]
    assert notifications[0]["user_id"] == expiring_due.user.id
    assert notifications[0]["level"] == NotificationLevel.HIGH
    assert notifications[0]["data"]["days_remaining"] == 3
    assert notifications[1]["user_id"] == expired.user.id
    assert notifications[1]["data"]["expired_at"] == expired.expires_at.isoformat()
