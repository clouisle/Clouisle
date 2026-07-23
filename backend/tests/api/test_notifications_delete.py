from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import notifications
from app.models.notification import NotificationScope
from app.schemas.response import BusinessError, ResponseCode, error


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(notifications.admin_router, prefix="/api/v1/admin/notifications")

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

    return app


@pytest.fixture
def notification_client():
    app = _app()
    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False)

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    with TestClient(app) as client:
        yield client, user


def test_delete_notification_requires_authentication():
    app = _app()

    async def reject_unauthenticated():
        raise BusinessError(status_code=403)

    app.dependency_overrides[deps.get_current_user] = reject_unauthenticated
    with TestClient(app) as client:
        response = client.delete(f"/api/v1/admin/notifications/{uuid4()}")

    assert response.status_code == 403


def test_delete_notification_returns_not_found(notification_client):
    client, _ = notification_client
    query = MagicMock()
    query.first = AsyncMock(return_value=None)

    with patch.object(notifications.Notification, "filter", return_value=query):
        response = client.delete(f"/api/v1/admin/notifications/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == ResponseCode.NOT_FOUND


def test_delete_global_notification_requires_superuser(notification_client):
    client, _ = notification_client
    query = MagicMock()
    query.first = AsyncMock(
        return_value=SimpleNamespace(scope=NotificationScope.GLOBAL)
    )

    with patch.object(notifications.Notification, "filter", return_value=query):
        response = client.delete(f"/api/v1/admin/notifications/{uuid4()}")

    assert response.status_code == 403
    assert response.json()["code"] == ResponseCode.INSUFFICIENT_PRIVILEGES


def test_delete_team_notification_requires_team_id(notification_client):
    client, user = notification_client
    user.is_superuser = True
    query = MagicMock()
    query.first = AsyncMock(
        return_value=SimpleNamespace(scope=NotificationScope.TEAM, team_id=None)
    )

    with patch.object(notifications.Notification, "filter", return_value=query):
        response = client.delete(f"/api/v1/admin/notifications/{uuid4()}")

    assert response.status_code == 400
    assert response.json()["code"] == ResponseCode.BAD_REQUEST


def test_superuser_deletes_global_notification(notification_client):
    client, user = notification_client
    user.is_superuser = True
    notification_id = uuid4()
    notification = SimpleNamespace(
        id=notification_id,
        scope=NotificationScope.GLOBAL,
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=notification)
    query.delete = AsyncMock(return_value=1)

    with (
        patch.object(
            notifications.Notification, "filter", return_value=query
        ) as mocked_filter,
        patch.object(
            notifications, "create_notification_audit", new=AsyncMock()
        ) as mocked_audit,
    ):
        response = client.delete(f"/api/v1/admin/notifications/{notification_id}")

    assert response.status_code == 200
    assert response.json()["data"] == {"id": str(notification_id)}
    mocked_audit.assert_awaited_once()
    mocked_filter.assert_any_call(id=notification_id)
    query.delete.assert_awaited_once_with()
