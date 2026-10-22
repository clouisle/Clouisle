"""Self-service Feishu binding preserves the signed-in account and identity owner."""

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
async def channel(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    actor = await User.create(
        username="local-user", email="local@example.com", hashed_password="kept"
    )
    other = await User.create(
        username="other-user", email="other@example.com", hashed_password="other"
    )
    integration = await Integration.create(
        name="feishu",
        provider_type="feishu",
        display_name="Feishu",
        enabled_capabilities=["user_login"],
    )
    identity = {
        "provider_user_id": "union-123",
        "username": "Feishu member",
        "email": "different@example.com",
    }
    provider = SimpleNamespace(
        get_authorization_url=AsyncMock(
            return_value=(
                "https://accounts.feishu.cn/authorize?state=state",
                "verifier",
                "",
            )
        ),
        handle_callback=AsyncMock(return_value=identity),
        map_user_attributes=lambda data: {},
    )
    monkeypatch.setattr(sso.SSOService, "get_provider_instance", lambda _: provider)
    login = AsyncMock(
        side_effect=AssertionError("Binding must never invoke login or email matching")
    )
    monkeypatch.setattr(sso.SSOService, "find_or_create_user", login)
    monkeypatch.setattr(sso.AuditLogService, "log", AsyncMock())
    # Authorization status codes are the subject here; the token blacklist lives
    # in Redis, so stub it rather than requiring a Redis instance.
    monkeypatch.setattr(deps, "is_token_blacklisted", AsyncMock(return_value=False))
    monkeypatch.setattr(sso, "_backend_url", lambda _: "https://api.example")

    async def setting(key, default=None):
        return {"sso_enabled": True, "site_url": "http://frontend"}.get(key, default)

    monkeypatch.setattr(sso.SiteSetting, "get_value", setting)
    app = FastAPI()
    app.include_router(sso.router, prefix="/sso")
    active = {"user": actor}
    app.dependency_overrides[deps.get_current_active_user] = lambda: active["user"]

    @app.exception_handler(BusinessError)
    async def business_error(_request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content=error(code=exc.code, msg_key=exc.msg_key),
        )

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        ) as client:
            yield SimpleNamespace(
                client=client,
                actor=actor,
                other=other,
                integration=integration,
                identity=identity,
                provider=provider,
                active=active,
                login=login,
                app=app,
            )
    finally:
        await Tortoise.close_connections()


async def authorize(channel):
    response = await channel.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )
    assert response.status_code == 200, response.text
    state = response.json()["data"]["session_id"]
    callback = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "realistic-code"}
    )
    assert callback.status_code == 303, callback.text
    assert parse_qs(urlsplit(callback.headers["location"]).query) == {
        "session_id": [state]
    }
    return state


@pytest.mark.asyncio
async def test_binding_reuses_registered_callback_and_keeps_local_account(channel):
    options = await channel.client.get("/sso/links/integrations")
    assert [item["name"] for item in options.json()["data"]] == ["feishu"]
    state = await authorize(channel)
    assert await UserSSOConnection.all().count() == 0
    assert (
        channel.provider.get_authorization_url.await_args.kwargs["redirect_uri"]
        == "https://api.example/api/v1/sso/callback/feishu"
    )
    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )
    assert response.status_code == 200, response.text
    connection = await UserSSOConnection.get(integration=channel.integration)
    assert connection.user_id == channel.actor.id
    assert connection.provider_user_id == "union-123"
    from app.integrations.feishu import FeishuDirectoryUser
    from app.services.feishu_directory import sync_directory_users
    from fastapi import Request

    synced = await sync_directory_users(
        [
            FeishuDirectoryUser(
                "directory-123",
                "open-123",
                "union-123",
                "Remote",
                "remote@example.com",
                None,
            )
        ],
        actor=channel.actor,
        request=Request({"type": "http", "headers": []}),
    )
    assert (synced.created, synced.updated, synced.skipped) == (0, 0, 1)
    from app.services.feishu_agent_preferences import linked_user
    from app.services.feishu_agent_runtime import _resolve_user

    assert await linked_user(channel.integration, channel.actor)
    resolved = await _resolve_user(channel.integration, "union_id", "union-123")
    assert resolved is not None and resolved.id == channel.actor.id
    restored = await User.get(id=channel.actor.id)
    assert (restored.email, restored.hashed_password, restored.auth_source) == (
        "local@example.com",
        "kept",
        "local",
    )
    assert await User.all().count() == 2
    assert not await SSOSession.filter(session_id=state).exists()
    assert (await channel.client.get("/sso/links/integrations")).json()["data"] == []
    assert (
        await channel.client.post("/sso/links/complete", json={"session_id": state})
    ).status_code == 400
    channel.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_another_signed_in_account_cannot_complete_binding(channel):
    state = await authorize(channel)
    channel.active["user"] = channel.other
    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )
    assert response.status_code == 400
    assert await UserSSOConnection.all().count() == 0
    channel.active["user"] = channel.actor
    assert (
        await channel.client.post("/sso/links/complete", json={"session_id": state})
    ).status_code == 200


@pytest.mark.asyncio
async def test_existing_feishu_owner_is_never_reassigned(channel):
    await UserSSOConnection.create(
        user=channel.other,
        integration=channel.integration,
        provider_user_id="union-123",
    )
    state = await authorize(channel)
    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )
    assert response.status_code == 400
    assert response.json()["code"] == 5001
    connection = await UserSSOConnection.get(provider_user_id="union-123")
    assert connection.user_id == channel.other.id
    assert await UserSSOConnection.all().count() == 1


