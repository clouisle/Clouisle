"""Permission, status and identity edge paths for the tool OAuth service.

Complements ``test_tool_oauth.py``. Every scenario is deterministic: external
HTTP is either denied explicitly or served by an in-process ``MockTransport``;
token storage, flow consumption, provider rotation and authorization checks run
against real Tortoise models.
"""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
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


async def _user(label: str, *, superuser: bool = False) -> User:
    user = await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@oauth.test",
        hashed_password="x",
        is_superuser=superuser,
    )
    permission, _ = await Permission.get_or_create(
        code="team:read",
        defaults={"id": uuid4(), "scope": "team", "description": "Read team"},
    )
    role, _ = await Role.get_or_create(
        name="oauth_paths_reader",
        defaults={"id": uuid4(), "description": "OAuth path reader"},
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


async def _mcp_tool(
    team: Team, admin: User, *, oauth_config: dict | None = None
) -> Tool:
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
            "oauth": oauth_config or {},
        },
    )


async def _connection(
    *,
    team: Team | None,
    tool: Tool | None = None,
    builtin_tool_key: str | None = None,
    user: User | None = None,
    scope: ToolConnectionScope,
    config: dict[str, str] | None = None,
    status: ToolConnectionStatus = ToolConnectionStatus.ACTIVE,
    secret_version: int = 1,
    account_label: str | None = None,
) -> ToolConnection:
    encrypted, fields = ToolConnectionService._encrypt_config(config or {})
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id if team else None,
        tool_id=tool.id if tool else None,
        builtin_tool_key=builtin_tool_key,
        scope=scope,
        owner_user_id=user.id if user else None,
        name=f"connection_{uuid4().hex[:8]}",
        account_label=account_label,
        encrypted_config=encrypted,
        secret_fields=fields,
        secret_version=secret_version,
        status=status,
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


async def _provider_for(tool: Tool, **overrides) -> ToolOAuthProvider:
    values = {
        "id": uuid4(),
        "tool_id": tool.id,
        "provider_kind": ToolOAuthProviderKind.HTTP,
        "authorization_server": "https://as.example.test",
        "issuer": "https://as.example.test",
        "authorization_endpoint": "https://as.example.test/authorize",
        "token_endpoint": "https://as.example.test/token",
        "client_id": "client-1",
        "token_endpoint_auth_method": ToolOAuthClientAuthMethod.NONE,
        "scopes": ["read"],
    }
    values.update(overrides)
    return await ToolOAuthProvider.create(**values)


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


async def _seed_tokens(
    *,
    team: Team,
    tool: Tool,
    owner: User,
    provider: ToolOAuthProvider,
    access: str = "old-access",
    refresh: str | None = "refresh-old",
    expires_in: int = -10,
    token_type: str = "Bearer",
    scope: str | None = "read",
    subject: str | None = "subject-old",
    status: ToolConnectionStatus = ToolConnectionStatus.ACTIVE,
) -> ToolConnection:
    config = {
        "oauth_access_token": access,
        "oauth_expires_at": (now_utc() + timedelta(seconds=expires_in)).isoformat(),
        "oauth_token_type": token_type,
        "oauth_provider_id": str(provider.id),
    }
    if refresh:
        config["oauth_refresh_token"] = refresh
    if scope is not None:
        config["oauth_scope"] = scope
    if subject:
        config["oauth_account_subject"] = subject
    return await _connection(
        team=team,
        tool=tool,
        user=owner,
        scope=ToolConnectionScope.USER,
        config=config,
        status=status,
    )


async def _expect(code: ResponseCode, scenario) -> BusinessError:
    with pytest.raises(BusinessError) as captured:
        await scenario()
    assert int(captured.value.code) == int(code), captured.value.msg_key
    return captured.value


# ---------------------------------------------------------------------------
# Pure security helpers
# ---------------------------------------------------------------------------


