"""Behavioral SQLite tests for the tool OAuth service.

No external network or browser is used: SSRF validation and the OAuth HTTP
client are replaced at the module boundary, while PKCE, state hashing,
one-time flow consumption, token storage, refresh locking/version rules and
discovery shaping run against real Tortoise models.
"""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.core.config import settings
from app.core.timezone import now_utc
from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.tool import CustomToolType, Tool, ToolType, ToolVisibility
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)
from app.models.tool_oauth import (
    ToolOAuthClientAuthMethod,
    ToolOAuthFlow,
    ToolOAuthProvider,
    ToolOAuthProviderKind,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_connection import ToolConnectionCreate
from app.schemas.tool_oauth import (
    HttpOAuth2Config,
    McpOAuthConfig,
    OAuthStartRequest,
    validate_redirect_path,
)
from app.services import tool_oauth as oauth
from app.services.tool_connections import ResolvedConnection, ToolConnectionService

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _user(label: str) -> User:
    user = await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@oauth.test",
        hashed_password="x",
    )
    permission, _ = await Permission.get_or_create(
        code="team:read",
        defaults={
            "id": uuid4(),
            "scope": "team",
            "description": "Read team",
        },
    )
    role, _ = await Role.get_or_create(
        name="oauth_test_reader",
        defaults={"id": uuid4(), "description": "OAuth test reader"},
    )
    await role.permissions.add(permission)
    await user.roles.add(role)
    return await User.get(id=user.id).prefetch_related("roles__permissions")


async def _team(owner: User, *, member: User | None = None) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    if member is not None:
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=member.id, role="member"
        )
    return team


async def _http_tool(
    team: Team,
    admin: User,
    *,
    auth_method: ToolOAuthClientAuthMethod = ToolOAuthClientAuthMethod.NONE,
) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=admin.id,
        name=f"http_{uuid4().hex[:8]}",
        display_name="OAuth HTTP tool",
        description="oauth test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        visibility=ToolVisibility.TEAM,
        http_config={
            "oauth2": {
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "client_id": "client-1",
                "scopes": ["read"],
                "token_endpoint_auth_method": auth_method.value,
            }
        },
        connection_fields=[
            {"name": "oauth_access_token", "secret": True, "required": True}
        ],
    )


async def _mcp_tool(team: Team, admin: User) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=admin.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="OAuth MCP server",
        description="oauth test",
        type=ToolType.MCP,
        visibility=ToolVisibility.TEAM,
        mcp_config={
            "transport": "http",
            "url": "https://mcp.example.test/mcp",
        },
    )


async def _connection(
    *,
    team: Team | None,
    tool: Tool,
    user: User | None,
    scope: ToolConnectionScope,
    config: dict[str, str] | None = None,
) -> ToolConnection:
    encrypted, fields = ToolConnectionService._encrypt_config(config or {})
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id if team else None,
        tool_id=tool.id,
        scope=scope,
        owner_user_id=user.id if user else None,
        name=f"connection_{uuid4().hex[:8]}",
        encrypted_config=encrypted,
        secret_fields=fields,
        secret_version=1,
        status=ToolConnectionStatus.ACTIVE,
    )


def _allow_ssrf(monkeypatch):
    async def allow(url, getaddrinfo=None):
        return url

    monkeypatch.setattr(oauth, "ensure_external_http_url_allowed", allow)
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.test")


def _frontend(monkeypatch, value="https://app.example.test"):
    async def fake_frontend_url():
        return value

    monkeypatch.setattr(oauth, "_frontend_url", fake_frontend_url)


def _id_token(claims: dict) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    )
    return f"eyJhbGciOiJub25lIn0.{payload}.sig"


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


# ---------------------------------------------------------------------------
# Schemas and pure helpers
# ---------------------------------------------------------------------------