@pytest.mark.asyncio
async def test_expired_and_unverified_sessions_cannot_bind(channel):
    response = await channel.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )
    state = response.json()["data"]["session_id"]
    assert (
        await channel.client.post("/sso/links/complete", json={"session_id": state})
    ).status_code == 400
    await SSOSession.filter(session_id=state).update(
        expires_at=now_utc() - timedelta(seconds=1)
    )
    callback = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "code"}
    )
    assert callback.headers["location"] == (
        "http://frontend/sso-link-callback?error=sso_session_expired"
    )
    channel.provider.handle_callback.assert_not_awaited()
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
async def test_replayed_provider_callback_does_not_overwrite_verified_identity(channel):
    state = await authorize(channel)
    replay = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "other-code"}
    )
    assert "error=sso_session_expired" in replay.headers["location"]
    assert channel.provider.handle_callback.await_count == 1
    assert (await SSOSession.get(session_id=state)).link_user_info[
        "provider_user_id"
    ] == "union-123"


@pytest.mark.asyncio
async def test_disabled_integration_cannot_start_or_complete_binding(channel):
    state = await authorize(channel)
    await Integration.filter(id=channel.integration.id).update(enabled_capabilities=[])
    assert (await channel.client.get("/sso/links/integrations")).json()["data"] == []
    assert (
        await channel.client.post("/sso/links", params={"provider_name": "feishu"})
    ).status_code == 400
    assert (
        await channel.client.post("/sso/links/complete", json={"session_id": state})
    ).status_code == 400
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
async def test_provider_configuration_error_is_a_safe_business_error(channel):
    channel.provider.get_authorization_url.side_effect = ValueError("missing app id")

    response = await channel.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )

    assert response.json()["code"] == 6304
    assert await SSOSession.all().count() == 0


@pytest.mark.asyncio
async def test_disabled_provider_link_callback_returns_binding_surface(channel):
    state = await authorize(channel)
    await Integration.filter(id=channel.integration.id).update(enabled_capabilities=[])

    callback = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "code"}
    )

    assert callback.headers["location"] == (
        "http://frontend/sso-link-callback?error=sso_provider_not_found"
    )
    assert await SSOSession.filter(session_id=state).exists()
    channel.provider.handle_callback.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_authorization_never_falls_back_to_login(channel):
    channel.provider.handle_callback.side_effect = RuntimeError("provider unavailable")
    response = await channel.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )
    state = response.json()["data"]["session_id"]
    callback = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "code"}
    )
    assert (
        callback.headers["location"]
        == "http://frontend/sso-link-callback?error=sso_login_failed"
    )
    assert not await SSOSession.filter(session_id=state).exists()
    assert await UserSSOConnection.all().count() == 0
    channel.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_directory_identity_bound_to_another_account_is_rejected(channel):
    from app.models.feishu_user import FeishuUser

    await FeishuUser.create(user=channel.other, feishu_user_id="directory-123")
    channel.identity["user_id"] = "directory-123"
    state = await authorize(channel)
    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )
    assert response.status_code == 400
    assert response.json()["code"] == 5001
    assert await UserSSOConnection.all().count() == 0
    assert await SSOSession.filter(session_id=state).exists()


@pytest.mark.asyncio
async def test_directory_email_owned_by_another_account_cannot_be_linked(channel):
    channel.identity["email"] = channel.other.email
    state = await authorize(channel)

    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] == 5001
    assert await SSOSession.filter(session_id=state).exists()


@pytest.mark.asyncio
async def test_new_identity_cannot_silently_replace_an_existing_link(channel):
    state = await authorize(channel)
    await UserSSOConnection.create(
        user=channel.actor,
        integration=channel.integration,
        provider_user_id="other-union",
    )
    response = await channel.client.post(
        "/sso/links/complete", json={"session_id": state}
    )
    assert response.status_code == 400
    assert (
        await UserSSOConnection.get(user=channel.actor)
    ).provider_user_id == "other-union"


@pytest.mark.asyncio
async def test_link_endpoints_require_authenticated_actor(channel):
    channel.app.dependency_overrides.clear()
    for method, url in [
        ("GET", "/sso/links/integrations"),
        ("POST", "/sso/links?provider_name=feishu"),
        ("POST", "/sso/links/complete"),
    ]:
        response = await channel.client.request(method, url)
        assert response.status_code in (401, 403)
    assert await SSOSession.all().count() == 0
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
async def test_global_sso_disable_revokes_pending_binding(channel, monkeypatch):
    state = await authorize(channel)

    async def disabled(key, default=None):
        return {"sso_enabled": False, "site_url": "http://frontend"}.get(key, default)

    monkeypatch.setattr(sso.SiteSetting, "get_value", disabled)
    assert (await channel.client.get("/sso/links/integrations")).json()["data"] == []
    assert (
        await channel.client.post("/sso/links", params={"provider_name": "feishu"})
    ).status_code == 400
    assert (
        await channel.client.post("/sso/links/complete", json={"session_id": state})
    ).status_code == 400
    assert await UserSSOConnection.all().count() == 0


@pytest.mark.asyncio
async def test_provider_without_identity_cannot_stage_a_binding(channel):
    channel.identity.pop("provider_user_id")
    response = await channel.client.post(
        "/sso/links", params={"provider_name": "feishu"}
    )
    state = response.json()["data"]["session_id"]
    callback = await channel.client.get(
        "/sso/callback/feishu", params={"state": state, "code": "code"}
    )
    assert (
        callback.headers["location"]
        == "http://frontend/sso-link-callback?error=sso_login_failed"
    )
    assert not await SSOSession.filter(session_id=state).exists()
    assert await UserSSOConnection.all().count() == 0
    channel.login.assert_not_awaited()