async def test_https_endpoint_metadata_and_claim_helpers():
    with pytest.raises(oauth._OAuthEndpointError) as insecure:
        oauth._require_https_endpoint("http://auth.example.test/a")
    assert insecure.value.error == "invalid_endpoint"
    with pytest.raises(oauth._OAuthEndpointError):
        oauth._require_https_endpoint("https://user:pass@auth.example.test/a")
    with pytest.raises(oauth._OAuthEndpointError):
        oauth._require_https_endpoint("https://auth.example.test/" + "a" * 2000)
    assert (
        oauth._require_https_endpoint("https://auth.example.test/a")
        == "https://auth.example.test/a"
    )

    scopes = ["read", 5, "x" * 300] + [f"s{index}" for index in range(60)]
    sanitized = oauth._sanitize_metadata(
        {
            "issuer": "https://as.example.test",
            "authorization_endpoint": "x" * 2001,
            "scopes_supported": scopes,
            "code_challenge_methods_supported": "not-a-list",
            "unknown": "dropped",
        }
    )
    assert sanitized["issuer"] == "https://as.example.test"
    assert "authorization_endpoint" not in sanitized
    assert "unknown" not in sanitized
    assert sanitized["scopes_supported"][0] == "read"
    assert sanitized["scopes_supported"][1] == "x" * 200
    assert 5 not in sanitized["scopes_supported"]
    assert len(sanitized["scopes_supported"]) == 49

    assert oauth._normalize_scope_values(" read  write read ") == (
        "read",
        "write",
    )
    assert oauth._normalize_scope_values(["", "x y", "a" * 201, "ok", "ok"]) == ("ok",)
    assert oauth._normalize_scope_values(42) == ()
    assert oauth._parse_expiry(None) is None
    assert oauth._parse_expiry("not-a-date") is None
    naive = oauth._parse_expiry("2026-01-01T00:00:00")
    assert naive is not None and naive.tzinfo == timezone.utc
    assert oauth._parse_expires_in(None) == oauth.DEFAULT_TOKEN_LIFETIME_SECONDS
    with pytest.raises(oauth._OAuthEndpointError):
        oauth._parse_expires_in(0)
    with pytest.raises(oauth._OAuthEndpointError):
        oauth._parse_expires_in("soon")
    assert oauth._sanitize_token_type(None) == "Bearer"
    assert oauth._sanitize_token_type(" bearer ") == "Bearer"
    with pytest.raises(oauth._OAuthEndpointError):
        oauth._sanitize_token_type("DPoP")

    assert oauth._decode_id_token_claims(None) == {}
    assert oauth._decode_id_token_claims("onlyonepart") == {}
    assert oauth._decode_id_token_claims("a." + "b" * 33000 + ".sig") == {}
    assert oauth._decode_id_token_claims("a.%%%%.sig") == {}
    not_a_map = base64.urlsafe_b64encode(b"123").rstrip(b"=").decode()
    assert oauth._decode_id_token_claims(f"a.{not_a_map}.sig") == {}
    assert oauth._decode_id_token_claims(
        _id_token({"sub": "external", "email": "a@example.test"})
    ) == {"sub": "external", "email": "a@example.test"}

    assert oauth._identity_from_claims({"sub": 7}) == (None, None)
    assert oauth._identity_from_claims({"sub": "s"}) == ("s", None)
    assert oauth._identity_from_claims(
        {"sub": "s", "email": "e" * 400, "name": "n"}
    ) == ("s", "e" * 150)
    assert oauth._identity_from_claims(
        {"sub": "s", "preferred_username": "p", "name": "n"}
    ) == ("s", "p")


async def test_frontend_redirect_allowlist_and_error_slug_mapping(monkeypatch):
    _frontend(monkeypatch)

    unsafe = await oauth._frontend_redirect(
        redirect_path="https://evil.example/steal", error_key="secret internal"
    )
    assert unsafe.startswith("https://app.example.test/app?")
    assert _query(unsafe)["oauth"] == ["error"]
    assert _query(unsafe)["error"] == ["oauth_callback_failed"]

    known = await oauth._frontend_redirect(
        redirect_path="/app?tab=1",
        error_key="tool_oauth_expired",
        connection_id=uuid4(),
    )
    assert known.startswith("https://app.example.test/app?tab=1&")
    assert _query(known)["error"] == ["oauth_expired"]
    assert _query(known)["connection_id"]

    success = await oauth._frontend_redirect(redirect_path=None)
    assert success == "https://app.example.test/app?oauth=success"


# ---------------------------------------------------------------------------
# Start authorization
# ---------------------------------------------------------------------------


async def test_start_rejects_builtin_revoked_and_invalid_inputs(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)

        builtin = await _connection(
            team=team,
            builtin_tool_key="web_search",
            user=admin,
            scope=ToolConnectionScope.USER,
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=builtin.id
            ),
        )

        tool = await _http_tool(team, admin)
        revoked = await _connection(
            team=team,
            tool=tool,
            user=admin,
            scope=ToolConnectionScope.USER,
            status=ToolConnectionStatus.REVOKED,
        )
        await _expect(
            ResponseCode.TOOL_CONNECTION_INACTIVE,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=revoked.id
            ),
        )

        personal = await _connection(
            team=team, tool=tool, user=admin, scope=ToolConnectionScope.USER
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin,
                connection_id=personal.id,
                redirect_path="/other",
            ),
        )
        for secret in ("", "x" * (oauth.MAX_CLIENT_SECRET_LENGTH + 1)):
            await _expect(
                ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
                lambda secret=secret: oauth.ToolOAuthService.start_authorization(
                    actor=admin,
                    connection_id=personal.id,
                    client_secret=secret,
                ),
            )

        # A connection whose tool the actor cannot read is rejected before any
        # provider configuration is written.
        assert await ToolOAuthProvider.filter(tool_id=tool.id).count() == 0