async def test_schema_rejects_unsafe_provider_configuration():
    with pytest.raises(ValueError):
        HttpOAuth2Config(
            authorization_endpoint="http://auth.example.test/a",
            token_endpoint="https://auth.example.test/t",
            client_id="c",
        )
    with pytest.raises(ValueError):
        HttpOAuth2Config(
            authorization_endpoint="https://auth.example.test/a",
            token_endpoint="https://auth.example.test/t",
            client_id="c",
            extra_authorization_params={"state": "override"},
        )
    with pytest.raises(ValueError):
        McpOAuthConfig(scopes=["read", "read"])
    assert (
        validate_redirect_path("/app/tools/../connections")
        == "/app/tools/../connections"
    )
    with pytest.raises(ValueError):
        validate_redirect_path("//evil.example/app")
    with pytest.raises(ValueError):
        validate_redirect_path("/other")

    request = OAuthStartRequest(client_secret="super-secret")
    assert "super-secret" not in repr(request)


async def test_pkce_state_and_authorization_url_helpers():
    verifier, challenge = oauth._pkce_pair()
    expected = (
        base64.urlsafe_b64encode(
            __import__("hashlib").sha256(verifier.encode()).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected
    assert 43 <= len(verifier) <= 128
    assert oauth._hash_state("abc") == oauth._hash_state("abc")
    assert oauth._hash_state("abc") != oauth._hash_state("abd")
    merged = oauth._merge_query(
        "https://auth.example.test/authorize?audience=x#frag",
        {"state": "s", "code_challenge": "c"},
    )
    assert "#" not in merged
    assert _query(merged)["state"] == ["s"]
    assert _query(merged)["audience"] == ["x"]


async def test_callback_url_uses_server_public_base(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.test")
    assert (
        oauth._callback_url() == "https://api.example.test/api/v1/tool-oauth/callback"
    )
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "http://10.0.0.5:8000")
    with pytest.raises(BusinessError):
        oauth._callback_url()


# ---------------------------------------------------------------------------
# HTTP provider start
# ---------------------------------------------------------------------------


async def test_http_start_creates_hashed_state_and_pkce(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )

        started = await oauth.ToolOAuthService.start_authorization(
            actor=owner,
            connection_id=connection.id,
            redirect_path="/app/tools",
        )

        query = _query(started.authorization_url)
        assert query["response_type"] == ["code"]
        assert query["client_id"] == ["client-1"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["read"]
        assert query["state"] == [started.state]
        assert query["redirect_uri"] == [
            "https://api.example.test/api/v1/tool-oauth/callback"
        ]
        assert "client_secret" not in query

        flow = await ToolOAuthFlow.filter().first()
        assert flow.state_hash != started.state
        assert flow.redirect_path == "/app/tools"
        assert decrypt_tool_secret(flow.code_verifier_encrypted)
        assert flow.consumed_at is None
        assert flow.expected_secret_version == connection.secret_version
        connection = await ToolConnection.get(id=connection.id)
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED


async def test_personal_user_cannot_set_shared_provider_client_secret(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(
            team, admin, auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC
        )
        team_connection = await _connection(
            team=team, tool=tool, user=None, scope=ToolConnectionScope.TEAM
        )
        personal = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin,
            connection_id=team_connection.id,
            client_secret="admin-secret",
        )
        assert started.authorization_url
        provider = await ToolOAuthProvider.get(tool_id=tool.id)
        assert provider.client_secret_encrypted
        assert "admin-secret" not in provider.client_secret_encrypted
        assert decrypt_tool_secret(provider.client_secret_encrypted) == "admin-secret"

        with pytest.raises(BusinessError) as denied:
            await oauth.ToolOAuthService.start_authorization(
                actor=owner,
                connection_id=personal.id,
                client_secret="user-secret",
            )
        assert denied.value.msg_key in {
            "permission_denied",
            "tool_access_denied",
            "team_admin_required",
        }

        # Starting without a secret reuses the administrator-managed provider.
        allowed = await oauth.ToolOAuthService.start_authorization(
            actor=owner, connection_id=personal.id
        )
        assert allowed.authorization_url
        provider = await ToolOAuthProvider.get(tool_id=tool.id)
        assert decrypt_tool_secret(provider.client_secret_encrypted) == "admin-secret"


# ---------------------------------------------------------------------------
# MCP discovery
# ---------------------------------------------------------------------------


async def test_mcp_discovery_and_dynamic_client_registration(monkeypatch):
    _allow_ssrf(monkeypatch)
    calls: list[tuple[str, dict]] = []

    async def fake_http_json(
        url, *, method, data=None, json_body=None, headers=None, max_bytes=None
    ):
        calls.append((url, {"method": method, "body": json_body, "data": data}))
        if "oauth-protected-resource" in url:
            return {
                "resource": "https://mcp.example.test/mcp",
                "authorization_servers": ["https://as.example.test"],
                "scopes_supported": ["mcp.read"],
            }
        if "oauth-authorization-server" in url:
            return {
                "issuer": "https://as.example.test",
                "authorization_endpoint": "https://as.example.test/authorize",
                "token_endpoint": "https://as.example.test/token",
                "registration_endpoint": "https://as.example.test/register",
                "code_challenge_methods_supported": ["S256"],
            }
        if url == "https://as.example.test/register":
            return {"client_id": "dcr-client", "client_secret": "dcr-secret"}
        raise AssertionError(f"unexpected OAuth URL {url}")

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)

        setup = await oauth.ToolOAuthService._ensure_provider(
            tool=tool,
            kind=ToolOAuthProviderKind.MCP,
            redirect_uri="https://api.example.test/api/v1/tool-oauth/callback",
            client_secret=None,
        )

        provider = setup.provider
        assert provider.authorization_server == "https://as.example.test"
        assert provider.client_id == "dcr-client"
        assert provider.resource == "https://mcp.example.test/mcp"
        assert provider.code_challenge_methods == ["S256"]
        assert decrypt_tool_secret(provider.client_secret_encrypted) == "dcr-secret"
        assert setup.scopes == ("mcp.read",)
        registration = next(
            call for call in calls if call[0] == "https://as.example.test/register"
        )
        assert registration[1]["body"]["redirect_uris"] == [
            "https://api.example.test/api/v1/tool-oauth/callback"
        ]
        assert registration[1]["body"]["token_endpoint_auth_method"] == "none"


async def test_mcp_without_registration_endpoint_fails_explicitly(monkeypatch):
    _allow_ssrf(monkeypatch)

    async def fake_http_json(url, **kwargs):
        if "oauth-protected-resource" in url:
            return {
                "authorization_servers": ["https://as.example.test"],
            }
        if "oauth-authorization-server" in url:
            return {
                "issuer": "https://as.example.test",
                "authorization_endpoint": "https://as.example.test/authorize",
                "token_endpoint": "https://as.example.test/token",
                "code_challenge_methods_supported": ["S256"],
            }
        raise AssertionError(url)

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)

        with pytest.raises(BusinessError) as error:
            await oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert error.value.msg_key == "tool_oauth_client_registration_required"


async def test_mcp_rejects_provider_without_s256(monkeypatch):
    _allow_ssrf(monkeypatch)

    async def fake_http_json(url, **kwargs):
        if "oauth-protected-resource" in url:
            return {"authorization_servers": ["https://as.example.test"]}
        return {
            "issuer": "https://as.example.test",
            "authorization_endpoint": "https://as.example.test/authorize",
            "token_endpoint": "https://as.example.test/token",
            "code_challenge_methods_supported": ["plain"],
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)

        with pytest.raises(BusinessError) as error:
            await oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert error.value.msg_key == "tool_oauth_pkce_unsupported"


# ---------------------------------------------------------------------------
# Callback exchange
# ---------------------------------------------------------------------------


async def test_callback_exchanges_once_and_stores_encrypted_tokens(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    calls: list[dict] = []

    async def fake_http_json(
        url, *, method, data=None, json_body=None, headers=None, max_bytes=None
    ):
        calls.append({"url": url, "method": method, "data": data, "headers": headers})
        return {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "token_type": "Bearer",
            "expires_in": 300,
            "scope": "read",
            "id_token": _id_token({"sub": "external-1", "email": "user@example.test"}),
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )
        started = await oauth.ToolOAuthService.start_authorization(
            actor=owner,
            connection_id=connection.id,
            redirect_path="/settings/connections",
        )

        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="auth-code"
        )

        assert redirect.startswith("https://app.example.test/settings/connections?")
        assert _query(redirect)["oauth"] == ["success"]
        assert _query(redirect)["connection_id"] == [str(connection.id)]
        assert len(calls) == 1
        token_call = calls[0]
        assert token_call["url"] == "https://auth.example.test/token"
        assert token_call["data"]["grant_type"] == "authorization_code"
        assert token_call["data"]["code"] == "auth-code"
        assert token_call["data"]["code_verifier"]
        assert "refresh_token" not in token_call["data"]

        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert config["oauth_access_token"] == "access-1"
        assert config["oauth_refresh_token"] == "refresh-1"
        assert config["oauth_scope"] == "read"
        assert config["oauth_token_type"] == "Bearer"
        assert config["oauth_account_subject"] == "external-1"
        assert connection.account_label == "user@example.test"
        assert connection.secret_version == 2
        assert connection.status == ToolConnectionStatus.ACTIVE

        replay = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="auth-code"
        )
        assert _query(replay)["error"] == ["oauth_state_invalid"]
        assert len(calls) == 1


