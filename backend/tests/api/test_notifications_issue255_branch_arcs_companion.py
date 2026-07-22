from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import notifications as endpoint
from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import NotificationAdminCreate


class QueryStub:
    def __init__(self, *, count=0, rows=None, values=None):
        self.total = count
        self.rows = rows or []
        self.values = values or []
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
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

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def notification():
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        scope=NotificationScope.GLOBAL,
        team_id=None,
        user_id=None,
        type="system.test",
        source=NotificationSource.SYSTEM,
        title="Title",
        content="Content",
        level=NotificationLevel.MEDIUM,
        data=None,
        link_url=None,
        status=NotificationStatus.ACTIVE,
        expires_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_unread_list_with_no_read_ids_skips_exclusion():
    query = QueryStub()
    reads = MagicMock()
    reads.values_list = AsyncMock(return_value=[])

    with (
        patch.object(endpoint, "build_visible_query", AsyncMock(return_value=query)),
        patch.object(endpoint.NotificationRead, "filter", return_value=reads),
    ):
        result = await endpoint.list_notifications(
            scope=None,
            type=None,
            level=None,
            search=None,
            unread_only=True,
            created_from=None,
            created_to=None,
            page=1,
            page_size=20,
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert result["data"]["total"] == 0
    assert not any(call[0] == "exclude" for call in query.calls)


@pytest.mark.asyncio
async def test_admin_list_without_scope_still_filters_by_team():
    query = QueryStub()
    team_id = uuid4()

    with patch.object(endpoint.Notification, "all", return_value=query):
        result = await endpoint.admin_list_notifications(
            scope=None,
            team_id=team_id,
            user_id=None,
            type=None,
            level=None,
            search=None,
            include_expired=True,
            page=1,
            page_size=20,
            current_user=SimpleNamespace(is_superuser=True),
        )

    assert result["data"]["total"] == 0
    assert ("filter", (), {"team_id": team_id}) in query.calls


CHANNEL_CASES = [
    (
        NotificationChannel.DINGTALK,
        "app.core.dingtalk.get_dingtalk_config",
        {
            "enabled": True,
            "notification_type": "other",
            "webhook_url": "",
            "app_key": "",
            "app_secret": "",
            "agent_id": "",
        },
        "send_notification_dingtalk_task",
    ),
    (
        NotificationChannel.DINGTALK,
        "app.core.dingtalk.get_dingtalk_config",
        {
            "enabled": True,
            "notification_type": "app",
            "webhook_url": "",
            "app_key": "key",
            "app_secret": "secret",
            "agent_id": "agent",
        },
        "send_notification_dingtalk_task",
    ),
    (
        NotificationChannel.WECHAT,
        "app.core.wechat.get_wechat_config",
        {
            "enabled": True,
            "notification_type": "webhook",
            "webhook_url": "https://example.test/hook",
            "corp_id": "",
            "secret": "",
            "agent_id": "",
        },
        "send_notification_wechat_task",
    ),
    (
        NotificationChannel.WECHAT,
        "app.core.wechat.get_wechat_config",
        {
            "enabled": True,
            "notification_type": "other",
            "webhook_url": "",
            "corp_id": "",
            "secret": "",
            "agent_id": "",
        },
        "send_notification_wechat_task",
    ),
    (
        NotificationChannel.FEISHU,
        "app.core.feishu.get_feishu_config",
        {
            "enabled": True,
            "notification_type": "webhook",
            "webhook_url": "https://example.test/hook",
            "app_id": "",
            "app_secret": "",
        },
        "send_notification_feishu_task",
    ),
    (
        NotificationChannel.FEISHU,
        "app.core.feishu.get_feishu_config",
        {
            "enabled": True,
            "notification_type": "other",
            "webhook_url": "",
            "app_id": "",
            "app_secret": "",
        },
        "send_notification_feishu_task",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "config_path", "config", "task_name"), CHANNEL_CASES
)
async def test_valid_or_unhandled_channel_modes_continue_to_creation(
    channel, config_path, config, task_name
):
    item = notification()
    delivery = SimpleNamespace(
        channel=channel,
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=0,
        sent_at=None,
        created_at=item.created_at,
        updated_at=item.updated_at,
        task_id=None,
        save=AsyncMock(),
    )
    task = MagicMock()
    task.delay.return_value = SimpleNamespace(id="task-id", state="PENDING")
    payload = NotificationAdminCreate(
        scope=NotificationScope.GLOBAL,
        type="system.test",
        title="Title",
        content="Content",
        notify_channels=[channel],
    )

    with (
        patch(config_path, new=AsyncMock(return_value=config)),
        patch.object(endpoint.Notification, "create", AsyncMock(return_value=item)),
        patch.object(
            endpoint.NotificationDelivery,
            "create",
            AsyncMock(return_value=delivery),
        ),
        patch.object(endpoint, "create_notification", AsyncMock()),
        patch(f"app.tasks.notification.{task_name}", new=task),
    ):
        result = await endpoint.admin_create_notification(
            payload, SimpleNamespace(id=uuid4(), is_superuser=True)
        )

    assert result["data"].id == item.id
    task.delay.assert_called_once_with(str(item.id))