async def test_start_requires_tool_access_for_personal_owner(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        team = await _team(admin, member=owner)
        tool = await _http_tool(team, admin)
        tool.visibility = ToolVisibility.PRIVATE
        await tool.save()
        connection = await _connection(
            team=team, tool=tool, user=owner, scope=ToolConnectionScope.USER
        )

        error = await _expect(
            ResponseCode.PERMISSION_DENIED,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=owner, connection_id=connection.id
            ),
        )
        assert error.msg_key == "tool_access_denied"
        assert await ToolOAuthProvider.filter(tool_id=tool.id).count() == 0


async def test_start_enforces_http_provider_secret_contract(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)

        basic_tool = await _http_tool(
            team, admin, auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC
        )
        basic_connection = await _connection(
            team=team, tool=basic_tool, user=admin, scope=ToolConnectionScope.USER
        )
        error = await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=basic_connection.id
            ),
        )
        assert error.msg_key == "tool_oauth_client_secret_required"

        none_tool = await _http_tool(team, admin)
        none_connection = await _connection(
            team=team, tool=none_tool, user=admin, scope=ToolConnectionScope.USER
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin,
                connection_id=none_connection.id,
                client_secret="unexpected",
            ),
        )

        missing_oauth_tool = await _http_tool(team, admin)
        missing_oauth_tool.http_config = {}
        await missing_oauth_tool.save()
        missing_connection = await _connection(
            team=team,
            tool=missing_oauth_tool,
            user=admin,
            scope=ToolConnectionScope.USER,
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=missing_connection.id
            ),
        )

        malformed_tool = await _http_tool(team, admin)
        malformed_tool.http_config = {
            "oauth2": {"authorization_endpoint": "https://auth.example.test/a"}
        }
        await malformed_tool.save()
        malformed_connection = await _connection(
            team=team,
            tool=malformed_tool,
            user=admin,
            scope=ToolConnectionScope.USER,
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=malformed_connection.id
            ),
        )


async def test_http_provider_reuses_row_and_fails_on_client_id_swap(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(
            team, admin, auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC
        )
        connection = await _connection(
            team=team, tool=tool, user=admin, scope=ToolConnectionScope.USER
        )

        await oauth.ToolOAuthService.start_authorization(
            actor=admin,
            connection_id=connection.id,
            client_secret="secret-one",
        )
        provider = await ToolOAuthProvider.get(tool_id=tool.id)
        assert provider.client_id == "client-1"
        assert decrypt_tool_secret(provider.client_secret_encrypted) == "secret-one"

        # Rotating the public client id without rotating the secret must fail
        # closed instead of silently reusing the old credential.
        tool.http_config["oauth2"]["client_id"] = "client-2"
        await tool.save()
        error = await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=connection.id
            ),
        )
        assert error.msg_key == "tool_oauth_client_secret_required"

        await oauth.ToolOAuthService.start_authorization(
            actor=admin,
            connection_id=connection.id,
            client_secret="secret-two",
        )
        providers = await ToolOAuthProvider.filter(tool_id=tool.id)
        assert len(providers) == 1
        provider = providers[0]
        assert provider.client_id == "client-2"
        assert decrypt_tool_secret(provider.client_secret_encrypted) == "secret-two"


# ---------------------------------------------------------------------------
# MCP discovery
# ---------------------------------------------------------------------------


async def _no_probe(monkeypatch):
    async def probe(_url):
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_probe_resource_metadata_url", probe)


async def test_mcp_provider_rejects_transport_and_missing_servers(monkeypatch):
    _allow_ssrf(monkeypatch)
    await _no_probe(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)
        tool.mcp_config["transport"] = "stdio"
        await tool.save()

        await _expect(
            ResponseCode.TOOL_OAUTH_NOT_SUPPORTED,
            lambda: oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            ),
        )

        tool.mcp_config["transport"] = "http"
        await tool.save()

        async def empty_prm(url, **kwargs):
            return {}

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", empty_prm)
        await _expect(
            ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
            lambda: oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            ),
        )


async def test_mcp_metadata_requires_exact_issuer_match(monkeypatch):
    _allow_ssrf(monkeypatch)
    await _no_probe(monkeypatch)

    async def fake_http_json(url, **kwargs):
        if "oauth-protected-resource" in url:
            return {"authorization_servers": ["https://as.example.test"]}
        return {
            "issuer": "https://other.example.test",
            "authorization_endpoint": "https://as.example.test/authorize",
            "token_endpoint": "https://as.example.test/token",
            "code_challenge_methods_supported": ["S256"],
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)

        await _expect(
            ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
            lambda: oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            ),
        )


