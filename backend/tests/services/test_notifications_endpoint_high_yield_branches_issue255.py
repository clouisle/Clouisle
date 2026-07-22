from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import notifications as endpoint
from app.models.notification import (
    NotificationChannel,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import NotificationAdminCreate
from app.schemas.response import BusinessError, ResponseCode


class QueryStub:
    def __init__(self, *, rows=None, count=0, values=None, first=None):
        self.rows = rows or []
        self.total = count
        self.values = values or []
        self.first_value = first
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

    async def first(self):
        return self.first_value

    async def all(self):
        return self.rows

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def notification(**overrides):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    values = {
        "id": uuid4(),
        "scope": NotificationScope.GLOBAL,
        "team_id": None,
        "user_id": None,
        "type": "system.test",
        "source": NotificationSource.SYSTEM,
        "title": "Title",
        "content": "Content",
        "level": NotificationLevel.MEDIUM,
        "data": None,
        "link_url": None,
        "status": NotificationStatus.ACTIVE,
        "expires_at": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def payload(**overrides):
    values = {
        "scope": NotificationScope.GLOBAL,
        "type": "system.test",
        "title": "Title",
        "content": "Content",
    }
    values.update(overrides)
    return NotificationAdminCreate(**values)


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def assert_business_error(exc_info, code, key):
    assert exc_info.value.code == code
    assert exc_info.value.msg_key == key


@pytest.mark.asyncio
async def test_list_notifications_excludes_nonempty_read_ids():
    visible_query = QueryStub()
    read_query = QueryStub(values=[uuid4()])

    with (
        patch.object(
            endpoint, "build_visible_query", AsyncMock(return_value=visible_query)
        ),
        patch.object(
            endpoint.NotificationRead, "filter", Mock(return_value=read_query)
        ),
    ):
        result = await endpoint.list_notifications(
            None, None, None, None, True, None, None, 1, 20, user()
        )

    assert any(call[0] == "exclude" for call in visible_query.calls)
    assert result["data"]["items"] == []


@pytest.mark.asyncio
async def test_admin_list_applies_scope_filter():
    query = QueryStub()

    with patch.object(endpoint.Notification, "all", Mock(return_value=query)):
        await endpoint.admin_list_notifications(
            [NotificationScope.GLOBAL],
            None,
            None,
            None,
            None,
            None,
            True,
            1,
            20,
            user(superuser=True),
        )

    assert ("filter", (), {"scope__in": [NotificationScope.GLOBAL]}) in query.calls


@pytest.mark.asyncio
async def test_admin_create_empty_user_batch_reports_creation_failure():
    class TruthyEmptyList(list):
        def __bool__(self):
            return True

    current_user = user(superuser=True)
    request = payload(scope=NotificationScope.USER, user_ids=[uuid4()])
    request.user_ids = TruthyEmptyList()

    with patch.object(endpoint.User, "filter", Mock(return_value=QueryStub(rows=[]))):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_create_notification(request, current_user)

    assert_business_error(
        exc_info, ResponseCode.INTERNAL_ERROR, "notification_creation_failed"
    )


@pytest.mark.asyncio
async def test_admin_create_non_superuser_single_user_continues_to_create():
    target_user_id = uuid4()
    created = notification(scope=NotificationScope.USER, user_id=target_user_id)

    with (
        patch.object(
            endpoint.User,
            "filter",
            Mock(return_value=QueryStub(first=SimpleNamespace(id=target_user_id))),
        ),
        patch.object(endpoint.Notification, "create", AsyncMock(return_value=created)),
        patch.object(endpoint, "create_notification", AsyncMock()),
    ):
        result = await endpoint.admin_create_notification(
            payload(scope=NotificationScope.USER, user_id=target_user_id), user()
        )

    assert result["data"].user_id == target_user_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "config_target", "config"),
    [
        (
            NotificationChannel.DINGTALK,
            "app.core.dingtalk.get_dingtalk_config",
            {
                "enabled": True,
                "notification_type": "app",
                "app_key": "",
                "app_secret": "secret",
                "agent_id": "agent",
            },
        ),
        (
            NotificationChannel.WECHAT,
            "app.core.wechat.get_wechat_config",
            {
                "enabled": True,
                "notification_type": "app",
                "corp_id": "",
                "secret": "secret",
                "agent_id": "agent",
            },
        ),
        (
            NotificationChannel.FEISHU,
            "app.core.feishu.get_feishu_config",
            {
                "enabled": True,
                "notification_type": "app",
                "app_id": "",
                "app_secret": "secret",
            },
        ),
    ],
)
async def test_admin_create_rejects_incomplete_external_app_config(
    channel, config_target, config
):
    with (
        patch(config_target, new=AsyncMock(return_value=config)),
        pytest.raises(BusinessError) as exc_info,
    ):
        await endpoint.admin_create_notification(
            payload(notify_channels=[channel]), user(superuser=True)
        )

    assert_business_error(
        exc_info, ResponseCode.BAD_REQUEST, f"{channel.value}_not_configured"
    )


@pytest.mark.asyncio
async def test_admin_delete_user_notification_allows_superuser():
    item = notification(scope=NotificationScope.USER, user_id=uuid4())
    first_query = QueryStub(first=item)
    delete_query = QueryStub()
    delete_query.delete = AsyncMock(return_value=1)

    with (
        patch.object(
            endpoint.Notification,
            "filter",
            Mock(side_effect=[first_query, delete_query]),
        ),
        patch.object(endpoint, "create_notification_audit", AsyncMock()) as audit,
    ):
        result = await endpoint.admin_delete_notification(item.id, user(superuser=True))

    audit.assert_awaited_once()
    delete_query.delete.assert_awaited_once()
    assert result["data"] == {"id": str(item.id)}
