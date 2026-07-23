from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import audit_logs
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._chain("filter", *args, **kwargs)

    def order_by(self, *args):
        return self._chain("order_by", *args)

    def offset(self, value):
        return self._chain("offset", value)

    def limit(self, value):
        return self._chain("limit", value)

    def distinct(self):
        return self._chain("distinct")

    def values_list(self, *args, **kwargs):
        return self._chain("values_list", *args, **kwargs)

    def annotate(self, **kwargs):
        return self._chain("annotate", **kwargs)

    def group_by(self, *args):
        return self._chain("group_by", *args)

    def values(self, *args):
        return self._chain("values", *args)

    async def count(self):
        return self.total

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def _log(**overrides):
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
        "username": "admin",
        "team_id": uuid4(),
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
        "action": "update_user",
        "resource_type": "user",
        "resource_id": uuid4(),
        "resource_name": "member",
        "operation": "update",
        "status": "success",
        "error_message": None,
        "changes": None,
        "metadata": None,
        "auth_method": "jwt",
        "api_key_id": None,
        "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _body(response):
    chunks = [chunk async for chunk in response.body_iterator]
    return b"".join(
        chunk if isinstance(chunk, bytes) else chunk.encode() for chunk in chunks
    )


def test_error_serialization_covers_empty_translated_safe_and_hidden(monkeypatch):
    monkeypatch.setattr(audit_logs, "has_translation", lambda value: value == "known")
    monkeypatch.setattr(audit_logs, "t", lambda value: f"translated:{value}")
    monkeypatch.setattr(
        audit_logs, "is_safe_user_visible_error", lambda value: value == "safe"
    )

    assert audit_logs.serialize_audit_error(None) is None
    assert audit_logs.serialize_audit_error("known") == "translated:known"
    assert audit_logs.serialize_audit_error("safe") == "safe"
    assert audit_logs.serialize_audit_error("secret") == "translated:unknown_error"


@pytest.mark.anyio
async def test_actions_and_route_permissions_are_exposed():
    response = await audit_logs.get_audit_log_actions(current_user=MagicMock())

    assert response["data"] is audit_logs.AUDIT_ACTION_OPTIONS
    permissions = {
        route.path: {
            dependency.call.required_permission
            for dependency in route.dependant.dependencies
            if hasattr(dependency.call, "required_permission")
        }
        for route in audit_logs.router.routes
    }
    assert permissions["/actions"] == {"audit:read"}
    assert permissions[""] == {"audit:read"}
    assert permissions["/stats"] == {"audit:read"}
    assert permissions["/stats/retention"] == {"audit:read"}
    assert permissions["/archive"] == {"audit:export"}
    assert permissions["/export"] == {"audit:export"}
    assert permissions["/{log_id}"] == {"audit:read"}


@pytest.mark.anyio
async def test_list_applies_all_filters_paginates_and_serializes(monkeypatch):
    log = _log(error_message="unsafe")
    query = _Query([log], count=21)
    monkeypatch.setattr(audit_logs.AuditLog, "all", MagicMock(return_value=query))
    monkeypatch.setattr(audit_logs, "serialize_audit_error", lambda value: "hidden")
    user_id, team_id, resource_id = uuid4(), uuid4(), uuid4()

    response = await audit_logs.list_audit_logs(
        user_id=user_id,
        team_id=team_id,
        action=["login_success"],
        resource_type="user",
        resource_id=resource_id,
        status=["failed"],
        start_date="2026-01-01",
        end_date="2026-01-31",
        search="member",
        page=2,
        page_size=20,
        current_user=MagicMock(),
    )

    data = response["data"]
    assert (data["total"], data["page"], data["total_pages"]) == (21, 2, 2)
    assert data["items"][0].error_message == "hidden"
    filter_kwargs = [call[2] for call in query.calls if call[0] == "filter"]
    assert filter_kwargs[:-1] == [
        {"user_id": user_id},
        {"team_id": team_id},
        {"action__in": ["login_success"]},
        {"resource_type": "user"},
        {"resource_id": resource_id},
        {"status__in": ["failed"]},
        {"created_at__gte": "2026-01-01"},
        {"created_at__lte": "2026-01-31"},
    ]
    assert filter_kwargs[-1] == {}
    assert ("offset", (20,), {}) in query.calls
    assert ("limit", (20,), {}) in query.calls


@pytest.mark.anyio
async def test_list_without_filters_returns_empty_page(monkeypatch):
    query = _Query([], count=0)
    monkeypatch.setattr(audit_logs.AuditLog, "all", MagicMock(return_value=query))

    response = await audit_logs.list_audit_logs(
        user_id=None,
        team_id=None,
        action=None,
        resource_type=None,
        resource_id=None,
        status=None,
        start_date=None,
        end_date=None,
        search=None,
        page=1,
        page_size=20,
        current_user=MagicMock(),
    )

    assert response["data"] == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
    }
    assert not [call for call in query.calls if call[0] == "filter"]


