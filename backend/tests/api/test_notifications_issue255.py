from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import notifications
from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import NotificationAdminCreate
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.team import TeamMemberRole


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value

    async def all(self):
        return self.value


def payload(**overrides):
    values = {
        "scope": NotificationScope.GLOBAL,
        "type": "system.test",
        "title": "Test",
        "content": "Test notification",
    }
    values.update(overrides)
    return NotificationAdminCreate(**values)


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
        "content": "Test notification",
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


@pytest.mark.parametrize(
    ("error_message", "status", "translated", "expected"),
    [
        (None, NotificationDeliveryStatus.FAILED, False, None),
        ("", NotificationDeliveryStatus.FAILED, False, None),
        (
            "smtp_not_enabled",
            NotificationDeliveryStatus.FAILED,
            True,
            "tr:smtp_not_enabled",
        ),
        (
            "provider details",
            NotificationDeliveryStatus.SUCCESS,
            False,
            "provider details",
        ),
        (
            "provider details",
            NotificationDeliveryStatus.FAILED,
            False,
            "tr:unknown_error",
        ),
    ],
)
def test_serialize_delivery_error_branches(
    monkeypatch, error_message, status, translated, expected
):
    monkeypatch.setattr(notifications, "has_translation", lambda _message: translated)
    monkeypatch.setattr(notifications, "t", lambda key: f"tr:{key}")

    assert notifications.serialize_delivery_error(error_message, status) == expected


@pytest.mark.anyio
async def test_team_admin_permission_rejects_missing_team(monkeypatch):
    monkeypatch.setattr(notifications.Team, "filter", MagicMock(return_value=Query()))

    with pytest.raises(BusinessError) as exc_info:
        await notifications.check_team_admin_permission(uuid4(), user())

    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "membership",
    [None, SimpleNamespace(role=TeamMemberRole.MEMBER)],
)
async def test_team_admin_permission_rejects_non_admin_members(monkeypatch, membership):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        notifications.Team, "filter", MagicMock(return_value=Query(team))
    )
    monkeypatch.setattr(
        notifications.TeamMember, "filter", MagicMock(return_value=Query(membership))
    )

    with pytest.raises(BusinessError) as exc_info:
        await notifications.check_team_admin_permission(team.id, user())

    assert exc_info.value.code == ResponseCode.TEAM_ADMIN_REQUIRED
    assert exc_info.value.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("role", [TeamMemberRole.OWNER, TeamMemberRole.ADMIN])
async def test_team_admin_permission_accepts_admin_roles(monkeypatch, role):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        notifications.Team, "filter", MagicMock(return_value=Query(team))
    )
    monkeypatch.setattr(
        notifications.TeamMember,
        "filter",
        MagicMock(return_value=Query(SimpleNamespace(role=role))),
    )

    assert await notifications.check_team_admin_permission(team.id, user()) is team


@pytest.mark.anyio
async def test_team_admin_permission_skips_membership_for_superuser(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    member_filter = MagicMock()
    monkeypatch.setattr(
        notifications.Team, "filter", MagicMock(return_value=Query(team))
    )
    monkeypatch.setattr(notifications.TeamMember, "filter", member_filter)

    assert (
        await notifications.check_team_admin_permission(team.id, user(superuser=True))
        is team
    )
    member_filter.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("notification_request", "current_user", "expected_code"),
    [
        (payload(), user(), ResponseCode.INSUFFICIENT_PRIVILEGES),
        (
            payload(scope=NotificationScope.TEAM),
            user(superuser=True),
            ResponseCode.BAD_REQUEST,
        ),
        (
            payload(scope=NotificationScope.USER),
            user(superuser=True),
            ResponseCode.BAD_REQUEST,
        ),
    ],
)
async def test_admin_create_rejects_invalid_scope_inputs(
    monkeypatch, notification_request, current_user, expected_code
):
    create = AsyncMock()
    monkeypatch.setattr(notifications.Notification, "create", create)

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_create_notification(
            notification_request, current_user
        )

    assert exc_info.value.code == expected_code
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_create_rejects_unknown_user(monkeypatch):
    request = payload(scope=NotificationScope.USER, user_id=uuid4())
    monkeypatch.setattr(notifications.User, "filter", MagicMock(return_value=Query()))
    create = AsyncMock()
    monkeypatch.setattr(notifications.Notification, "create", create)

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_create_notification(request, user(superuser=True))

    assert exc_info.value.code == ResponseCode.USER_NOT_FOUND
    create.assert_not_awaited()