async def test_mcp_explicit_server_skips_resource_discovery(monkeypatch):
    _allow_ssrf(monkeypatch)
    calls: list[str] = []

    async def forbidden_probe(_url):
        raise AssertionError("protected-resource discovery must be skipped")

    monkeypatch.setattr(
        oauth.ToolOAuthService, "_probe_resource_metadata_url", forbidden_probe
    )

    async def fake_http_json(url, **kwargs):
        calls.append(url)
        return {
            "issuer": "https://as.example.test",
            "authorization_endpoint": "https://as.example.test/authorize",
            "token_endpoint": "https://as.example.test/token",
            "code_challenge_methods_supported": ["S256"],
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(
            team,
            admin,
            oauth_config={
                "authorization_server": "https://as.example.test",
                "client_id": "preset-client",
            },
        )

        setup = await oauth.ToolOAuthService._ensure_provider(
            tool=tool,
            kind=ToolOAuthProviderKind.MCP,
            redirect_uri="https://api.example.test/callback",
            client_secret=None,
        )

        provider = setup.provider
        assert provider.client_id == "preset-client"
        assert provider.authorization_server == "https://as.example.test"
        assert provider.resource == "https://mcp.example.test/mcp"
        assert provider.provider_kind == ToolOAuthProviderKind.MCP
        assert provider.code_challenge_methods == ["S256"]
        assert all("oauth-protected-resource" not in url for url in calls)


async def test_mcp_reuses_client_id_and_requires_secret_on_rotation(monkeypatch):
    _allow_ssrf(monkeypatch)
    await _no_probe(monkeypatch)
    calls: list[str] = []

    async def fake_http_json(url, **kwargs):
        calls.append(url)
        if url == "https://as.example.test/register":
            return {"client_id": "registered", "client_secret": "registered-secret"}
        return {
            "issuer": "https://as.example.test",
            "authorization_endpoint": "https://as.example.test/authorize",
            "token_endpoint": "https://as.example.test/token",
            "registration_endpoint": "https://as.example.test/register",
            "code_challenge_methods_supported": ["S256"],
        }

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(
            team,
            admin,
            oauth_config={
                "authorization_server": "https://as.example.test",
                "client_id": "client-one",
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )

        first = await oauth.ToolOAuthService._ensure_provider(
            tool=tool,
            kind=ToolOAuthProviderKind.MCP,
            redirect_uri="https://api.example.test/callback",
            client_secret="secret-one",
        )
        assert first.provider.client_id == "client-one"

        # A new public client id needs a new secret.
        tool.mcp_config["oauth"]["client_id"] = "client-two"
        await tool.save()
        error = await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.MCP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            ),
        )
        assert error.msg_key == "tool_oauth_client_secret_required"

        rotated = await oauth.ToolOAuthService._ensure_provider(
            tool=tool,
            kind=ToolOAuthProviderKind.MCP,
            redirect_uri="https://api.example.test/callback",
            client_secret="secret-two",
        )
        assert rotated.provider.client_id == "client-two"
        assert (
            decrypt_tool_secret(rotated.provider.client_secret_encrypted)
            == "secret-two"
        )

        # Dropping the explicit client id reuses the registered client rather
        # than performing dynamic registration again.
        del tool.mcp_config["oauth"]["client_id"]
        await tool.save()
        reused = await oauth.ToolOAuthService._ensure_provider(
            tool=tool,
            kind=ToolOAuthProviderKind.MCP,
            redirect_uri="https://api.example.test/callback",
            client_secret=None,
        )
        assert reused.provider.client_id == "client-two"
        assert await ToolOAuthProvider.filter(tool_id=tool.id).count() == 1
        assert "https://as.example.test/register" not in calls


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


async def _started_flow(admin: User, owner: User, team: Team, tool: Tool):
    connection = await _connection(
        team=team, tool=tool, user=owner, scope=ToolConnectionScope.USER
    )
    started = await oauth.ToolOAuthService.start_authorization(
        actor=owner, connection_id=connection.id
    )
    return connection, started


async def test_callback_rejects_unusable_state(monkeypatch):
    _frontend(monkeypatch)
    async with _database():
        for state in (None, "x" * 513, "unknown-state"):
            redirect = await oauth.ToolOAuthService.handle_callback(
                state=state, code="code"
            )
            assert _query(redirect)["error"] == ["oauth_state_invalid"]


async def test_callback_requires_code_and_readable_verifier(monkeypatch):
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
        _, started = await _started_flow(admin, owner, team, tool)

        missing = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code=None
        )
        assert _query(missing)["error"] == ["oauth_exchange_failed"]

        connection, started = await _started_flow(admin, owner, team, tool)
        await ToolOAuthFlow.filter(connection_id=connection.id).update(
            code_verifier_encrypted="not-a-fernet-token"
        )
        unreadable = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(unreadable)["error"] == ["oauth_state_invalid"]

        _, started = await _started_flow(admin, owner, team, tool)
        oversized = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="c" * 4097
        )
        assert _query(oversized)["error"] == ["oauth_exchange_failed"]


