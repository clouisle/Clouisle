from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import observability
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


@pytest.fixture
def admin_observability_client():
    app = FastAPI()
    app.include_router(observability.router, prefix="/api/v1/admin/observability")

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

    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        roles=[],
    )

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_observability_requires_dashboard_permission(admin_observability_client):
    client, user = admin_observability_client
    user.roles = [_Role("admin:user:read")]

    response = client.get("/api/v1/admin/observability/overview")

    assert response.status_code == 403
    assert response.json()["code"] == 3000


def test_observability_allows_dashboard_permission(admin_observability_client):
    client, user = admin_observability_client
    user.roles = [_Role("admin:dashboard:access")]

    with patch(
        "app.api.v1.admin.endpoints.observability.admin_observability.cached_payload",
        new=AsyncMock(return_value={"ok": True}),
    ):
        response = client.get("/api/v1/admin/observability/overview")

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}


def test_observability_allows_superuser(admin_observability_client):
    client, user = admin_observability_client
    user.is_superuser = True

    with patch(
        "app.api.v1.admin.endpoints.observability.admin_observability.cached_payload",
        new=AsyncMock(return_value={"ok": True}),
    ):
        response = client.get("/api/v1/admin/observability/system/health")

    assert response.status_code == 200
    assert response.json()["data"] == {"ok": True}


def test_observability_endpoint_shapes(admin_observability_client):
    client, user = admin_observability_client
    user.roles = [_Role("admin:dashboard:access")]

    endpoints = [
        "/overview",
        "/agents",
        f"/agent/{uuid4()}",
        "/workflows",
        f"/workflow/{uuid4()}",
        "/timeouts",
        "/throughput",
        "/tokens",
        "/system/health",
        "/system/trend",
        "/system/slow-queries",
        "/system/workers",
    ]

    with patch(
        "app.api.v1.admin.endpoints.observability.admin_observability.cached_payload",
        new=AsyncMock(return_value={"items": []}),
    ):
        for endpoint in endpoints:
            response = client.get(f"/api/v1/admin/observability{endpoint}")
            assert response.status_code == 200
            assert response.json()["data"] == {"items": []}
