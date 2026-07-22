from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import audit_logs
from app.schemas.response import BusinessError, ResponseCode, error


class Query:
    def __init__(self, rows=None, *, count=0, first=None):
        self.rows = [] if rows is None else rows
        self.count_value = count
        self.first_value = first
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
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
        return self.count_value

    async def first(self):
        return self.first_value

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


class Permission:
    def __init__(self, code):
        self.code = code


class Role:
    def __init__(self, *codes):
        self.permissions = [Permission(code) for code in codes]


@pytest.fixture
def audit_client():
    app = FastAPI()
    app.include_router(audit_logs.router, prefix="/api/v1/admin/audit-logs")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code,
                msg=exc.msg,
                msg_key=exc.msg_key,
                data=exc.data,
                **exc.kwargs,
            ),
        )

    user = SimpleNamespace(is_active=True, is_superuser=False, roles=[])

    async def current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = current_user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()


def test_actions_require_audit_read_permission(audit_client):
    client, user = audit_client
    user.roles = [Role("admin:unrelated")]

    response = client.get("/api/v1/admin/audit-logs/actions")

    assert response.status_code == 403
    assert response.json()["code"] == ResponseCode.PERMISSION_DENIED


def test_actions_return_options_for_authorized_user(audit_client):
    client, user = audit_client
    user.roles = [Role("audit:read")]

    response = client.get("/api/v1/admin/audit-logs/actions")

    assert response.status_code == 200
    assert response.json()["data"][0]["value"] == "login_success"


@pytest.mark.parametrize(
    ("message", "translated", "safe", "expected"),
    [
        (None, False, False, None),
        ("known_key", True, False, "translated"),
        ("safe detail", False, True, "safe detail"),
        ("secret detail", False, False, "unknown"),
    ],
)
def test_serialize_audit_error_hides_unsafe_messages(
    monkeypatch, message, translated, safe, expected
):
    monkeypatch.setattr(audit_logs, "has_translation", lambda value: translated)
    monkeypatch.setattr(audit_logs, "is_safe_user_visible_error", lambda value: safe)
    monkeypatch.setattr(
        audit_logs,
        "t",
        lambda key: "translated" if key == "known_key" else "unknown",
    )

    assert audit_logs.serialize_audit_error(message) == expected


@pytest.mark.anyio
async def test_list_audit_logs_applies_filters_and_pagination(monkeypatch):
    log = SimpleNamespace(id=uuid4())
    query = Query([log], count=21)
    monkeypatch.setattr(audit_logs.AuditLog, "all", lambda: query)
    monkeypatch.setattr(
        audit_logs, "serialize_audit_log", lambda value: {"id": value.id}
    )

    result = await audit_logs.list_audit_logs(
        user_id=uuid4(),
        team_id=uuid4(),
        action=["login_failed"],
        resource_type="user",
        resource_id=uuid4(),
        status=["failed"],
        start_date="2026-01-01",
        end_date="2026-01-31",
        search="127.0.0.1",
        page=2,
        page_size=20,
        current_user=object(),
    )

    assert result["data"]["items"] == [{"id": log.id}]
    assert result["data"]["total_pages"] == 2
    assert [call[0] for call in query.calls] == [
        "filter",
        "filter",
        "filter",
        "filter",
        "filter",
        "filter",
        "filter",
        "filter",
        "filter",
        "order_by",
        "offset",
        "limit",
    ]
    assert query.calls[-2][1] == (20,)


@pytest.mark.anyio
async def test_get_audit_log_rejects_missing_record(monkeypatch):
    monkeypatch.setattr(
        audit_logs.AuditLog, "get_or_none", AsyncMock(return_value=None)
    )

    with pytest.raises(BusinessError) as exc:
        await audit_logs.get_audit_log(uuid4(), current_user=object())

    assert exc.value.code == ResponseCode.NOT_FOUND


@pytest.mark.anyio
async def test_retention_stats_use_setting_and_oldest_log(monkeypatch):
    oldest = SimpleNamespace(created_at=datetime(2025, 1, 2, tzinfo=UTC))
    all_queries = iter([Query(count=8), Query(first=oldest)])
    monkeypatch.setattr(audit_logs.AuditLog, "all", lambda: next(all_queries))
    monkeypatch.setattr(audit_logs.AuditLog, "filter", lambda **kwargs: Query(count=3))
    setting = AsyncMock(return_value=30)
    monkeypatch.setattr(audit_logs.SiteSetting, "get_value", setting)

    result = await audit_logs.get_retention_stats(current_user=object())

    assert result["data"].total_logs == 8
    assert result["data"].logs_to_archive == 3
    assert result["data"].oldest_log_date == oldest.created_at.isoformat()
    setting.assert_awaited_once_with("audit_log_retention_days", 365)


@pytest.mark.anyio
@pytest.mark.parametrize("format", ["csv", "json"])
async def test_export_audit_logs_supports_csv_and_json(monkeypatch, format):
    log = SimpleNamespace(
        id=uuid4(),
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        username="admin",
        action="login_success",
        resource_type="session",
        resource_name=None,
        operation="login",
        status="success",
        ip_address="127.0.0.1",
        error_message=None,
    )
    query = Query([log])
    monkeypatch.setattr(audit_logs.AuditLog, "all", lambda: query)
    serialized = SimpleNamespace(model_dump=lambda **kwargs: {"action": log.action})
    monkeypatch.setattr(audit_logs, "serialize_audit_log", lambda value: serialized)

    response = await audit_logs.export_audit_logs(
        format=format,
        user_id=None,
        team_id=None,
        action=None,
        resource_type=None,
        status=None,
        start_date=None,
        end_date=None,
        search=None,
        current_user=object(),
    )
    chunks = [chunk async for chunk in response.body_iterator]
    body = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )

    assert (
        response.media_type
        == f"{'text/csv' if format == 'csv' else 'application/json'}"
    )
    assert "login_success" in body
    assert query.calls[-1] == ("limit", (10000,), {})
