from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.notifications import (
    admin_create_notification,
    admin_list_notifications,
    check_team_admin_permission,
    list_notifications,
    mark_read,
)
from app.models.notification import (
    Notification,
    NotificationAudit,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationRead,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.notification import NotificationAdminCreate, NotificationReadRequest
from app.schemas.response import BusinessError


class FakeQuery:
    def __init__(self, *, rows=None, ids=None, total=0):
        self.rows = rows or []
        self.ids = ids or []
        self.total = total
        self.filters = []
        self.excludes = []
        self.pagination = None

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.excludes.append((args, kwargs))
        return self

    async def count(self):
        return self.total

    def order_by(self, *args):
        return self

    def offset(self, value):
        self.pagination = [value, None]
        return self

    async def limit(self, value):
        self.pagination[1] = value
        return self.rows

    async def values_list(self, *args, **kwargs):
        return self.ids

    def __await__(self):
        async def result():
            return self.rows

        return result().__await__()


def notification_row(notification_id):
    timestamp = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=notification_id,
        scope=NotificationScope.GLOBAL,
        team_id=None,
        user_id=None,
        type="system.notice",
        source=NotificationSource.SYSTEM,
        title="Maintenance",
        content="Scheduled",
        level=NotificationLevel.MEDIUM,
        data=None,
        link_url=None,
        status=NotificationStatus.ACTIVE,
        expires_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.mark.asyncio
async def test_list_notifications_applies_filters_unread_and_pagination():
    user = SimpleNamespace(id=uuid4())
    unread_id = uuid4()
    read_id = uuid4()
    query = FakeQuery(rows=[notification_row(unread_id)], total=1)
    read_ids_query = FakeQuery(ids=[read_id])
    reads_query = FakeQuery(rows=[])

    with (
        patch(
            "app.api.v1.endpoints.notifications.build_visible_query",
            new=AsyncMock(return_value=query),
        ),
        patch.object(
            NotificationRead,
            "filter",
            side_effect=[read_ids_query, reads_query],
        ),
    ):
        response = await list_notifications(
            scope=NotificationScope.GLOBAL,
            type="system.notice",
            level="medium",
            search="maint",
            unread_only=True,
            created_from="2026-01-01",
            created_to="2026-12-31",
            page=2,
            page_size=10,
            current_user=user,
        )

    assert response["data"]["total"] == 1
    assert response["data"]["items"][0].id == unread_id
    assert response["data"]["items"][0].is_read is False
    assert query.pagination == [10, 10]
    assert query.excludes == [((), {"id__in": [read_id]})]
    keyword_filters = [kwargs for args, kwargs in query.filters if kwargs]
    assert keyword_filters == [
        {"scope": NotificationScope.GLOBAL},
        {"type": "system.notice"},
        {"level": "medium"},
        {"created_at__gte": "2026-01-01"},
        {"created_at__lte": "2026-12-31"},
    ]
    assert any(args for args, _ in query.filters)


@pytest.mark.asyncio
async def test_mark_read_deduplicates_existing_rows():
    user = SimpleNamespace(id=uuid4())
    existing_id, new_id = uuid4(), uuid4()
    visible_query = FakeQuery(ids=[existing_id, new_id])
    existing_query = FakeQuery(ids=[existing_id])

    with (
        patch(
            "app.api.v1.endpoints.notifications.build_visible_query",
            new=AsyncMock(return_value=visible_query),
        ),
        patch.object(NotificationRead, "filter", return_value=existing_query),
        patch.object(NotificationRead, "bulk_create", new=AsyncMock()) as create_reads,
        patch.object(
            NotificationAudit, "bulk_create", new=AsyncMock()
        ) as create_audits,
    ):
        response = await mark_read(
            NotificationReadRequest(notification_ids=[existing_id, new_id]), user
        )

    assert response["data"] == {"updated": 1}
    read_rows = create_reads.await_args.args[0]
    audit_rows = create_audits.await_args.args[0]
    assert len(read_rows) == 1
    assert len(audit_rows) == 1


@pytest.mark.asyncio
async def test_mark_read_empty_request_fails_fast():
    with pytest.raises(BusinessError) as exc_info:
        await mark_read(NotificationReadRequest(), SimpleNamespace(id=uuid4()))

    assert exc_info.value.status_code == 400
    assert exc_info.value.msg_key == "validation_error"


@pytest.mark.asyncio
async def test_mark_read_no_visible_notifications_is_noop():
    query = FakeQuery(ids=[])
    with (
        patch(
            "app.api.v1.endpoints.notifications.build_visible_query",
            new=AsyncMock(return_value=query),
        ),
        patch.object(NotificationRead, "bulk_create", new=AsyncMock()) as create_reads,
    ):
        response = await mark_read(
            NotificationReadRequest(notification_ids=[uuid4()]),
            SimpleNamespace(id=uuid4()),
        )

    assert response["data"] == {"updated": 0}
    create_reads.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_list_includes_safe_delivery_errors_and_pagination():
    notification_id = uuid4()
    notification = notification_row(notification_id)
    query = FakeQuery(rows=[notification], total=1)
    timestamp = datetime.now(timezone.utc)
    deliveries = FakeQuery(
        rows=[
            SimpleNamespace(
                notification_id=notification_id,
                channel=NotificationChannel.WEBHOOK,
                status=NotificationDeliveryStatus.FAILED,
                error_message="provider leaked details",
                retry_count=2,
                sent_at=None,
                created_at=timestamp,
                updated_at=timestamp,
            )
        ]
    )

    with (
        patch.object(Notification, "all", return_value=query),
        patch.object(NotificationDelivery, "filter", return_value=deliveries),
        patch("app.api.v1.endpoints.notifications.t", return_value="Unknown error"),
        patch("app.api.v1.endpoints.notifications.has_translation", return_value=False),
    ):
        response = await admin_list_notifications(
            scope=[NotificationScope.GLOBAL],
            type="system.notice",
            level=["medium"],
            search="maint",
            page=2,
            page_size=5,
            current_user=SimpleNamespace(is_superuser=True),
        )

    assert response["data"]["total"] == 1
    assert query.pagination == [5, 5]
    assert response["data"]["items"][0].deliveries[0].error_message == "Unknown error"
    assert any(args for args, _ in query.filters)


@pytest.mark.asyncio
async def test_team_admin_permission_handles_missing_team_and_non_admin():
    missing_team = MagicMock()
    missing_team.first = AsyncMock(return_value=None)
    with patch.object(Team, "filter", return_value=missing_team):
        with pytest.raises(BusinessError) as exc_info:
            await check_team_admin_permission(uuid4(), SimpleNamespace())
    assert exc_info.value.status_code == 404

    team = SimpleNamespace(id=uuid4())
    found_team = MagicMock()
    found_team.first = AsyncMock(return_value=team)
    missing_membership = MagicMock()
    missing_membership.first = AsyncMock(return_value=None)
    with (
        patch.object(Team, "filter", return_value=found_team),
        patch.object(TeamMember, "filter", return_value=missing_membership),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await check_team_admin_permission(
                team.id, SimpleNamespace(is_superuser=False)
            )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_user_notification_persists_without_external_dispatch():
    actor = SimpleNamespace(id=uuid4(), is_superuser=True)
    target_id = uuid4()
    created = notification_row(uuid4())
    created.scope = NotificationScope.USER
    created.user_id = target_id
    user_query = MagicMock()
    user_query.first = AsyncMock(return_value=SimpleNamespace(id=target_id))
    payload = NotificationAdminCreate(
        scope=NotificationScope.USER,
        user_id=target_id,
        type="account.notice",
        title="Account notice",
        content="Review your account",
    )

    with (
        patch.object(User, "filter", return_value=user_query),
        patch.object(
            Notification, "create", new=AsyncMock(return_value=created)
        ) as create,
        patch(
            "app.api.v1.endpoints.notifications.create_notification", new=AsyncMock()
        ) as persist,
        patch.object(
            NotificationDelivery, "create", new=AsyncMock()
        ) as create_delivery,
    ):
        response = await admin_create_notification(payload, actor)

    assert response["data"].id == created.id
    create.assert_awaited_once()
    persist.assert_awaited_once_with(created, actor=actor, meta={"source": "admin"})
    create_delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_create_rejects_missing_user_before_persistence():
    target_id = uuid4()
    user_query = MagicMock()
    user_query.first = AsyncMock(return_value=None)
    payload = NotificationAdminCreate(
        scope=NotificationScope.USER,
        user_id=target_id,
        type="account.notice",
        title="Account notice",
        content="Review your account",
    )

    with (
        patch.object(User, "filter", return_value=user_query),
        patch.object(Notification, "create", new=AsyncMock()) as create,
    ):
        with pytest.raises(BusinessError) as exc_info:
            await admin_create_notification(payload, SimpleNamespace(is_superuser=True))

    assert exc_info.value.status_code == 404
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_create_provider_failure_is_safe_and_does_not_persist():
    payload = NotificationAdminCreate(
        scope=NotificationScope.GLOBAL,
        type="system.notice",
        title="Maintenance",
        content="Scheduled",
        notify_channels=[NotificationChannel.WEBHOOK],
    )

    with (
        patch(
            "app.core.webhook.get_webhook_config",
            new=AsyncMock(return_value={"enabled": False, "url": None}),
        ),
        patch.object(Notification, "create", new=AsyncMock()) as create,
    ):
        with pytest.raises(BusinessError) as exc_info:
            await admin_create_notification(payload, SimpleNamespace(is_superuser=True))

    assert exc_info.value.status_code == 400
    assert exc_info.value.msg_key == "webhook_not_enabled"
    create.assert_not_awaited()