async def test_callback_rejects_inactive_user_and_lost_membership(monkeypatch):
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

        _, started = await _started_flow(admin, owner, team, tool)
        await User.filter(id=owner.id).update(is_active=False)
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(redirect)["error"] == ["oauth_state_invalid"]

        await User.filter(id=owner.id).update(is_active=True)
        _, started = await _started_flow(admin, owner, team, tool)
        await TeamMember.filter(team_id=team.id, user_id=owner.id).delete()
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(redirect)["error"] == ["oauth_state_invalid"]


async def test_callback_rejects_revoked_or_retargeted_connection(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    monkeypatch.setattr(
        oauth.ToolOAuthService,
        "_http_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no network")),
    )
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        connection, started = await _started_flow(admin, admin, team, tool)
        await ToolConnection.filter(id=connection.id).update(
            status=ToolConnectionStatus.REVOKED
        )
        revoked = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(revoked)["error"] == ["oauth_callback_failed"]

        await ToolConnection.filter(id=connection.id).update(
            status=ToolConnectionStatus.ACTIVE
        )
        connection, started = await _started_flow(admin, admin, team, tool)
        other_tool = await _http_tool(team, admin)
        await ToolConnection.filter(id=connection.id).update(tool_id=other_tool.id)
        retargeted = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(retargeted)["error"] == ["oauth_callback_failed"]
        assert "oauth_access_token" not in ToolConnectionService._decrypt_config(
            await ToolConnection.get(id=connection.id)
        )


async def test_callback_maps_endpoint_and_unexpected_failures(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        async def unsupported(url, **kwargs):
            raise oauth._OAuthEndpointError("unsupported_token_type")

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", unsupported)
        _, started = await _started_flow(admin, admin, team, tool)
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(redirect)["error"] == ["oauth_config_invalid"]

        async def explode(url, **kwargs):
            raise RuntimeError("provider broke")

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", explode)
        unexpected, started = await _started_flow(admin, admin, team, tool)
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(redirect)["error"] == ["oauth_callback_failed"]
        # An unexpected error never half-applies tokens: the connection keeps
        # the pending state it had when the flow started.
        unexpected = await ToolConnection.get(id=unexpected.id)
        assert unexpected.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert ToolConnectionService._decrypt_config(unexpected) == {}

        # A classified provider failure during reauthorization downgrades a
        # connection whose stored token is already expired, so it cannot keep
        # looking usable after the browser flow failed.
        async def classified_failure(url, **kwargs):
            raise oauth._OAuthEndpointError("server_error", status=500)

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", classified_failure)
        provider = await _provider_for(tool)
        stale = await _seed_tokens(
            team=team, tool=tool, owner=admin, provider=provider, expires_in=-60
        )
        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=stale.id
        )
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="code"
        )
        assert _query(redirect)["error"] == ["oauth_exchange_failed"]
        stale = await ToolConnection.get(id=stale.id)
        assert stale.status == ToolConnectionStatus.REAUTH_REQUIRED
        config = ToolConnectionService._decrypt_config(stale)
        # The stale credential is retained for audit but is never served: the
        # execution path attempts a refresh and surfaces the provider failure.
        assert config["oauth_access_token"] == "old-access"
        with pytest.raises(BusinessError) as refresh_failed:
            await oauth.ToolOAuthService.get_access_token(
                _resolved(stale, team.id, admin.id, tool.id)
            )
        assert refresh_failed.value.code == ResponseCode.TOOL_OAUTH_EXCHANGE_FAILED
        assert refresh_failed.value.msg_key == "tool_oauth_refresh_failed"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def test_status_falls_back_to_tool_provider_and_scopes(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool, scopes=["read", "profile"])
        future = (now_utc() + timedelta(minutes=10)).isoformat()

        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            scope=ToolConnectionScope.USER,
            config={
                "oauth_access_token": "access",
                "oauth_expires_at": future,
                "oauth_provider_id": "not-a-uuid",
            },
        )
        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=connection.id
        )
        assert status.provider_configured is True
        assert status.client_id == provider.client_id
        assert status.scopes == ["read", "profile"]
        assert status.authorized is True
        assert status.needs_reauth is False

        # An unknown provider id never blocks reporting the tool's provider.
        assert status.provider_kind == ToolOAuthProviderKind.HTTP


async def test_status_needs_reauth_depends_on_refresh_availability(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)

        without_refresh = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            refresh=None,
            expires_in=-30,
        )
        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=without_refresh.id
        )
        assert status.authorized is True
        assert status.needs_reauth is True

        with_refresh = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            expires_in=-30,
        )
        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=with_refresh.id
        )
        assert status.authorized is True
        assert status.needs_reauth is False

        never_authorized = await _connection(
            team=team, tool=tool, user=admin, scope=ToolConnectionScope.USER
        )
        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=never_authorized.id
        )
        assert status.authorized is False
        assert status.needs_reauth is True


