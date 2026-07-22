from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
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
from app.schemas.notification import NotificationAdminCreate, NotificationReadRequest
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberRole


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
        self.calls.append(("order_by", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    async def count(self):
        return self.total

    async def values_list(self, *args, **kwargs):
        return self.values

    async def first(self):
        return self.first_value

    async def all(self):
        return self.rows

    async def delete(self):
        self.calls.append(("delete", (), {}))
        return 1

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


def assert_error(exc_info, code, key):
    assert exc_info.value.code == code
    assert exc_info.value.msg_key == key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("team_ids", "include_expired"), [([], True), ([uuid4()], False)]
)
async def test_build_visible_query_routes_team_and_expiration_preferences(
    team_ids, include_expired
):
    query = QueryStub()
    with (
        patch.object(
            endpoint.TeamMember,
            "filter",
            Mock(return_value=QueryStub(values=team_ids)),
        ),
        patch.object(endpoint.Notification, "filter", Mock(return_value=query)),
    ):
        result = await endpoint.build_visible_query(
            user(), include_expired=include_expired
        )

    assert result is query
    assert sum(call[0] == "filter" for call in query.calls) == (not include_expired)


@pytest.mark.asyncio
async def test_visible_query_and_user_list_cover_filters_and_read_state():
    current_user = user()
    item = notification()
    visible = QueryStub(rows=[item], count=1)
    read_at = datetime(2026, 1, 2, tzinfo=UTC)
    reads = QueryStub(rows=[SimpleNamespace(notification_id=item.id, read_at=read_at)])

    with (
        patch.object(endpoint, "build_visible_query", AsyncMock(return_value=visible)),
        patch.object(
            endpoint.NotificationRead,
            "filter",
            Mock(side_effect=[QueryStub(values=[uuid4()]), reads]),
        ),
    ):
        result = await endpoint.list_notifications(
            scope=NotificationScope.GLOBAL,
            type="system.test",
            level="medium",
            search="title",
            unread_only=True,
            created_from="2026-01-01",
            created_to="2026-01-31",
            page=2,
            page_size=5,
            current_user=current_user,
        )

    assert result["data"]["items"][0].is_read is True
    assert result["data"]["items"][0].read_at == read_at
    assert ("offset", (5,), {}) in visible.calls
    assert any(call[0] == "exclude" for call in visible.calls)


@pytest.mark.asyncio
async def test_user_list_empty_and_unread_count_without_existing_reads():
    current_user = user()
    empty = QueryStub(count=0)
    unread = QueryStub(count=3)

    with patch.object(endpoint, "build_visible_query", AsyncMock(return_value=empty)):
        listed = await endpoint.list_notifications(
            scope=None,
            type=None,
            level=None,
            search=None,
            unread_only=False,
            created_from=None,
            created_to=None,
            page=1,
            page_size=20,
            current_user=current_user,
        )

    with (
        patch.object(endpoint, "build_visible_query", AsyncMock(return_value=unread)),
        patch.object(
            endpoint.NotificationRead,
            "filter",
            Mock(return_value=QueryStub(values=[])),
        ),
    ):
        count = await endpoint.get_unread_count(current_user=current_user)

    assert listed["data"]["items"] == []
    assert count["data"].total == 3
    assert not any(call[0] == "exclude" for call in unread.calls)


@pytest.mark.asyncio
async def test_mark_read_validation_and_zero_update_paths():
    current_user = user()
    with pytest.raises(BusinessError) as exc_info:
        await endpoint.mark_read(NotificationReadRequest(), current_user=current_user)
    assert_error(exc_info, ResponseCode.BAD_REQUEST, "validation_error")

    with (
        patch.object(
            endpoint,
            "build_visible_query",
            AsyncMock(return_value=QueryStub(values=[])),
        ),
        patch.object(
            endpoint.NotificationRead,
            "filter",
            Mock(return_value=QueryStub(values=[])),
        ),
    ):
        result = await endpoint.mark_read(
            NotificationReadRequest(mark_all=True), current_user=current_user
        )
    assert result["data"] == {"updated": 0}

    notification_id = uuid4()
    with (
        patch.object(
            endpoint,
            "build_visible_query",
            AsyncMock(return_value=QueryStub(values=[notification_id])),
        ),
        patch.object(
            endpoint.NotificationRead,
            "filter",
            Mock(
                side_effect=[
                    QueryStub(values=[]),
                    QueryStub(values=[notification_id]),
                ]
            ),
        ),
    ):
        result = await endpoint.mark_read(
            NotificationReadRequest(mark_all=True), current_user=current_user
        )
    assert result["data"] == {"updated": 0}


@pytest.mark.asyncio
async def test_mark_read_bulk_creates_only_new_rows():
    current_user = user()
    old_id, new_id = uuid4(), uuid4()
    visible = QueryStub(values=[old_id, new_id])

    with (
        patch.object(endpoint, "build_visible_query", AsyncMock(return_value=visible)),
        patch.object(
            endpoint.NotificationRead,
            "filter",
            Mock(return_value=QueryStub(values=[old_id])),
        ),
        patch.object(
            endpoint.NotificationRead, "bulk_create", AsyncMock()
        ) as bulk_read,
        patch(
            "app.models.notification.NotificationAudit.bulk_create", new=AsyncMock()
        ) as bulk_audit,
    ):
        result = await endpoint.mark_read(
            NotificationReadRequest(notification_ids=[old_id, new_id]),
            current_user=current_user,
        )

    assert result["data"] == {"updated": 1}
    assert len(bulk_read.await_args.args[0]) == 1
    assert len(bulk_audit.await_args.args[0]) == 1


@pytest.mark.asyncio
async def test_team_admin_permission_access_branches():
    current_user = user()
    with patch.object(
        endpoint.Team, "filter", Mock(return_value=QueryStub(first=None))
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.check_team_admin_permission(uuid4(), current_user)
    assert_error(exc_info, ResponseCode.TEAM_NOT_FOUND, "team_not_found")

    team = SimpleNamespace(id=uuid4())
    with (
        patch.object(endpoint.Team, "filter", Mock(return_value=QueryStub(first=team))),
        patch.object(
            endpoint.TeamMember,
            "filter",
            Mock(return_value=QueryStub(first=SimpleNamespace(role="member"))),
        ),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.check_team_admin_permission(team.id, current_user)
    assert_error(exc_info, ResponseCode.TEAM_ADMIN_REQUIRED, "team_admin_required")

    membership = SimpleNamespace(role=TeamMemberRole.ADMIN)
    with (
        patch.object(endpoint.Team, "filter", Mock(return_value=QueryStub(first=team))),
        patch.object(
            endpoint.TeamMember,
            "filter",
            Mock(return_value=QueryStub(first=membership)),
        ),
    ):
        assert await endpoint.check_team_admin_permission(team.id, current_user) is team


@pytest.mark.asyncio
async def test_admin_list_access_errors_and_delivery_serialization():
    current_user = user()
    with pytest.raises(BusinessError) as exc_info:
        await endpoint.admin_list_notifications(
            scope=[NotificationScope.GLOBAL],
            team_id=None,
            user_id=None,
            type=None,
            level=None,
            search=None,
            include_expired=False,
            page=1,
            page_size=20,
            current_user=current_user,
        )
    assert_error(
        exc_info, ResponseCode.INSUFFICIENT_PRIVILEGES, "insufficient_privileges"
    )

    with pytest.raises(BusinessError) as exc_info:
        await endpoint.admin_list_notifications(
            scope=None,
            team_id=None,
            user_id=None,
            type=None,
            level=None,
            search=None,
            include_expired=False,
            page=1,
            page_size=20,
            current_user=current_user,
        )
    assert_error(exc_info, ResponseCode.BAD_REQUEST, "notification_scope_requires_team")

    item = notification()
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    delivery = SimpleNamespace(
        notification_id=item.id,
        channel=NotificationChannel.EMAIL,
        status=NotificationDeliveryStatus.FAILED,
        error_message="raw provider secret",
        retry_count=1,
        sent_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    query = QueryStub(rows=[item], count=1)
    with (
        patch.object(endpoint.Notification, "all", Mock(return_value=query)),
        patch.object(
            endpoint.NotificationDelivery,
            "filter",
            Mock(return_value=QueryStub(rows=[delivery])),
        ),
    ):
        result = await endpoint.admin_list_notifications(
            scope=[NotificationScope.GLOBAL],
            team_id=None,
            user_id=uuid4(),
            type="system.test",
            level=["medium"],
            search="Title",
            include_expired=True,
            page=1,
            page_size=20,
            current_user=user(superuser=True),
        )

    assert (
        result["data"]["items"][0].deliveries[0].error_message != delivery.error_message
    )
    assert endpoint.serialize_delivery_error(None, delivery.status) is None
    assert (
        endpoint.serialize_delivery_error(
            "raw success", NotificationDeliveryStatus.SUCCESS
        )
        == "raw success"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("create_payload", "expected_code", "expected_key"),
    [
        (
            payload(scope=NotificationScope.GLOBAL),
            ResponseCode.INSUFFICIENT_PRIVILEGES,
            "insufficient_privileges",
        ),
        (
            payload(scope=NotificationScope.TEAM),
            ResponseCode.BAD_REQUEST,
            "notification_scope_requires_team",
        ),
        (
            payload(scope=NotificationScope.USER),
            ResponseCode.BAD_REQUEST,
            "notification_scope_requires_user",
        ),
    ],
)
async def test_admin_create_scope_access_errors(
    create_payload, expected_code, expected_key
):
    with pytest.raises(BusinessError) as exc_info:
        await endpoint.admin_create_notification(create_payload, current_user=user())
    assert_error(exc_info, expected_code, expected_key)


@pytest.mark.asyncio
async def test_admin_create_user_lookup_and_batch_errors():
    current_user = user(superuser=True)
    missing_user = payload(scope=NotificationScope.USER, user_id=uuid4())
    with patch.object(
        endpoint.User, "filter", Mock(return_value=QueryStub(first=None))
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_create_notification(
                missing_user, current_user=current_user
            )
    assert_error(exc_info, ResponseCode.USER_NOT_FOUND, "user_not_found")

    ids = [uuid4(), uuid4()]
    batch = payload(scope=NotificationScope.USER, user_ids=ids)
    with patch.object(
        endpoint.User,
        "filter",
        Mock(return_value=QueryStub(rows=[SimpleNamespace(id=ids[0])])),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_create_notification(batch, current_user=current_user)
    assert_error(exc_info, ResponseCode.USER_NOT_FOUND, "some_users_not_found")


CHANNEL_CASES = [
    (
        NotificationChannel.EMAIL,
        "app.core.email.get_smtp_config",
        {"enabled": True, "host": "smtp", "from_address": "from@example.com"},
    ),
    (
        NotificationChannel.DINGTALK,
        "app.core.dingtalk.get_dingtalk_config",
        {
            "enabled": True,
            "notification_type": "webhook",
            "webhook_url": "https://example.test",
        },
    ),
    (
        NotificationChannel.WECHAT,
        "app.core.wechat.get_wechat_config",
        {
            "enabled": True,
            "notification_type": "app",
            "corp_id": "corp",
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
            "app_id": "app",
            "app_secret": "secret",
        },
    ),
    (
        NotificationChannel.WEBHOOK,
        "app.core.webhook.get_webhook_config",
        {"enabled": True, "url": "https://example.test"},
    ),
    (
        NotificationChannel.SLACK,
        "app.core.slack.get_slack_config",
        {"enabled": True, "webhook_url": "https://example.test"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "config_path", "config"), CHANNEL_CASES)
async def test_admin_create_routes_each_channel_without_external_delivery(
    channel, config_path, config
):
    created = notification()
    timestamp = created.created_at
    delivery = SimpleNamespace(
        channel=channel,
        status=NotificationDeliveryStatus.PENDING,
        error_message=None,
        retry_count=0,
        sent_at=None,
        created_at=timestamp,
        updated_at=timestamp,
        task_id=None,
        save=AsyncMock(),
    )
    task = SimpleNamespace(
        delay=Mock(return_value=SimpleNamespace(id="task-id", state="PENDING"))
    )
    task_name = {
        NotificationChannel.EMAIL: "send_notification_email_task",
        NotificationChannel.DINGTALK: "send_notification_dingtalk_task",
        NotificationChannel.WECHAT: "send_notification_wechat_task",
        NotificationChannel.FEISHU: "send_notification_feishu_task",
        NotificationChannel.WEBHOOK: "send_notification_webhook_task",
        NotificationChannel.SLACK: "send_notification_slack_task",
    }[channel]

    with (
        patch(config_path, new=AsyncMock(return_value=config)),
        patch.object(endpoint.Notification, "create", AsyncMock(return_value=created)),
        patch.object(endpoint, "create_notification", AsyncMock()),
        patch.object(
            endpoint.NotificationDelivery, "create", AsyncMock(return_value=delivery)
        ),
        patch(f"app.tasks.notification.{task_name}", task),
    ):
        result = await endpoint.admin_create_notification(
            payload(notify_channels=[channel]), current_user=user(superuser=True)
        )

    task.delay.assert_called_once_with(str(created.id))
    delivery.save.assert_awaited_once()
    assert result["data"].deliveries[0].channel == channel


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("channel", "config_path", "config", "key"),
    [
        (
            NotificationChannel.EMAIL,
            "app.core.email.get_smtp_config",
            {"enabled": False},
            "smtp_not_enabled",
        ),
        (
            NotificationChannel.EMAIL,
            "app.core.email.get_smtp_config",
            {"enabled": True, "host": "", "from_address": ""},
            "smtp_not_configured",
        ),
        (
            NotificationChannel.DINGTALK,
            "app.core.dingtalk.get_dingtalk_config",
            {"enabled": False},
            "dingtalk_not_enabled",
        ),
        (
            NotificationChannel.DINGTALK,
            "app.core.dingtalk.get_dingtalk_config",
            {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
            "dingtalk_not_configured",
        ),
        (
            NotificationChannel.WECHAT,
            "app.core.wechat.get_wechat_config",
            {"enabled": False},
            "wechat_not_enabled",
        ),
        (
            NotificationChannel.WECHAT,
            "app.core.wechat.get_wechat_config",
            {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
            "wechat_not_configured",
        ),
        (
            NotificationChannel.FEISHU,
            "app.core.feishu.get_feishu_config",
            {"enabled": False},
            "feishu_not_enabled",
        ),
        (
            NotificationChannel.FEISHU,
            "app.core.feishu.get_feishu_config",
            {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
            "feishu_not_configured",
        ),
        (
            NotificationChannel.WEBHOOK,
            "app.core.webhook.get_webhook_config",
            {"enabled": False},
            "webhook_not_enabled",
        ),
        (
            NotificationChannel.WEBHOOK,
            "app.core.webhook.get_webhook_config",
            {"enabled": True, "url": ""},
            "webhook_not_configured",
        ),
        (
            NotificationChannel.SLACK,
            "app.core.slack.get_slack_config",
            {"enabled": False},
            "slack_not_enabled",
        ),
        (
            NotificationChannel.SLACK,
            "app.core.slack.get_slack_config",
            {"enabled": True, "webhook_url": ""},
            "slack_not_configured",
        ),
    ],
)
async def test_admin_create_rejects_disabled_or_incomplete_channel_preferences(
    channel, config_path, config, key
):
    with patch(config_path, new=AsyncMock(return_value=config)):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_create_notification(
                payload(notify_channels=[channel]), current_user=user(superuser=True)
            )
    assert_error(exc_info, ResponseCode.BAD_REQUEST, key)


@pytest.mark.asyncio
async def test_admin_delete_access_errors_and_success():
    notification_id = uuid4()
    current_user = user()

    with patch.object(
        endpoint.Notification, "filter", Mock(return_value=QueryStub(first=None))
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_delete_notification(notification_id, current_user)
    assert_error(exc_info, ResponseCode.NOT_FOUND, "notification_not_found")

    global_item = notification(id=notification_id)
    with patch.object(
        endpoint.Notification,
        "filter",
        Mock(return_value=QueryStub(first=global_item)),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_delete_notification(notification_id, current_user)
    assert_error(
        exc_info, ResponseCode.INSUFFICIENT_PRIVILEGES, "insufficient_privileges"
    )

    team_item = notification(
        id=notification_id, scope=NotificationScope.TEAM, team_id=None
    )
    with patch.object(
        endpoint.Notification, "filter", Mock(return_value=QueryStub(first=team_item))
    ):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint.admin_delete_notification(notification_id, current_user)
    assert_error(exc_info, ResponseCode.BAD_REQUEST, "notification_scope_requires_team")

    first_query = QueryStub(first=global_item)
    delete_query = QueryStub()
    with (
        patch.object(
            endpoint.Notification,
            "filter",
            Mock(side_effect=[first_query, delete_query]),
        ),
        patch.object(endpoint, "create_notification_audit", AsyncMock()) as audit,
    ):
        result = await endpoint.admin_delete_notification(
            notification_id, user(superuser=True)
        )

    audit.assert_awaited_once()
    assert ("delete", (), {}) in delete_query.calls
    assert result["data"] == {"id": str(notification_id)}