async def test_callback_provider_error_and_version_conflict(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    calls: list[str] = []

    async def fake_http_json(
        url, *, method, data=None, json_body=None, headers=None, max_bytes=None
    ):
        calls.append(url)
        return {"access_token": "new", "expires_in": 300, "scope": "read"}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )
        first = await oauth.ToolOAuthService.start_authorization(
            actor=owner, connection_id=connection.id
        )
        provider_error = await oauth.ToolOAuthService.handle_callback(
            state=first.state, code=None, error="access_denied"
        )
        assert _query(provider_error)["error"] == ["oauth_provider_error"]
        assert calls == []

        second = await oauth.ToolOAuthService.start_authorization(
            actor=owner, connection_id=connection.id
        )
        await ToolConnection.filter(id=connection.id).update(secret_version=99)
        conflict = await oauth.ToolOAuthService.handle_callback(
            state=second.state, code="code"
        )
        assert _query(conflict)["error"] == ["oauth_version_conflict"]
        assert calls == []


async def test_callback_rejects_scope_escalation_and_bad_redirect(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)

    async def fake_http_json(url, **kwargs):
        return {
            "access_token": "new",
            "expires_in": 300,
            "scope": "read write",
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )
        started = await oauth.ToolOAuthService.start_authorization(
            actor=owner, connection_id=connection.id
        )
        await ToolOAuthFlow.filter().update(redirect_path="https://evil.example/x")

        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )

        query = _query(redirect)
        assert query["error"] == ["oauth_scope_escalation"]
        assert redirect.startswith("https://app.example.test/app?")
        connection = await ToolConnection.get(id=connection.id)
        assert "oauth_access_token" not in ToolConnectionService._decrypt_config(
            connection
        )
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED


