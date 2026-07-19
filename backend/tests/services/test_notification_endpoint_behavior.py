from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.notifications import list_notifications, mark_read
from app.models.notification import (
    NotificationAudit,
    NotificationLevel,
    NotificationRead,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import NotificationReadRequest
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