async def test_status_denies_other_users_personal_connection(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        bob = await _user("bob")
        team = await _team(admin, member=owner)
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=bob.id, role="member"
        )
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team, tool=tool, user=owner, scope=ToolConnectionScope.USER
        )

        await _expect(
            ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
            lambda: oauth.ToolOAuthService.get_status(
                actor=bob, connection_id=connection.id
            ),
        )


# ---------------------------------------------------------------------------
# Disconnect and revocation
# ---------------------------------------------------------------------------


async def test_disconnect_permissions_and_reserved_key_cleanup(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        owner = await _user("owner")
        bob = await _user("bob")
        root = await _user("root", superuser=True)
        team = await _team(admin, member=owner)
        await TeamMember.create(
            id=uuid4(), team_id=team.id, user_id=bob.id, role="member"
        )
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
            config={
                "api_key": "keep-me",
                "oauth_access_token": "access",
                "oauth_refresh_token": "refresh",
                "oauth_expires_at": now_utc().isoformat(),
                "oauth_scope": "read",
                "oauth_account_subject": "subject",
            },
        )

        for actor in (bob, root):
            await _expect(
                ResponseCode.TOOL_CONNECTION_ACCESS_DENIED,
                lambda actor=actor: oauth.ToolOAuthService.disconnect(
                    actor=actor, connection_id=connection.id
                ),
            )

        result = await oauth.ToolOAuthService.disconnect(
            actor=owner, connection_id=connection.id
        )
        assert result.local_revoked is True
        assert result.remote_revocation == "unsupported"
        assert result.needs_reauth is True
        stored = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(stored)
        assert config == {"api_key": "keep-me"}
        assert stored.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert stored.secret_version == 2

        revoked = await _connection(
            team=team,
            tool=tool,
            user=owner,
            scope=ToolConnectionScope.USER,
            config={
                "oauth_access_token": "access",
                "oauth_refresh_token": "refresh",
            },
            status=ToolConnectionStatus.REVOKED,
        )
        result = await oauth.ToolOAuthService.disconnect(
            actor=owner, connection_id=revoked.id
        )
        assert result.local_revoked is True
        assert result.needs_reauth is False
        stored = await ToolConnection.get(id=revoked.id)
        assert stored.status == ToolConnectionStatus.REVOKED
        assert ToolConnectionService._decrypt_config(stored) == {}


async def test_remote_revocation_maps_transport_outcomes(monkeypatch):
    _allow_ssrf(monkeypatch)
    seen: dict[str, str] = {}
    handler_holder: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(
            transport=httpx.MockTransport(handler_holder["handler"]),
            follow_redirects=False,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(
            tool,
            revocation_endpoint="https://as.example.test/revoke",
            client_id="client id",
            client_secret_encrypted=encrypt_tool_secret("s3cret"),
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC,
        )

        def success(request):
            seen["authorization"] = request.headers.get("authorization", "")
            seen["body"] = request.content.decode()
            return httpx.Response(204)

        handler_holder["handler"] = success
        assert (
            await oauth.ToolOAuthService._revoke_remote_token(
                provider, "refresh-token", "refresh_token"
            )
            == "revoked"
        )
        assert seen["authorization"].startswith("Basic ")
        body = parse_qs(seen["body"])
        assert body["token"] == ["refresh-token"]
        assert body["token_type_hint"] == ["refresh_token"]

        handler_holder["handler"] = lambda request: httpx.Response(500)
        assert (
            await oauth.ToolOAuthService._revoke_remote_token(
                provider, "token", "access_token"
            )
            == "failed"
        )

        def explode(request):
            raise httpx.ConnectError("boom", request=request)

        handler_holder["handler"] = explode
        assert (
            await oauth.ToolOAuthService._revoke_remote_token(
                provider, "token", "access_token"
            )
            == "failed"
        )

        provider.revocation_endpoint = None
        await provider.save()
        assert (
            await oauth.ToolOAuthService._revoke_remote_token(
                provider, "token", "access_token"
            )
            == "unsupported"
        )

        async def deny(url, getaddrinfo=None):
            raise RuntimeError("blocked")

        monkeypatch.setattr(oauth, "ensure_external_http_url_allowed", deny)
        provider.revocation_endpoint = "https://as.example.test/revoke"
        await provider.save()
        assert (
            await oauth.ToolOAuthService._revoke_remote_token(
                provider, "token", "access_token"
            )
            == "failed"
        )


# ---------------------------------------------------------------------------
# Execution-facing token access
# ---------------------------------------------------------------------------


async def test_access_token_without_refresh_token(monkeypatch):
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
        valid = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            access="still-valid",
            refresh=None,
            expires_in=300,
        )
        resolved = _resolved(valid, team.id, admin.id, tool.id)
        assert await oauth.ToolOAuthService.get_access_token(resolved) == "still-valid"
        assert (
            await oauth.ToolOAuthService.get_access_token(resolved, force=True)
            == "still-valid"
        )
        assert (
            await oauth.ToolOAuthService.get_authorization_header(resolved)
            == "Bearer still-valid"
        )

        expired = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            access="expired",
            refresh=None,
            expires_in=-60,
        )
        resolved = _resolved(expired, team.id, admin.id, tool.id)
        error = await _expect(
            ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED,
            lambda: oauth.ToolOAuthService.get_access_token(resolved),
        )
        assert error.msg_key == "tool_oauth_reauth_required"
        stored = await ToolConnection.get(id=expired.id)
        assert stored.status == ToolConnectionStatus.REAUTH_REQUIRED