CHANNEL_FAILURES = [
    (
        "app.core.email",
        "get_smtp_config",
        NotificationChannel.EMAIL,
        {"enabled": False},
        "smtp_not_enabled",
    ),
    (
        "app.core.email",
        "get_smtp_config",
        NotificationChannel.EMAIL,
        {"enabled": True, "host": "", "from_address": "sender@example.com"},
        "smtp_not_configured",
    ),
    (
        "app.core.dingtalk",
        "get_dingtalk_config",
        NotificationChannel.DINGTALK,
        {"enabled": False},
        "dingtalk_not_enabled",
    ),
    (
        "app.core.dingtalk",
        "get_dingtalk_config",
        NotificationChannel.DINGTALK,
        {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
        "dingtalk_not_configured",
    ),
    (
        "app.core.dingtalk",
        "get_dingtalk_config",
        NotificationChannel.DINGTALK,
        {
            "enabled": True,
            "notification_type": "app",
            "app_key": "",
            "app_secret": "secret",
            "agent_id": "agent",
        },
        "dingtalk_not_configured",
    ),
    (
        "app.core.wechat",
        "get_wechat_config",
        NotificationChannel.WECHAT,
        {"enabled": False},
        "wechat_not_enabled",
    ),
    (
        "app.core.wechat",
        "get_wechat_config",
        NotificationChannel.WECHAT,
        {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
        "wechat_not_configured",
    ),
    (
        "app.core.wechat",
        "get_wechat_config",
        NotificationChannel.WECHAT,
        {
            "enabled": True,
            "notification_type": "app",
            "corp_id": "corp",
            "secret": "",
            "agent_id": "agent",
        },
        "wechat_not_configured",
    ),
    (
        "app.core.feishu",
        "get_feishu_config",
        NotificationChannel.FEISHU,
        {"enabled": False},
        "feishu_not_enabled",
    ),
    (
        "app.core.feishu",
        "get_feishu_config",
        NotificationChannel.FEISHU,
        {"enabled": True, "notification_type": "webhook", "webhook_url": ""},
        "feishu_not_configured",
    ),
    (
        "app.core.feishu",
        "get_feishu_config",
        NotificationChannel.FEISHU,
        {
            "enabled": True,
            "notification_type": "app",
            "app_id": "app",
            "app_secret": "",
        },
        "feishu_not_configured",
    ),
    (
        "app.core.webhook",
        "get_webhook_config",
        NotificationChannel.WEBHOOK,
        {"enabled": False},
        "webhook_not_enabled",
    ),
    (
        "app.core.webhook",
        "get_webhook_config",
        NotificationChannel.WEBHOOK,
        {"enabled": True, "url": ""},
        "webhook_not_configured",
    ),
    (
        "app.core.slack",
        "get_slack_config",
        NotificationChannel.SLACK,
        {"enabled": False},
        "slack_not_enabled",
    ),
    (
        "app.core.slack",
        "get_slack_config",
        NotificationChannel.SLACK,
        {"enabled": True, "webhook_url": ""},
        "slack_not_configured",
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("module_name", "getter_name", "channel", "config", "message_key"),
    CHANNEL_FAILURES,
)
async def test_admin_create_rejects_invalid_channel_configuration(
    monkeypatch, module_name, getter_name, channel, config, message_key
):
    monkeypatch.setattr(
        import_module(module_name), getter_name, AsyncMock(return_value=config)
    )
    create = AsyncMock()
    monkeypatch.setattr(notifications.Notification, "create", create)

    with pytest.raises(BusinessError) as exc_info:
        await notifications.admin_create_notification(
            payload(notify_channels=[channel]), user(superuser=True)
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == message_key
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_admin_create_without_channels_persists_and_returns_notification(
    monkeypatch,
):
    created = notification()
    create = AsyncMock(return_value=created)
    publish = AsyncMock()
    monkeypatch.setattr(notifications.Notification, "create", create)
    monkeypatch.setattr(notifications, "create_notification", publish)

    response = await notifications.admin_create_notification(
        payload(), user(superuser=True)
    )

    assert response["data"].id == created.id
    assert response["data"].deliveries == []
    create.assert_awaited_once()
    publish.assert_awaited_once()