async def test_expired_flow_is_consumed_and_rejected(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    monkeypatch.setattr(
        oauth.ToolOAuthService,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network")),
    )
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
        )
        started = await oauth.ToolOAuthService.start_authorization(
            actor=owner, connection_id=connection.id
        )
        await ToolOAuthFlow.filter().update(expires_at=now_utc() - timedelta(seconds=1))

        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )

        assert _query(redirect)["error"] == ["oauth_expired"]
        flow = await ToolOAuthFlow.filter().first()
        assert flow.consumed_at is not None


# ---------------------------------------------------------------------------
# Token request validation
# ---------------------------------------------------------------------------


async def test_client_secret_basic_and_post_are_not_put_in_the_body(monkeypatch):
    _allow_ssrf(monkeypatch)
    captured: list[dict] = []

    async def fake_http_json(
        url, *, method, data=None, json_body=None, headers=None, max_bytes=None
    ):
        captured.append({"data": dict(data or {}), "headers": dict(headers or {})})
        return {"access_token": "token", "expires_in": 60}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        basic_provider = ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            authorization_server="https://as.example.test",
            authorization_endpoint="https://as.example.test/authorize",
            token_endpoint="https://as.example.test/token",
            client_id="client-1",
            client_secret_encrypted=encrypt_tool_secret("secret-1"),
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC,
        )
        await basic_provider.save()
        await oauth.ToolOAuthService._request_token(
            basic_provider,
            {
                "grant_type": "refresh_token",
                "refresh_token": "r",
                "client_id": "client-1",
            },
        )
        assert captured[-1]["headers"]["Authorization"].startswith("Basic ")
        assert "client_secret" not in captured[-1]["data"]

        post_provider = ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            authorization_server="https://post.example.test",
            authorization_endpoint="https://post.example.test/authorize",
            token_endpoint="https://post.example.test/token",
            client_id="client-2",
            client_secret_encrypted=encrypt_tool_secret("secret-2"),
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_POST,
        )
        await post_provider.save()
        await oauth.ToolOAuthService._request_token(
            post_provider,
            {
                "grant_type": "refresh_token",
                "refresh_token": "r",
                "client_id": "client-2",
            },
        )
        assert captured[-1]["data"]["client_secret"] == "secret-2"