async def test_access_token_rejects_bad_storage_and_missing_binding(monkeypatch):
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

        wrong_type = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            token_type="DPoP",
            expires_in=300,
        )
        await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.get_access_token(
                _resolved(wrong_type, team.id, admin.id, tool.id)
            ),
        )

        revoked = await _seed_tokens(
            team=team,
            tool=tool,
            owner=admin,
            provider=provider,
            status=ToolConnectionStatus.REVOKED,
        )
        await _expect(
            ResponseCode.TOOL_CONNECTION_INACTIVE,
            lambda: oauth.ToolOAuthService.get_access_token(
                _resolved(revoked, team.id, admin.id, tool.id)
            ),
        )

        deleted = await _seed_tokens(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(deleted, team.id, admin.id, tool.id)
        await ToolConnection.filter(id=deleted.id).delete()
        await _expect(
            ResponseCode.TOOL_CONNECTION_NOT_FOUND,
            lambda: oauth.ToolOAuthService.get_access_token(resolved),
        )

        # A refreshable connection with no discoverable provider must ask for
        # reauthorization rather than calling an arbitrary endpoint.
        orphan_tool = await _http_tool(team, admin)
        orphan = await _seed_tokens(
            team=team,
            tool=orphan_tool,
            owner=admin,
            provider=provider,
            expires_in=-60,
        )
        # Point at a provider that does not exist and hide the tool fallback.
        config = ToolConnectionService._decrypt_config(orphan)
        config["oauth_provider_id"] = str(uuid4())
        encrypted, fields = ToolConnectionService._encrypt_config(config)
        await ToolConnection.filter(id=orphan.id).update(
            encrypted_config=encrypted, secret_fields=fields
        )
        await ToolOAuthProvider.filter(tool_id=orphan_tool.id).delete()
        await _expect(
            ResponseCode.TOOL_OAUTH_REAUTH_REQUIRED,
            lambda: oauth.ToolOAuthService.get_access_token(
                _resolved(orphan, team.id, admin.id, orphan_tool.id)
            ),
        )


async def test_refresh_endpoint_failures_map_to_consumer_errors(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _seed_tokens(
            team=team, tool=tool, owner=admin, provider=provider
        )
        resolved = _resolved(connection, team.id, admin.id, tool.id)

        async def server_error(url, **kwargs):
            raise oauth._OAuthEndpointError("server_error", status=500)

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", server_error)
        error = await _expect(
            ResponseCode.TOOL_OAUTH_EXCHANGE_FAILED,
            lambda: oauth.ToolOAuthService.get_access_token(resolved),
        )
        assert error.msg_key == "tool_oauth_refresh_failed"
        assert error.status_code == 502
        stored = await ToolConnection.get(id=connection.id)
        assert stored.status == ToolConnectionStatus.ACTIVE

        async def unsupported(url, **kwargs):
            raise oauth._OAuthEndpointError("unsupported_token_type")

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", unsupported)
        error = await _expect(
            ResponseCode.TOOL_OAUTH_CONFIG_INVALID,
            lambda: oauth.ToolOAuthService.get_access_token(resolved),
        )
        assert error.msg_key == "tool_oauth_config_invalid"
        assert error.status_code == 409


async def test_has_oauth_binding_requires_matching_connection_and_tool(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)

        assert await oauth.ToolOAuthService.has_oauth_binding(None) is False

        plain = await _connection(
            team=team, tool=tool, user=admin, scope=ToolConnectionScope.USER
        )
        assert (
            await oauth.ToolOAuthService.has_oauth_binding(
                _resolved(plain, team.id, admin.id, tool.id)
            )
            is False
        )

        bound = await _connection(
            team=team,
            tool=tool,
            user=admin,
            scope=ToolConnectionScope.USER,
            config={"oauth_provider_id": str(provider.id)},
        )
        assert (
            await oauth.ToolOAuthService.has_oauth_binding(
                _resolved(bound, team.id, admin.id, tool.id)
            )
            is True
        )
        assert (
            await oauth.ToolOAuthService.has_oauth_binding(
                _resolved(bound, team.id, admin.id, uuid4())
            )
            is False
        )


# ---------------------------------------------------------------------------
# HTTP client bounds and registration
# ---------------------------------------------------------------------------


async def test_http_json_bounds_and_error_shapes(monkeypatch):
    _allow_ssrf(monkeypatch)
    handler_holder: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(
            transport=httpx.MockTransport(handler_holder["handler"]),
            follow_redirects=False,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)

    handler_holder["handler"] = lambda request: httpx.Response(
        400, json={"error": "invalid_client", "error_description": "bad client"}
    )
    with pytest.raises(oauth._OAuthEndpointError) as failed:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST"
        )
    assert (failed.value.error, failed.value.description, failed.value.status) == (
        "invalid_client",
        "bad client",
        400,
    )

    handler_holder["handler"] = lambda request: httpx.Response(200, json={"ok": True})
    assert await oauth.ToolOAuthService._http_json(
        "https://as.example.test/token", method="POST"
    ) == {"ok": True}

    handler_holder["handler"] = lambda request: httpx.Response(
        200, content=b"not json", headers={"content-type": "text/plain"}
    )
    with pytest.raises(oauth._OAuthEndpointError) as invalid:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST"
        )
    assert invalid.value.error == "invalid_json"

    handler_holder["handler"] = lambda request: httpx.Response(
        200, content=b"0123456789", headers={"content-type": "application/json"}
    )
    with pytest.raises(oauth._OAuthEndpointError) as oversized:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST", max_bytes=5
        )
    assert oversized.value.error == "response_too_large"

    def explode(request):
        raise httpx.ConnectError("unreachable", request=request)

    handler_holder["handler"] = explode
    with pytest.raises(oauth._OAuthEndpointError) as network:
        await oauth.ToolOAuthService._http_json(
            "https://as.example.test/token", method="POST"
        )
    assert network.value.error == "network_error"


