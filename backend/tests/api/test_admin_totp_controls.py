from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import totp
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _CountQuery:
    def __init__(self, count: int):
        self.count = AsyncMock(return_value=count)


@pytest.fixture
def admin_totp_client():
    app = FastAPI()
    app.include_router(totp.router, prefix="/api/v1/admin/totp")

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

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_totp_stats_requires_dashboard_permission(admin_totp_client):
    client, _ = admin_totp_client

    response = client.get("/api/v1/admin/totp/stats")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_totp_stats_returns_rounded_adoption_rate(admin_totp_client):
    client, user = admin_totp_client
    user.roles = [_Role("admin:dashboard:access")]

    with patch(
        "app.api.v1.admin.endpoints.totp.User.filter",
        side_effect=[_CountQuery(3), _CountQuery(1)],
    ):
        response = client.get("/api/v1/admin/totp/stats")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "total_users": 3,
        "totp_enabled": 1,
        "adoption_rate": 33.33,
    }


def test_totp_status_requires_superuser(admin_totp_client):
    client, user = admin_totp_client
    user.roles = [_Role("admin:dashboard:access")]

    response = client.get(f"/api/v1/admin/totp/users/{uuid4()}/status")

    assert response.status_code == 403
    assert response.json()["code"] == 3001


def test_admin_disable_totp_clears_secrets_and_audits(admin_totp_client):
    client, user = admin_totp_client
    user.is_superuser = True
    target = SimpleNamespace(
        id=uuid4(),
        username="target-user",
        totp_enabled=True,
        totp_secret="secret",
        totp_enabled_at="2026-01-01T00:00:00Z",
        totp_backup_codes_hash="hash",
        save=AsyncMock(),
    )
    audit_log = AsyncMock()

    with (
        patch(
            "app.api.v1.admin.endpoints.totp.User.get_or_none",
            new=AsyncMock(return_value=target),
        ),
        patch(
            "app.api.v1.admin.endpoints.totp.AuditLogService.log",
            audit_log,
        ),
    ):
        response = client.post(f"/api/v1/admin/totp/users/{target.id}/disable")

    assert response.status_code == 200
    assert target.totp_enabled is False
    assert target.totp_secret is None
    assert target.totp_enabled_at is None
    assert target.totp_backup_codes_hash is None
    target.save.assert_awaited_once()
    assert audit_log.await_args.kwargs["action"] == "admin_disable_totp"
    assert audit_log.await_args.kwargs["metadata"] == {
        "target_user_id": str(target.id),
        "target_username": target.username,
    }