async def test_token_response_rejects_invalid_values():
    with pytest.raises(oauth._OAuthEndpointError):
        oauth.ToolOAuthService._parse_token_response({"expires_in": 60})
    with pytest.raises(oauth._OAuthEndpointError):
        oauth.ToolOAuthService._parse_token_response(
            {"access_token": "a", "expires_in": 10**12}
        )
    with pytest.raises(oauth._OAuthEndpointError):
        oauth.ToolOAuthService._parse_token_response({"error": "invalid_grant"})
    with pytest.raises(oauth._OAuthEndpointError) as unsupported:
        oauth.ToolOAuthService._parse_token_response(
            {"access_token": "a", "token_type": "DPoP", "expires_in": 60}
        )
    assert unsupported.value.error == "unsupported_token_type"


@pytest.mark.parametrize("seconds", [604801, 15552000, 31536000])
async def test_token_response_accepts_long_lived_provider_tokens(seconds):
    tokens = oauth.ToolOAuthService._parse_token_response(
        {
            "access_token": "provider-token",
            "token_type": "bearer",
            "expires_in": seconds,
        }
    )
    assert tokens.expires_in == seconds
    assert tokens.access_token == "provider-token"


# ---------------------------------------------------------------------------
# Refresh and binding rules
# ---------------------------------------------------------------------------


def _resolved(
    connection: ToolConnection, team_id, user_id, tool_id
) -> ResolvedConnection:
    return ResolvedConnection(
        connection_id=connection.id,
        team_id=team_id,
        scope=ToolConnectionScope.USER,
        owner_user_id=user_id,
        effective_user_id=user_id,
        tool_id=tool_id,
        builtin_tool_key=None,
        account_label=None,
        status=ToolConnectionStatus.ACTIVE,
        secret_version=connection.secret_version,
        secrets={},
    )


