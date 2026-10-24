"""Authorization and isolation boundaries for the trajectory detail API."""

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
def trajectory_client():
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

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_trajectory_detail_requires_dashboard_permission(trajectory_client):
    client, user = trajectory_client
    user.roles = [_Role("admin:user:read")]
    detail = AsyncMock()
    with patch(
        "app.api.v1.admin.endpoints.observability.service.trajectory_detail",
        new=detail,
    ):
        response = client.get(
            f"/api/v1/admin/observability/runs/agent/{uuid4()}/trajectory/{uuid4()}"
        )
    assert response.status_code == 403
    detail.assert_not_awaited()


def test_trajectory_detail_uses_read_permission_and_returns_payload(
    trajectory_client,
):
    client, user = trajectory_client
    user.roles = [_Role("admin:dashboard:access")]
    run_id = uuid4()
    entry_id = uuid4()
    payload = {
        "id": str(entry_id),
        "kind": "model",
        "input": {"messages": [{"role": "user", "content": "hi"}]},
        "output": {"content": "hello"},
        "partial": False,
        "recorded": True,
    }
    detail = AsyncMock(return_value=payload)
    with patch(
        "app.api.v1.admin.endpoints.observability.service.trajectory_detail",
        new=detail,
    ):
        response = client.get(
            f"/api/v1/admin/observability/runs/agent/{run_id}/trajectory/{entry_id}"
        )
    assert response.status_code == 200
    assert response.json()["data"]["kind"] == "model"
    assert response.json()["data"]["recorded"] is True
    detail.assert_awaited_once_with("agent", run_id, str(entry_id))


def test_missing_or_unrecorded_trajectory_entry_returns_not_found(
    trajectory_client,
):
    client, user = trajectory_client
    user.roles = [_Role("admin:dashboard:access")]
    with patch(
        "app.api.v1.admin.endpoints.observability.service.trajectory_detail",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(
            f"/api/v1/admin/observability/runs/workflow/{uuid4()}/trajectory/{uuid4()}"
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Trajectory entry not found"
