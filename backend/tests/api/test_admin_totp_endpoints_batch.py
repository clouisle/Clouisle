from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import totp as admin_totp
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _CountQuery:
    def __init__(self, count: int):
        self._count = count

    async def count(self):
        return self._count


@pytest.fixture
def admin_totp_client():
    app = FastAPI()
    app.include_router(admin_totp.router, prefix="/api/v1/admin/totp")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
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

    admin = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        roles=[],
    )

    async def fake_current_user():
        return admin

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    app.dependency_overrides[deps.get_current_active_superuser] = fake_current_user
    client = TestClient(app)
    try:
        yield client, admin
    finally:
        app.dependency_overrides.clear()


def test_totp_stats_requires_dashboard_permission(admin_totp_client):
    client, admin = admin_totp_client
    admin.roles = [_Role("admin:user:read")]

    response = client.get("/api/v1/admin/totp/stats")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_totp_stats_reports_rounded_adoption(admin_totp_client):
    client, admin = admin_totp_client
    admin.roles = [_Role("admin:dashboard:access")]

    with patch(
        "app.api.v1.admin.endpoints.totp.User.filter",
        side_effect=[_CountQuery(3), _CountQuery(1)],
    ) as user_filter:
        response = client.get("/api/v1/admin/totp/stats")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "total_users": 3,
        "totp_enabled": 1,
        "adoption_rate": 33.33,
    }
    assert user_filter.call_args_list == [
        call(is_active=True),
        call(is_active=True, totp_enabled=True),
    ]


def test_totp_user_routes_reject_invalid_uuid(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True

    status_response = client.get("/api/v1/admin/totp/users/not-a-uuid/status")
    disable_response = client.post("/api/v1/admin/totp/users/not-a-uuid/disable")

    assert status_response.status_code == 422
    assert disable_response.status_code == 422


def test_totp_status_returns_missing_user(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True

    with patch(
        "app.api.v1.admin.endpoints.totp.User.get_or_none",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(f"/api/v1/admin/totp/users/{uuid4()}/status")

    assert response.status_code == 400
    assert response.json()["msg"]


def test_totp_status_returns_enabled_timestamp(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True
    enabled_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    with patch(
        "app.api.v1.admin.endpoints.totp.User.get_or_none",
        new=AsyncMock(
            return_value=SimpleNamespace(totp_enabled=True, totp_enabled_at=enabled_at)
        ),
    ):
        response = client.get(f"/api/v1/admin/totp/users/{uuid4()}/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "enabled": True,
        "enabled_at": enabled_at.isoformat(),
    }


def test_disable_totp_rejects_user_without_totp(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True

    with patch(
        "app.api.v1.admin.endpoints.totp.User.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace(totp_enabled=False)),
    ):
        response = client.post(f"/api/v1/admin/totp/users/{uuid4()}/disable")

    assert response.status_code == 400
    assert response.json()["msg"]


def test_disable_totp_clears_secrets_and_audits(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True
    user = SimpleNamespace(
        id=uuid4(),
        username="target",
        totp_enabled=True,
        totp_secret="encrypted",
        totp_enabled_at=datetime.now(UTC),
        totp_backup_codes_hash="hashes",
        save=AsyncMock(),
    )

    with (
        patch(
            "app.api.v1.admin.endpoints.totp.User.get_or_none",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.api.v1.admin.endpoints.totp.AuditLogService.log",
            new=AsyncMock(),
        ) as audit_log,
    ):
        response = client.post(f"/api/v1/admin/totp/users/{user.id}/disable")

    assert response.status_code == 200
    assert user.totp_enabled is False
    assert user.totp_secret is None
    assert user.totp_enabled_at is None
    assert user.totp_backup_codes_hash is None
    user.save.assert_awaited_once_with()
    assert audit_log.await_args.kwargs["user"] is admin
    assert audit_log.await_args.kwargs["resource_id"] == user.id
    assert audit_log.await_args.kwargs["metadata"] == {
        "target_user_id": str(user.id),
        "target_username": "target",
    }


def test_disable_totp_propagates_audit_service_error(admin_totp_client):
    client, admin = admin_totp_client
    admin.is_superuser = True
    user = SimpleNamespace(
        id=uuid4(),
        username="target",
        totp_enabled=True,
        totp_secret="encrypted",
        totp_enabled_at=datetime.now(UTC),
        totp_backup_codes_hash="hashes",
        save=AsyncMock(),
    )

    with (
        patch(
            "app.api.v1.admin.endpoints.totp.User.get_or_none",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.api.v1.admin.endpoints.totp.AuditLogService.log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        client.post(f"/api/v1/admin/totp/users/{user.id}/disable")

    user.save.assert_awaited_once_with()