async def _seed_refresh_connection(
    *,
    team,
    tool,
    owner,
    access_token: str = "old-access",
    refresh_token: str | None = "refresh-old",
    expires_in: int = -10,
    subject: str | None = "subject-old",
    provider: ToolOAuthProvider,
) -> ToolConnection:
    config = {
        "oauth_access_token": access_token,
        "oauth_expires_at": (now_utc() + timedelta(seconds=expires_in)).isoformat(),
        "oauth_scope": "read",
        "oauth_provider_id": str(provider.id),
    }
    if refresh_token:
        config["oauth_refresh_token"] = refresh_token
    if subject:
        config["oauth_account_subject"] = subject
    encrypted, fields = ToolConnectionService._encrypt_config(config)
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id,
        tool_id=tool.id,
        scope=ToolConnectionScope.USER,
        owner_user_id=owner.id,
        name=f"refresh_{uuid4().hex[:8]}",
        encrypted_config=encrypted,
        secret_fields=fields,
        secret_version=1,
        status=ToolConnectionStatus.ACTIVE,
    )


async def _provider_for(tool: Tool) -> ToolOAuthProvider:
    return await ToolOAuthProvider.create(
        id=uuid4(),
        tool_id=tool.id,
        provider_kind=ToolOAuthProviderKind.HTTP,
        authorization_server="https://as.example.test",
        issuer="https://as.example.test",
        authorization_endpoint="https://as.example.test/authorize",
        token_endpoint="https://as.example.test/token",
        client_id="client-1",
        token_endpoint_auth_method=ToolOAuthClientAuthMethod.NONE,
        scopes=["read"],
    )


async def test_refresh_rotates_tokens_without_bumping_secret_version(monkeypatch):
    _allow_ssrf(monkeypatch)
    calls: list[dict] = []

    async def fake_http_json(
        url, *, method, data=None, json_body=None, headers=None, max_bytes=None
    ):
        calls.append(dict(data or {}))
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 900,
            "scope": "read",
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        token = await oauth.ToolOAuthService.get_access_token(resolved)
        header = await oauth.ToolOAuthService.get_authorization_header(resolved)

        assert token == "new-access"
        assert header == "Bearer new-access"
        assert calls[0]["grant_type"] == "refresh_token"
        assert calls[0]["refresh_token"] == "refresh-old"
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert config["oauth_access_token"] == "new-access"
        assert config["oauth_refresh_token"] == "new-refresh"
        assert config["oauth_scope"] == "read"
        assert connection.secret_version == 1
        assert connection.status == ToolConnectionStatus.ACTIVE


async def test_refresh_invalid_grant_marks_reauth_required(monkeypatch):
    _allow_ssrf(monkeypatch)

    async def fake_http_json(url, **kwargs):
        raise oauth._OAuthEndpointError("invalid_grant", status=400)

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        with pytest.raises(BusinessError) as error:
            await oauth.ToolOAuthService.get_access_token(resolved)

        assert error.value.code == ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED
        connection = await ToolConnection.get(id=connection.id)
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED


async def test_refresh_scope_escalation_fails_without_storing(monkeypatch):
    _allow_ssrf(monkeypatch)

    async def fake_http_json(url, **kwargs):
        return {
            "access_token": "escalated",
            "expires_in": 300,
            "scope": "read write",
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        with pytest.raises(BusinessError) as error:
            await oauth.ToolOAuthService.get_access_token(resolved)

        assert error.value.code == ResponseCode.TOOL_OAUTH_SCOPE_ESCALATION
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert config["oauth_access_token"] == "old-access"
        assert config["oauth_refresh_token"] == "refresh-old"


async def test_refresh_subject_change_bumps_secret_version(monkeypatch):
    _allow_ssrf(monkeypatch)

    async def fake_http_json(url, **kwargs):
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 300,
            "scope": "read",
            "id_token": _id_token(
                {"sub": "subject-new", "preferred_username": "new-user"}
            ),
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        await oauth.ToolOAuthService.get_access_token(resolved)

        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert connection.secret_version == 2
        assert config["oauth_account_subject"] == "subject-new"
        assert connection.account_label == "new-user"


async def test_refresh_requires_matching_binding_version(monkeypatch):
    _allow_ssrf(monkeypatch)
    monkeypatch.setattr(
        oauth.ToolOAuthService,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network")),
    )
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)
        await ToolConnection.filter(id=connection.id).update(secret_version=5)

        with pytest.raises(BusinessError) as error:
            await oauth.ToolOAuthService.get_access_token(resolved)

        assert error.value.msg_key == "tool_oauth_version_conflict"


