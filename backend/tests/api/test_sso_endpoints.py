from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from tortoise import Tortoise

from app.api import deps
from app.api.v1.endpoints import sso
from app.core.timezone import now_utc
from app.models.integration import Integration
from app.models.sso_session import SSOSession
from app.models.user import User
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.response import BusinessError, error


@pytest_asyncio.fixture
async def sso_app(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    actor = await User.create(
        username="actor", email="actor@example.com", hashed_password="password"
    )
    provider = await Integration.create(
        name="feishu",
        provider_type="feishu",
        display_name="Feishu",
        enabled_capabilities=["user_login"],
    )
    app = FastAPI()
    app.include_router(sso.router, prefix="/sso")
    app.dependency_overrides[deps.get_current_active_user] = lambda: actor

    @app.exception_handler(BusinessError)
    async def handle_business_error(_request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content=error(code=exc.code, msg_key=exc.msg_key),
        )

    async def setting(key, default=None):
        return {"sso_enabled": True, "site_url": "https://frontend.example"}.get(
            key, default
        )

    monkeypatch.setattr(sso.SiteSetting, "get_value", setting)
    monkeypatch.setattr(sso, "_backend_url", lambda _: "https://backend.example")
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        ) as client:
            yield SimpleNamespace(client=client, actor=actor, provider=provider)
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_start_link_rejects_existing_link(sso_app):
    await UserSSOConnection.create(
        user=sso_app.actor,
        integration=sso_app.provider,
        provider_user_id="already-linked",
    )
    response = await sso_app.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )

    assert response.status_code == 400
    assert response.json()["code"] != 0
    assert await SSOSession.all().count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", ["not-a-tuple", (None, "verifier", "nonce")])
async def test_start_link_rejects_malformed_provider_authorization(
    sso_app, monkeypatch, authorization
):
    provider_client = SimpleNamespace(
        get_authorization_url=AsyncMock(return_value=authorization)
    )
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", lambda _: provider_client
    )

    response = await sso_app.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )

    assert response.status_code == 400
    assert response.json()["code"] != 0
    assert await SSOSession.all().count() == 0


@pytest.mark.asyncio
async def test_disabled_feishu_callback_returns_link_error_surface(monkeypatch):
    provider = SimpleNamespace(
        name="feishu", provider_type="feishu", is_enabled=True, enabled_capabilities=[]
    )
    pending = SimpleNamespace(link_user_id="actor")
    monkeypatch.setattr(
        sso.Integration, "get_or_none", AsyncMock(return_value=provider)
    )
    monkeypatch.setattr(sso.SSOSession, "get_or_none", AsyncMock(return_value=pending))
    monkeypatch.setattr(
        sso.SiteSetting,
        "get_value",
        AsyncMock(return_value="https://frontend.example"),
    )

    response = await sso.sso_callback(
        "feishu", SimpleNamespace(query_params={}), state="state"
    )

    assert response.status_code == 303
    assert urlsplit(response.headers["location"]).path == "/sso-link-callback"
    assert parse_qs(urlsplit(response.headers["location"]).query) == {
        "error": ["sso_provider_not_found"]
    }


@pytest.mark.asyncio
async def test_complete_link_rejects_inactive_actor(sso_app):
    state = "inactive-link"
    await SSOSession.create(
        session_id=state,
        integration=sso_app.provider,
        link_user=sso_app.actor,
        link_user_info={"provider_user_id": "subject"},
        expires_at=now_utc() + timedelta(minutes=5),
    )
    sso_app.actor.is_active = False
    await sso_app.actor.save(update_fields=["is_active"])

    response = await sso_app.client.post(
        "/sso/links/complete", json={"session_id": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] != 0
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [{"provider_user_id": ""}])
async def test_complete_link_rejects_invalid_identity(sso_app, identity):
    state = "invalid-identity"
    await SSOSession.create(
        session_id=state,
        integration=sso_app.provider,
        link_user=sso_app.actor,
        link_user_info=identity,
        expires_at=now_utc() + timedelta(minutes=5),
    )

    response = await sso_app.client.post(
        "/sso/links/complete", json={"session_id": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] != 0
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
async def test_complete_link_creates_connection_and_marks_existing_manual_link(sso_app):
    async def stage(state, provider_user_id):
        return await SSOSession.create(
            session_id=state,
            integration=sso_app.provider,
            link_user=sso_app.actor,
            link_user_info={"provider_user_id": provider_user_id, "username": "member"},
            expires_at=now_utc() + timedelta(minutes=5),
        )

    await stage("new", "new-subject")
    response = await sso_app.client.post(
        "/sso/links/complete", json={"session_id": "new"}
    )
    assert response.status_code == 200
    created = await UserSSOConnection.get(provider_user_id="new-subject")
    assert created.self_service_linked is True

    await UserSSOConnection.all().delete()
    manual = await UserSSOConnection.create(
        user=sso_app.actor,
        integration=sso_app.provider,
        provider_user_id="manual-subject",
        self_service_linked=False,
    )
    await stage("manual", "manual-subject")
    response = await sso_app.client.post(
        "/sso/links/complete", json={"session_id": "manual"}
    )
    assert response.status_code == 200
    await manual.refresh_from_db()
    assert manual.self_service_linked is True