async def test_register_client_validates_response_and_scope_payload(monkeypatch):
    captured: list[dict] = []

    async def fake_http_json(url, *, method, json_body=None, **kwargs):
        captured.append({"url": url, "body": dict(json_body or {})})
        return {"client_id": "dcr-client"}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", fake_http_json)
    _allow_ssrf(monkeypatch)

    client_id, secret = await oauth.ToolOAuthService._register_client(
        registration_endpoint="https://as.example.test/register",
        redirect_uri="https://api.example.test/callback",
        scopes=["read", "write"],
    )
    assert (client_id, secret) == ("dcr-client", None)
    assert captured[0]["body"]["scope"] == "read write"
    assert captured[0]["body"]["token_endpoint_auth_method"] == "none"

    await oauth.ToolOAuthService._register_client(
        registration_endpoint="https://as.example.test/register",
        redirect_uri="https://api.example.test/callback",
        scopes=[],
    )
    assert "scope" not in captured[1]["body"]

    response_payload: dict = {}

    async def payload_http_json(url, *, method, json_body=None, **kwargs):
        return response_payload

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", payload_http_json)
    for payload in (
        {"client_id": ""},
        {"client_id": 5},
        {"client_id": "ok", "client_secret": 5},
        {"client_id": "ok", "client_secret": "x" * 8193},
    ):
        response_payload.clear()
        response_payload.update(payload)
        error = await _expect(
            ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
            lambda: oauth.ToolOAuthService._register_client(
                registration_endpoint="https://as.example.test/register",
                redirect_uri="https://api.example.test/callback",
                scopes=["read"],
            ),
        )
        assert error.msg_key == "tool_oauth_client_registration_failed"

    async def broken_http_json(url, **kwargs):
        raise oauth._OAuthEndpointError("http_error", status=500)

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", broken_http_json)
    error = await _expect(
        ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED,
        lambda: oauth.ToolOAuthService._register_client(
            registration_endpoint="https://as.example.test/register",
            redirect_uri="https://api.example.test/callback",
            scopes=["read"],
        ),
    )
    assert error.msg_key == "tool_oauth_client_registration_failed"


async def test_cleanup_expired_flows_is_bounded_and_noop():
    async with _database():
        assert await oauth.ToolOAuthService.cleanup_expired_flows() == 0

        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _connection(
            team=team, tool=tool, user=admin, scope=ToolConnectionScope.USER
        )
        old = now_utc() - oauth.FLOW_RETENTION - timedelta(hours=1)
        flow_ids = []
        for index in range(3):
            flow = await ToolOAuthFlow.create(
                state_hash=f"{index}" * 64,
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
            flow_ids.append(flow.id)

        assert await oauth.ToolOAuthService.cleanup_expired_flows(limit=2) == 2
        assert await ToolOAuthFlow.filter(id__in=flow_ids).count() == 1