async def test_valid_access_token_skips_network(monkeypatch):
    _allow_ssrf(monkeypatch)
    calls = {"count": 0}

    async def fake_http_json(url, **kwargs):
        calls["count"] += 1
        return {"access_token": "unused", "expires_in": 300}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            access_token="valid-access",
            expires_in=300,
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        token = await oauth.ToolOAuthService.get_access_token(resolved)

        assert token == "valid-access"
        assert calls["count"] == 0


async def test_status_is_secret_free(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )

        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=connection.id
        )

        payload = status.model_dump(mode="json")
        assert payload["authorized"] is True
        assert payload["needs_reauth"] is False
        assert payload["scopes"] == ["read"]
        assert "oauth_access_token" not in payload
        assert "old-access" not in json.dumps(payload)


# ---------------------------------------------------------------------------
# WWW-Authenticate discovery, revocation, cleanup
# ---------------------------------------------------------------------------


async def test_www_authenticate_parser_only_accepts_bearer_metadata():
    assert (
        oauth._bearer_resource_metadata(
            'Basic realm="x", Bearer resource_metadata="https://as.example.test/meta", scope="read"'
        )
        == "https://as.example.test/meta"
    )
    assert oauth._bearer_resource_metadata('Basic realm="x"') is None
    assert (
        oauth._bearer_resource_metadata('Bearer resource_metadata="not-a-url"')
        == "not-a-url"
    )
    assert oauth._bearer_resource_metadata(None) is None


async def test_in_process_oauth_http_smoke_via_mock_transport(monkeypatch):
    """Full MCP discovery + PKCE callback + revocation over httpx MockTransport."""
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    calls: list[tuple[str, str]] = []
    metadata_url = "https://as.example.test/.well-known/oauth-protected-resource"

    def handler(request):
        import httpx as http

        url = str(request.url)
        calls.append((request.method, url))
        if url == "https://mcp.example.test/mcp":
            return http.Response(
                401,
                headers={
                    "WWW-Authenticate": (f'Bearer resource_metadata="{metadata_url}"')
                },
                content=b"",
            )
        if url == metadata_url:
            return http.Response(
                200,
                json={
                    "resource": "https://mcp.example.test/mcp",
                    "authorization_servers": ["https://as.example.test"],
                    "scopes_supported": ["mcp.read"],
                },
            )
        if url.endswith("/.well-known/oauth-authorization-server"):
            return http.Response(
                200,
                json={
                    "issuer": "https://as.example.test",
                    "authorization_endpoint": "https://as.example.test/authorize",
                    "token_endpoint": "https://as.example.test/token",
                    "registration_endpoint": "https://as.example.test/register",
                    "revocation_endpoint": "https://as.example.test/revoke",
                    "code_challenge_methods_supported": ["S256"],
                },
            )
        if url == "https://as.example.test/register":
            return http.Response(
                200,
                json={
                    "client_id": "dcr-client",
                    "client_secret": "dcr-secret",
                    "token_endpoint_auth_method": "client_secret_basic",
                },
            )
        if url == "https://as.example.test/token":
            return http.Response(
                200,
                json={
                    "access_token": "mcp-access",
                    "refresh_token": "mcp-refresh",
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "scope": "mcp.read",
                    "id_token": _id_token(
                        {"sub": "mcp-subject", "email": "mcp@example.test"}
                    ),
                },
            )
        if url == "https://as.example.test/revoke":
            return http.Response(200, json={})
        raise AssertionError(f"unexpected request {request.method} {url}")

    real_client = __import__("httpx").AsyncClient

    def client_factory(*args, **kwargs):
        import httpx as http

        return real_client(
            transport=http.MockTransport(handler),
            follow_redirects=False,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            scope=ToolConnectionScope.USER,
        )

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=connection.id
        )
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="mcp-code"
        )
        assert _query(redirect)["oauth"] == ["success"]
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert config["oauth_access_token"] == "mcp-access"
        token_calls = [url for _, url in calls if url.endswith("/token")]
        assert token_calls == ["https://as.example.test/token"]

        disconnected = await oauth.ToolOAuthService.disconnect(
            actor=admin, connection_id=connection.id
        )
        assert disconnected.local_revoked is True
        assert disconnected.remote_revocation == "revoked"
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert "oauth_access_token" not in config
        assert "oauth_refresh_token" not in config
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert any(url.endswith("/revoke") for _, url in calls)


