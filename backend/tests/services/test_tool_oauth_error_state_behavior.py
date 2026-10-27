"""Error and state behavior for tool OAuth connections on real ORM rows.

Focuses on outcomes a browser/consumer can observe after a failed
re-authorization: a still-valid token must not be downgraded, a revoked
connection must fail with the generic sanitized redirect, providers without
scopes must not receive a synthetic scope, and root-mounted MCP servers must
be discoverable. External HTTP and the SSRF guard are replaced at their module
boundary; tokens, flows and connection state use real Tortoise models.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.core.config import settings
from app.core.timezone import now_utc
from app.models.tool import CustomToolType, Tool, ToolType, ToolVisibility
from app.models.tool_connection import (
    ToolConnection,
    ToolConnectionScope,
    ToolConnectionStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.services import tool_oauth as oauth
from app.services.tool_connections import ToolConnectionService

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
    suffix = uuid4().hex[:8]
    user = await User.create(
        id=uuid4(),
        username=f"{label}_{suffix}",
        email=f"{label}_{suffix}@oauth.test",
        hashed_password="x",
    )
    permission, _ = await Permission.get_or_create(
        code="team:read",
        defaults={"id": uuid4(), "scope": "team", "description": "Read team"},
    )
    role, _ = await Role.get_or_create(
        name="oauth_state_reader",
        defaults={"id": uuid4(), "description": "OAuth state reader"},
    )
    await role.permissions.add(permission)
    await user.roles.add(role)
    return await User.get(id=user.id).prefetch_related("roles__permissions")


async def _team(owner: User) -> Team:
    team = await Team.create(
        id=uuid4(), name=f"team_{uuid4().hex[:8]}", owner_id=owner.id
    )
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _http_tool(team: Team, admin: User, *, oauth2: dict | None = None) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=admin.id,
        name=f"http_{uuid4().hex[:8]}",
        display_name="OAuth HTTP tool",
        description="oauth state test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        visibility=ToolVisibility.TEAM,
        http_config={
            "oauth2": oauth2
            if oauth2 is not None
            else {
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "client_id": "client-1",
                "scopes": ["read"],
            }
        },
        connection_fields=[
            {"name": "oauth_access_token", "secret": True, "required": True}
        ],
    )


async def _connection(
    *,
    team: Team,
    tool: Tool,
    user: User,
    config: dict[str, str] | None = None,
) -> ToolConnection:
    encrypted, fields = ToolConnectionService._encrypt_config(config or {})
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id,
        tool_id=tool.id,
        scope=ToolConnectionScope.USER,
        owner_user_id=user.id,
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


def _frontend(monkeypatch, value: str = "https://app.example.test") -> None:
    async def fake_frontend_url():
        return value

    monkeypatch.setattr(oauth, "_frontend_url", fake_frontend_url)


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


async def test_failed_reauthorization_keeps_still_valid_token(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)

    async def token_response(*args, **kwargs):
        return {"access_token": "attempted", "expires_in": 300, "scope": "read write"}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", token_response)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            config={
                "oauth_access_token": "still-valid",
                "oauth_expires_at": (now_utc() + timedelta(minutes=10)).isoformat(),
                "oauth_scope": "read",
            },
        )

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=connection.id
        )
        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="auth-code"
        )

        query = _query(redirect)
        assert query["oauth"] == ["error"]
        assert query["error"] == ["oauth_scope_escalation"]
        stored = await ToolConnection.get(id=connection.id)
        assert stored.status == ToolConnectionStatus.ACTIVE
        assert stored.secret_version == 1
        config = ToolConnectionService._decrypt_config(stored)
        assert config["oauth_access_token"] == "still-valid"
        assert config["oauth_scope"] == "read"


async def test_revoked_connection_callback_redirects_generic_failure(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)

    async def no_network(*args, **kwargs):
        raise AssertionError("revoked connections must not exchange tokens")

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", no_network)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        connection = await _connection(team=team, tool=tool, user=admin)

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=connection.id
        )
        await ToolConnectionService.revoke_connection(
            actor=admin, connection_id=connection.id
        )

        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="auth-code"
        )

        query = _query(redirect)
        assert query["oauth"] == ["error"]
        assert query["error"] == ["oauth_callback_failed"]
        assert query["connection_id"] == [str(connection.id)]
        stored = await ToolConnection.get(id=connection.id)
        assert stored.status == ToolConnectionStatus.REVOKED


async def test_start_and_callback_without_provider_scopes_omit_scope(monkeypatch):
    _allow_ssrf(monkeypatch)
    _frontend(monkeypatch)

    async def token_response(*args, **kwargs):
        return {"access_token": "access-1", "expires_in": 300}

    monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", token_response)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(
            team,
            admin,
            oauth2={
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "client_id": "client-1",
            },
        )
        connection = await _connection(team=team, tool=tool, user=admin)

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=connection.id
        )
        assert "scope" not in _query(started.authorization_url)

        redirect = await oauth.ToolOAuthService.handle_callback(
            state=started.state, code="auth-code"
        )
        assert _query(redirect)["oauth"] == ["success"]

        stored = await ToolConnection.get(id=connection.id)
        assert stored.status == ToolConnectionStatus.ACTIVE
        config = ToolConnectionService._decrypt_config(stored)
        assert config["oauth_access_token"] == "access-1"
        assert "oauth_scope" not in config


async def test_protected_resource_metadata_supports_root_mcp_url(monkeypatch):
    async def no_header_probe(mcp_url):
        return None

    monkeypatch.setattr(
        oauth.ToolOAuthService, "_probe_resource_metadata_url", no_header_probe
    )
    seen: list[str] = []

    async def try_json(url):
        seen.append(url)
        if url == "https://mcp.example.test/.well-known/oauth-protected-resource":
            return {"resource": "https://mcp.example.test"}
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_try_json", try_json)

    metadata = await oauth.ToolOAuthService._protected_resource_metadata(
        "https://mcp.example.test"
    )

    assert metadata == {"resource": "https://mcp.example.test"}
    assert seen == ["https://mcp.example.test/.well-known/oauth-protected-resource"]
