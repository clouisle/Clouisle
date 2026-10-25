from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from tortoise.context import TortoiseContext

from app.api import deps
from app.api.v1.admin.endpoints import deliveries
from app.schemas.response import BusinessError, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(deliveries.router, prefix="/api/v1/admin/deliveries")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code, msg=exc.msg, msg_key=exc.msg_key, data=exc.data
            ),
        )

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])
    app.dependency_overrides[deps.get_current_active_user] = lambda: user
    try:
        yield TestClient(app), user
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


def test_delivery_log_requires_integration_settings_permission(client):
    http, user = client
    user.roles = [_Role("admin:dashboard:access")]
    response = http.get("/api/v1/admin/deliveries")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delivery_log_multi_filters_use_sqlite_and_hide_content(client, database):
    from app.models.integration_delivery import IntegrationDelivery

    http, user = client
    user.roles = [_Role("admin:integrations:settings:read")]
    common = dict(receipt_id=uuid4(), event_key="final", sequence=0)
    rows = [
        await IntegrationDelivery.create(
            provider_type="feishu", status="error", **common
        ),
        await IntegrationDelivery.create(
            provider_type="wechat",
            status="unknown",
            **{**common, "receipt_id": uuid4()},
        ),
        await IntegrationDelivery.create(
            provider_type="feishu", status="sent", **{**common, "receipt_id": uuid4()}
        ),
        await IntegrationDelivery.create(
            provider_type="other", status="error", **{**common, "receipt_id": uuid4()}
        ),
    ]
    rows[0].text = "never returned"
    rows[0].payload = {"secret": "never returned"}
    rows[0].media_key = "private-resource"
    rows[0].error_detail = "Original provider failure detail"
    await rows[0].save()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http.app), base_url="http://test"
    ) as api:
        response = await api.get(
            "/api/v1/admin/deliveries",
            params=[
                ("provider_type", "feishu"),
                ("provider_type", "wechat"),
                ("status", "error"),
                ("status", "unknown"),
            ],
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 2
    assert {item["id"] for item in payload["items"]} == {
        str(rows[0].id),
        str(rows[1].id),
    }
    item = next(item for item in payload["items"] if item["id"] == str(rows[0].id))
    assert item["error_detail"] == "Original provider failure detail"
    assert item["has_media_key"] is True
    assert "text" not in item and "payload" not in item and "media_key" not in item


def test_delivery_log_rejects_unknown_provider_and_status(client):
    http, user = client
    user.roles = [_Role("admin:integrations:settings:read")]
    for params in (
        {"provider_type": "slack"},
        {"provider_type": ["feishu", "slack"]},
        {"status": "done"},
        {"status": ["error", "done"]},
        {"limit": 500},
    ):
        assert http.get("/api/v1/admin/deliveries", params=params).status_code == 422