async def test_disconnect_is_local_first_when_remote_unsupported(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )

        result = await oauth.ToolOAuthService.disconnect(
            actor=admin, connection_id=connection.id
        )

        assert result.remote_revocation == "unsupported"
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert "oauth_access_token" not in config
        assert "oauth_refresh_token" not in config
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert connection.secret_version == 2


async def test_disconnect_remote_failure_never_blocks_local(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        provider.revocation_endpoint = "https://as.example.test/revoke"
        await provider.save()
        connection = await _seed_refresh_connection(
            team=team, tool=tool, owner=admin, provider=provider
        )

        async def failing_revoke(*args, **kwargs):
            return "failed"

        monkeypatch.setattr(
            oauth.ToolOAuthService, "_revoke_remote_token", failing_revoke
        )
        result = await oauth.ToolOAuthService.disconnect(
            actor=admin, connection_id=connection.id
        )

        assert result.remote_revocation == "failed"
        connection = await ToolConnection.get(id=connection.id)
        assert "oauth_access_token" not in ToolConnectionService._decrypt_config(
            connection
        )


async def test_cleanup_deletes_only_retained_expired_flows(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            scope=ToolConnectionScope.USER,
        )
        old = now_utc() - oauth.FLOW_RETENTION - timedelta(hours=1)
        expired = await ToolOAuthFlow.create(
            state_hash="a" * 64,
            user_id=admin.id,
            team_id=team.id,
            tool_id=tool.id,
            connection_id=connection.id,
            provider_id=provider.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            redirect_uri="https://api.example.test/callback",
            code_verifier_encrypted=encrypt_tool_secret("verifier"),
            expected_secret_version=1,
            expires_at=old,
        )
        recent = await ToolOAuthFlow.create(
            state_hash="b" * 64,
            user_id=admin.id,
            team_id=team.id,
            tool_id=tool.id,
            connection_id=connection.id,
            provider_id=provider.id,
            provider_kind=ToolOAuthProviderKind.HTTP,
            redirect_uri="https://api.example.test/callback",
            code_verifier_encrypted=encrypt_tool_secret("verifier"),
            expected_secret_version=1,
            expires_at=now_utc() + timedelta(minutes=5),
        )

        deleted = await oauth.ToolOAuthService.cleanup_expired_flows(limit=10)

        assert deleted == 1
        assert not await ToolOAuthFlow.filter(id=expired.id).exists()
        assert await ToolOAuthFlow.filter(id=recent.id).exists()


# ---------------------------------------------------------------------------
# HTTP provider connection creation contract
# ---------------------------------------------------------------------------


async def test_connection_creation_still_accepts_oauth_credential_fields():
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        connection = await ToolConnectionService.create_connection(
            actor=admin,
            payload=ToolConnectionCreate(
                team_id=team.id,
                scope=ToolConnectionScope.USER,
                name="oauth connection",
                tool_id=tool.id,
                config={
                    "oauth_access_token": "seed-token",
                    "oauth_expires_at": now_utc().isoformat(),
                },
            ),
        )

        assert connection.secret_fields == [
            "oauth_access_token",
            "oauth_expires_at",
        ]
        assert "seed-token" not in json.dumps(connection.model_dump(mode="json"))
