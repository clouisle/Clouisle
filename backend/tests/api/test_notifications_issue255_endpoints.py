from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import notifications
from app.models.notification import (
    NotificationAudit,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import NotificationAdminCreate, NotificationReadRequest
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, *, rows=None, count=0, values=None):
        self.rows = rows or []
        self.total = count
        self.values = values or []

    def filter(self, *args, **kwargs):
        return self

    def exclude(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        return self

    def limit(self, value):
        return self

    async def count(self):
        return self.total

    async def values_list(self, *args, **kwargs):
        return self.values

    async def first(self):
        return self.rows[0] if self.rows else None

    async def all(self):
        return self.rows

    async def delete(self):
        return 1

    def __await__(self):
        async def result():
            return self.rows

        return result().__await__()


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def notification(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "scope": NotificationScope.GLOBAL,
        "team_id": None,
        "user_id": None,
        "type": "system.test",
        "source": NotificationSource.SYSTEM,
        "title": "Test",
        "content": "Notification",
        "level": NotificationLevel.MEDIUM,
        "data": None,
        "link_url": None,
        "status": NotificationStatus.ACTIVE,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_list_notifications_applies_filters_and_read_state(monkeypatch):
    current_user = user()
    item = notification()
    read_at = datetime.now(UTC)
    query = Query(rows=[item], count=1)
    monkeypatch.setattr(
        notifications, "build_visible_query", AsyncMock(return_value=query)
    )
    monkeypatch.setattr(
        notifications.NotificationRead,
        "filter",
        MagicMock(
            side_effect=[
                Query(values=[uuid4()]),
                Query(rows=[SimpleNamespace(notification_id=item.id, read_at=read_at)]),
            ]
        ),
    )

    response = await notifications.list_notifications(
        scope=NotificationScope.GLOBAL,
        type="system.test",
        level="medium",
        search="Test",
        unread_only=True,
        created_from="2026-01-01",
        created_to="2026-12-31",
        page=2,
        page_size=10,
        current_user=current_user,
    )

    assert response["data"]["total"] == 1
    assert response["data"]["items"][0].is_read is True
    assert response["data"]["items"][0].read_at == read_at


@pytest.mark.anyio
async def test_mark_read_bulk_creates_only_new_rows_and_audits(monkeypatch):
    current_user = user()
    existing_id, new_id = uuid4(), uuid4()
    visible = Query(values=[existing_id, new_id])
    read_bulk = AsyncMock()
    audit_bulk = AsyncMock()
    monkeypatch.setattr(
        notifications, "build_visible_query", AsyncMock(return_value=visible)
    )
    monkeypatch.setattr(
        notifications.NotificationRead,
        "filter",
        MagicMock(return_value=Query(values=[existing_id])),
    )
    monkeypatch.setattr(notifications.NotificationRead, "bulk_create", read_bulk)
    monkeypatch.setattr(NotificationAudit, "bulk_create", audit_bulk)

    response = await notifications.mark_read(
        NotificationReadRequest(notification_ids=[existing_id, new_id]), current_user
    )

    assert response["data"] == {"updated": 1}
    assert len(read_bulk.await_args.args[0]) == 1
    assert len(audit_bulk.await_args.args[0]) == 1
    assert (
        audit_bulk.await_args.args[0][0].action
        == notifications.NotificationAuditAction.READ
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scope", "superuser", "expected_code"),
    [
        (NotificationScope.GLOBAL, False, ResponseCode.INSUFFICIENT_PRIVILEGES),
        (NotificationScope.TEAM, True, ResponseCode.BAD_REQUEST),
        (NotificationScope.USER, False, ResponseCode.INSUFFICIENT_PRIVILEGES),
    ],
)
async def test_admin_delete_enforces_scope_authorization(
    monkeypatch, scope, superuser, expected_code
):
    item = notification(scope=scope)
    monkeypatch.setattr(
        notifications.Notification, "filter", MagicMock(return_value=Query(rows=[item]))
    )
    audit = AsyncMock()
    monkeypatch.setattr(notifications, "create_notification_audit", audit)

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_delete_notification(
            item.id, user(superuser=superuser)
        )

    assert exc_info.value.code == expected_code
    audit.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_create_batch_user_notifications(monkeypatch):
    current_user = user()
    user_ids = [uuid4(), uuid4()]
    created = [
        notification(scope=NotificationScope.USER, user_id=value) for value in user_ids
    ]
    monkeypatch.setattr(
        notifications.User,
        "filter",
        MagicMock(
            return_value=Query(rows=[SimpleNamespace(id=value) for value in user_ids])
        ),
    )
    create = AsyncMock(side_effect=created)
    publish = AsyncMock()
    monkeypatch.setattr(notifications.Notification, "create", create)
    monkeypatch.setattr(notifications, "create_notification", publish)

    response = await notifications.admin_create_notification(
        NotificationAdminCreate(
            scope=NotificationScope.USER,
            user_ids=user_ids,
            type="system.test",
            title="Test",
            content="Notification",
        ),
        current_user,
    )

    assert response["data"].id == created[0].id
    assert create.await_count == 2
    assert publish.await_count == 2


CHANNEL_CASES = [
    (
        NotificationChannel.EMAIL,
        "app.core.email",
        "get_smtp_config",
        {"enabled": True, "host": "smtp", "from_address": "from@example.com"},
        "send_notification_email_task",
    ),
    (
        NotificationChannel.DINGTALK,
        "app.core.dingtalk",
        "get_dingtalk_config",
        {
            "enabled": True,
            "notification_type": "webhook",
            "webhook_url": "https://example.com",
        },
        "send_notification_dingtalk_task",
    ),
    (
        NotificationChannel.WECHAT,
        "app.core.wechat",
        "get_wechat_config",
        {
            "enabled": True,
            "notification_type": "app",
            "corp_id": "corp",
            "secret": "secret",
            "agent_id": "agent",
        },
        "send_notification_wechat_task",
    ),
    (
        NotificationChannel.FEISHU,
        "app.core.feishu",
        "get_feishu_config",
        {
            "enabled": True,
            "notification_type": "app",
            "app_id": "app",
            "app_secret": "secret",
        },
        "send_notification_feishu_task",
    ),
    (
        NotificationChannel.WEBHOOK,
        "app.core.webhook",
        "get_webhook_config",
        {"enabled": True, "url": "https://example.com"},
        "send_notification_webhook_task",
    ),
    (
        NotificationChannel.SLACK,
        "app.core.slack",
        "get_slack_config",
        {"enabled": True, "webhook_url": "https://example.com"},
        "send_notification_slack_task",
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("channel", "config_module", "config_getter", "config", "task_name"),
    CHANNEL_CASES,
)
async def test_admin_create_dispatches_configured_channel(
    monkeypatch, channel, config_module, config_getter, config, task_name
):
    created = notification()
    delivery = SimpleNamespace(
        channel=channel,
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=0,
        sent_at=None,
        created_at=created.created_at,
        updated_at=created.updated_at,
        task_id=None,
        save=AsyncMock(),
    )
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="task-id", state="PENDING")
    monkeypatch.setattr(
        import_module(config_module), config_getter, AsyncMock(return_value=config)
    )
    monkeypatch.setattr(import_module("app.tasks.notification"), task_name, task)
    monkeypatch.setattr(
        notifications.Notification, "create", AsyncMock(return_value=created)
    )
    monkeypatch.setattr(
        notifications.NotificationDelivery, "create", AsyncMock(return_value=delivery)
    )
    monkeypatch.setattr(notifications, "create_notification", AsyncMock())

    response = await notifications.admin_create_notification(
        NotificationAdminCreate(
            scope=NotificationScope.GLOBAL,
            type="system.test",
            title="Test",
            content="Notification",
            notify_channels=[channel],
        ),
        user(superuser=True),
    )

    assert response["data"].deliveries[0].channel == channel
    assert delivery.task_id == "task-id"
    delivery.save.assert_awaited_once()
    task.delay.assert_called_once_with(str(created.id))
