from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.v1.endpoints import notifications
from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationScope,
    NotificationSource,
)
from app.schemas.notification import NotificationAdminCreate
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, result=None, values=None):
        self.result = result
        self.values = values or []
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    async def first(self):
        return self.result

    async def values_list(self, *args, **kwargs):
        return self.values


@pytest.mark.parametrize(
    ("message", "status", "expected"),
    [
        (None, NotificationDeliveryStatus.FAILED, None),
        ("raw success", NotificationDeliveryStatus.SUCCESS, "raw success"),
        ("raw failure", NotificationDeliveryStatus.FAILED, "translated:unknown_error"),
        ("known.key", NotificationDeliveryStatus.FAILED, "translated:known.key"),
    ],
)
def test_serialize_delivery_error_issue255_branches(
    monkeypatch, message, status, expected
):
    monkeypatch.setattr(
        notifications, "has_translation", lambda key: key == "known.key"
    )
    monkeypatch.setattr(notifications, "t", lambda key: f"translated:{key}")

    assert notifications.serialize_delivery_error(message, status) == expected


@pytest.mark.asyncio
async def test_check_team_admin_permission_issue255_rejects_missing_team(monkeypatch):
    monkeypatch.setattr(notifications.Team, "filter", lambda **kwargs: _Query())

    with pytest.raises(BusinessError) as exc_info:
        await notifications.check_team_admin_permission(
            uuid4(), SimpleNamespace(is_superuser=False)
        )

    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND


@pytest.mark.asyncio
async def test_check_team_admin_permission_issue255_rejects_non_admin_member(
    monkeypatch,
):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(notifications.Team, "filter", lambda **kwargs: _Query(team))
    monkeypatch.setattr(notifications.TeamMember, "filter", lambda **kwargs: _Query())

    with pytest.raises(BusinessError) as exc_info:
        await notifications.check_team_admin_permission(
            team.id, SimpleNamespace(is_superuser=False)
        )

    assert exc_info.value.code == ResponseCode.TEAM_ADMIN_REQUIRED


@pytest.mark.asyncio
async def test_admin_list_notifications_issue255_non_superuser_cannot_query_global():
    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_list_notifications(
            scope=[NotificationScope.GLOBAL],
            current_user=SimpleNamespace(is_superuser=False),
        )

    assert exc_info.value.code == ResponseCode.INSUFFICIENT_PRIVILEGES


@pytest.mark.asyncio
async def test_admin_create_notification_issue255_email_requires_enabled_smtp(
    monkeypatch,
):
    payload = NotificationAdminCreate(
        scope=NotificationScope.GLOBAL,
        type="maintenance",
        source=NotificationSource.SYSTEM,
        title="Maintenance",
        content="Soon",
        notify_channels=[NotificationChannel.EMAIL],
    )

    async def disabled_smtp_config():
        return {
            "enabled": False,
            "host": "smtp.example.com",
            "from_address": "noreply@example.com",
        }

    monkeypatch.setattr("app.core.email.get_smtp_config", disabled_smtp_config)

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_create_notification(
            payload,
            current_user=SimpleNamespace(is_superuser=True),
        )

    assert exc_info.value.msg_key == "smtp_not_enabled"


@pytest.mark.asyncio
async def test_admin_delete_notification_issue255_team_scope_requires_team_id(
    monkeypatch,
):
    notification = SimpleNamespace(
        id=uuid4(),
        scope=NotificationScope.TEAM,
        team_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        notifications.Notification, "filter", lambda **kwargs: _Query(notification)
    )

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_delete_notification(
            notification.id,
            current_user=SimpleNamespace(is_superuser=True),
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "notification_scope_requires_team"