@pytest.mark.anyio
async def test_stats_uses_aggregates_and_ignores_anonymous_active_users(monkeypatch):
    active_id = uuid4()
    all_queries = iter(
        [
            _Query(count=12),
            _Query([{"action": "login", "count": 7}]),
        ]
    )
    filter_queries = iter(
        [
            _Query(count=4),
            _Query(count=2),
            _Query([active_id, None]),
            _Query([{"user_id": active_id, "username": "admin", "count": 5}]),
        ]
    )
    monkeypatch.setattr(audit_logs.AuditLog, "all", lambda: next(all_queries))
    monkeypatch.setattr(
        audit_logs.AuditLog, "filter", lambda **kwargs: next(filter_queries)
    )
    fixed_now = datetime(2026, 1, 10, 12, tzinfo=UTC)
    monkeypatch.setattr(audit_logs, "now_utc", lambda: fixed_now)

    response = await audit_logs.get_audit_log_stats(current_user=MagicMock())

    stats = response["data"]
    assert stats.model_dump() == {
        "total_logs": 12,
        "today_logs": 4,
        "failed_logs": 2,
        "active_users": 1,
        "top_actions": [{"action": "login", "count": 7}],
        "top_users": [{"user_id": active_id, "username": "admin", "count": 5}],
    }


@pytest.mark.anyio
@pytest.mark.parametrize("oldest", [None, _log()])
async def test_retention_stats_covers_missing_and_present_oldest(monkeypatch, oldest):
    fixed_now = datetime(2026, 2, 1, 12, tzinfo=UTC)
    all_queries = iter([_Query(count=30), _Query(oldest)])
    monkeypatch.setattr(audit_logs, "now_utc", lambda: fixed_now)
    monkeypatch.setattr(audit_logs.SiteSetting, "get_value", AsyncMock(return_value=90))
    monkeypatch.setattr(audit_logs.AuditLog, "all", lambda: next(all_queries))
    monkeypatch.setattr(
        audit_logs.AuditLog, "filter", MagicMock(return_value=_Query(count=8))
    )

    response = await audit_logs.get_retention_stats(current_user=MagicMock())

    stats = response["data"]
    assert stats.total_logs == 30
    assert stats.logs_to_archive == 8
    assert stats.retention_days == 90
    assert stats.oldest_log_date == (oldest.created_at.isoformat() if oldest else None)
    assert stats.next_archive_date == "2026-02-02T03:00:00+00:00"


@pytest.mark.anyio
async def test_manual_archive_dispatches_task(monkeypatch):
    task = SimpleNamespace(id=uuid4())
    delay = MagicMock(return_value=task)
    monkeypatch.setattr("app.tasks.audit_log.archive_old_audit_logs.delay", delay)

    response = await audit_logs.trigger_manual_archive(current_user=MagicMock())

    delay.assert_called_once_with()
    assert response["data"] == {"task_id": str(task.id)}


@pytest.mark.anyio
@pytest.mark.parametrize("format", ["csv", "json"])
async def test_export_applies_filters_and_emits_both_formats(monkeypatch, format):
    log = _log(
        username=None,
        resource_name=None,
        ip_address=None,
        error_message="safe",
        created_at=None if format == "csv" else datetime(2026, 1, 2, tzinfo=UTC),
    )
    query = _Query([log])
    monkeypatch.setattr(audit_logs.AuditLog, "all", MagicMock(return_value=query))
    monkeypatch.setattr(audit_logs, "serialize_audit_error", lambda value: value)
    monkeypatch.setattr(
        audit_logs,
        "now_utc",
        lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    user_id, team_id = uuid4(), uuid4()

    response = await audit_logs.export_audit_logs(
        format=format,
        user_id=user_id,
        team_id=team_id,
        action=["update_user"],
        resource_type="user",
        status=["success"],
        start_date="2026-01-01",
        end_date="2026-01-31",
        search="member",
        current_user=MagicMock(),
    )
    body = await _body(response)

    assert (
        response.media_type
        == f"{'text/csv' if format == 'csv' else 'application/json'}"
    )
    assert "audit-logs-20260102-030405" in response.headers["content-disposition"]
    assert b"update_user" in body
    assert ("limit", (10000,), {}) in query.calls
    assert len([call for call in query.calls if call[0] == "filter"]) == 8
    if format == "csv":
        assert body.startswith(b"ID,Time,User,Action")
    else:
        assert b'"username": null' in body


@pytest.mark.anyio
async def test_export_without_filters_skips_filtering(monkeypatch):
    query = _Query([])
    monkeypatch.setattr(audit_logs.AuditLog, "all", MagicMock(return_value=query))

    response = await audit_logs.export_audit_logs(
        format="json",
        user_id=None,
        team_id=None,
        action=None,
        resource_type=None,
        status=None,
        start_date=None,
        end_date=None,
        search=None,
        current_user=MagicMock(),
    )

    assert await _body(response) == b"[]"
    assert not [call for call in query.calls if call[0] == "filter"]


@pytest.mark.anyio
async def test_detail_returns_log_and_rejects_missing(monkeypatch):
    log = _log()
    get_or_none = AsyncMock(side_effect=[log, None])
    monkeypatch.setattr(audit_logs.AuditLog, "get_or_none", get_or_none)

    response = await audit_logs.get_audit_log(log.id, current_user=MagicMock())
    assert response["data"].id == log.id

    with pytest.raises(BusinessError) as exc:
        await audit_logs.get_audit_log(uuid4(), current_user=MagicMock())

    assert exc.value.code == ResponseCode.NOT_FOUND
    assert exc.value.msg_key == "audit_log_not_found"
