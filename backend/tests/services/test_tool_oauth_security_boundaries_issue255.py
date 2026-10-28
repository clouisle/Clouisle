"""Security and error-path boundaries for tool OAuth configuration and service.

Every scenario targets a decision a consumer can observe: rejected provider
config, fail-closed discovery, corrupt local secrets, stale/revoked connection
state and race-lost rows. Real Tortoise models are used; only external HTTP and
the SSRF guard are replaced at their module boundary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from tortoise import Tortoise
from tortoise.exceptions import IntegrityError

from app.core.config import settings
from app.core.timezone import now_utc
from app.models.site_setting import SiteSetting
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
        name="oauth_boundaries_reader",
        defaults={"id": uuid4(), "description": "OAuth boundary reader"},
    )
    await role.permissions.add(permission)
    await user.roles.add(role)
    return await User.get(id=user.id).prefetch_related("roles__permissions")


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _http_tool(
    team: Team,
    admin: User,
    *,
    oauth2: dict | None = None,
) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=admin.id,
        name=f"http_{uuid4().hex[:8]}",
        display_name="OAuth HTTP tool",
        description="oauth boundary test",
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


async def _mcp_tool(
    team: Team, admin: User, *, oauth_config: dict | None = None
) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=admin.id,
        name=f"mcp_{uuid4().hex[:8]}",
        display_name="OAuth MCP server",
        description="oauth boundary test",
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
    user: User | None = None,
    config: dict[str, str] | None = None,
    status: ToolConnectionStatus = ToolConnectionStatus.ACTIVE,
    secret_version: int = 1,
) -> ToolConnection:
    encrypted, fields = ToolConnectionService._encrypt_config(config or {})
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id if team else None,
        tool_id=tool.id if tool else None,
        scope=ToolConnectionScope.USER,
        owner_user_id=user.id if user else None,
        name=f"connection_{uuid4().hex[:8]}",
        encrypted_config=encrypted,
        secret_fields=fields,
        secret_version=secret_version,
        status=status,
    )


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


def _allow_ssrf(monkeypatch):
    async def allow(url, getaddrinfo=None):
        return url

    monkeypatch.setattr(oauth, "ensure_external_http_url_allowed", allow)
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.test")


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def _resolved(connection: ToolConnection, team_id, user_id, tool_id):
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


def _tokens(**overrides) -> oauth._OAuthTokens:
    values = {
        "access_token": "access",
        "refresh_token": None,
        "token_type": "Bearer",
        "expires_in": 300,
        "scope": (),
        "id_token": None,
    }
    values.update(overrides)
    return oauth._OAuthTokens(**values)


class _MissingRow:
    async def first(self):
        return None


# ---------------------------------------------------------------------------
# Schema validation boundaries
# ---------------------------------------------------------------------------


async def test_provider_schema_rejects_unsafe_url_and_scope_shapes():
    with pytest.raises(ValidationError) as empty_url:
        McpOAuthConfig(authorization_server="   ")
    assert "oauth_url_invalid" in str(empty_url.value)

    with pytest.raises(ValidationError) as long_url:
        McpOAuthConfig(resource="https://as.example.test/" + "a" * 2000)
    assert "oauth_url_invalid" in str(long_url.value)

    for unsafe in (
        "http://as.example.test",
        "https://:443/path",
        "https://user:secret@as.example.test",
    ):
        with pytest.raises(ValidationError) as insecure:
            McpOAuthConfig(resource=unsafe)
        assert "oauth_url_must_be_https" in str(insecure.value)

    with pytest.raises(ValidationError) as too_many_scopes:
        McpOAuthConfig(scopes=[f"scope-{index}" for index in range(51)])
    assert "oauth_scopes_too_many" in str(too_many_scopes.value)

    for invalid_scope in ("bad scope", "", "读", "a" * 201):
        with pytest.raises(ValidationError) as invalid:
            McpOAuthConfig(scopes=[invalid_scope])
        assert "oauth_scope_invalid" in str(invalid.value)

    with pytest.raises(ValidationError) as duplicate_scopes:
        McpOAuthConfig(scopes=["read", " read "])
    assert "oauth_scopes_duplicate" in str(duplicate_scopes.value)

    assert McpOAuthConfig(scopes=[" read ", "write"]).scopes == ["read", "write"]


async def test_provider_schema_rejects_reserved_and_oversized_extra_params():
    with pytest.raises(ValidationError) as too_many:
        McpOAuthConfig(
            extra_authorization_params={f"param{index}": "value" for index in range(21)}
        )
    assert "oauth_extra_params_too_many" in str(too_many.value)

    with pytest.raises(ValidationError) as bad_name:
        McpOAuthConfig(extra_authorization_params={"1state": "value"})
    assert "oauth_extra_param_name_invalid" in str(bad_name.value)

    with pytest.raises(ValidationError) as reserved_authorization:
        McpOAuthConfig(extra_authorization_params={"state": "attacker"})
    assert "oauth_extra_param_reserved" in str(reserved_authorization.value)

    with pytest.raises(ValidationError) as reserved_token:
        McpOAuthConfig(extra_token_params={"code_verifier": "attacker"})
    assert "oauth_extra_param_reserved" in str(reserved_token.value)

    with pytest.raises(ValidationError) as oversized:
        McpOAuthConfig(extra_token_params={"audience": "x" * 501})
    assert "oauth_extra_param_value_invalid" in str(oversized.value)

    http_config = HttpOAuth2Config(
        authorization_endpoint="https://as.example.test/authorize",
        token_endpoint="https://as.example.test/token",
        client_id="client-1",
        extra_authorization_params={"audience": "api"},
        extra_token_params={"audience": "api"},
    )
    assert http_config.extra_authorization_params == {"audience": "api"}
    assert http_config.extra_token_params == {"audience": "api"}

    with pytest.raises(ValidationError) as reserved_http:
        HttpOAuth2Config(
            authorization_endpoint="https://as.example.test/authorize",
            token_endpoint="https://as.example.test/token",
            client_id="client-1",
            extra_token_params={"grant_type": "override"},
        )
    assert "oauth_extra_param_reserved" in str(reserved_http.value)


async def test_provider_schema_accepts_minimal_configs_and_defaults():
    mcp_config = McpOAuthConfig(
        authorization_server=None,
        resource=None,
        client_id=None,
        extra_authorization_params={},
        extra_token_params={},
    )
    assert mcp_config.authorization_server is None
    assert mcp_config.resource is None
    assert mcp_config.client_id is None
    assert mcp_config.extra_authorization_params == {}
    assert mcp_config.extra_token_params == {}

    assert McpOAuthConfig(client_id=" client-1 ").client_id == "client-1"

    http_config = HttpOAuth2Config(
        issuer=None,
        authorization_endpoint="https://as.example.test/authorize",
        token_endpoint="https://as.example.test/token",
        revocation_endpoint=None,
        client_id="client-1",
        extra_authorization_params={},
        extra_token_params={},
    )
    assert http_config.issuer is None
    assert http_config.revocation_endpoint is None
    assert http_config.extra_token_params == {}

    start_request = OAuthStartRequest(redirect_path=None)
    assert start_request.redirect_path is None
    with pytest.raises(ValidationError):
        OAuthStartRequest(client_secret="")


async def test_redirect_path_allowlist_and_length_boundaries():
    assert validate_redirect_path(None) is None
    assert validate_redirect_path("   ") is None
    assert validate_redirect_path("/app") == "/app"
    assert validate_redirect_path("/app/") == "/app/"
    assert validate_redirect_path("/app?tab=oauth") == "/app?tab=oauth"
    assert validate_redirect_path("/settings/profile") == "/settings/profile"
    assert validate_redirect_path("/tools/42") == "/tools/42"

    with pytest.raises(ValueError):
        validate_redirect_path("/app/" + "a" * 500)
    with pytest.raises(ValueError):
        validate_redirect_path("/app\\..\\settings")
    with pytest.raises(ValueError):
        validate_redirect_path("/app/\x00evil")
    for not_allowed in ("/app2", "/application", "/other", "app", "//app"):
        with pytest.raises(ValueError):
            validate_redirect_path(not_allowed)
    with pytest.raises(ValueError) as outside_allowlist:
        validate_redirect_path("/admin")
    assert "oauth_redirect_path_not_allowed" in str(outside_allowlist.value)

    assert OAuthStartRequest(redirect_path="  ").redirect_path is None
    with pytest.raises(ValidationError):
        OAuthStartRequest(redirect_path="/admin")
    with pytest.raises(ValidationError):
        OAuthStartRequest(unknown_field="x")


# ---------------------------------------------------------------------------
# Local URL / flow helpers
# ---------------------------------------------------------------------------


async def test_frontend_url_prefers_site_setting_then_falls_back(monkeypatch):
    async with _database():
        monkeypatch.setattr(settings, "FRONTEND_URL", "https://fallback.example.test")
        setting = await SiteSetting.create(
            id=uuid4(), key="site_url", value="https://site.example.test/"
        )
        assert await oauth._frontend_url() == "https://site.example.test"

        await SiteSetting.filter(id=setting.id).update(value="")
        assert await oauth._frontend_url() == "https://fallback.example.test"


async def test_callback_url_rejects_origin_without_hostname(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://")
    with pytest.raises(BusinessError) as invalid:
        oauth._callback_url()
    assert invalid.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID

    monkeypatch.setattr(settings, "PUBLIC_API_URL", "http://localhost:8000/")
    assert oauth._callback_url() == "http://localhost:8000/api/v1/tool-oauth/callback"


async def test_provider_kind_and_authorization_server_bounds():
    with pytest.raises(BusinessError) as unsupported:
        oauth.ToolOAuthService._provider_kind(Tool(type=ToolType.BUILTIN))
    assert unsupported.value.code == ResponseCode.TOOL_OAUTH_NOT_SUPPORTED

    with pytest.raises(BusinessError) as code_tool:
        oauth.ToolOAuthService._provider_kind(
            Tool(type=ToolType.CUSTOM, custom_type=CustomToolType.CODE)
        )
    assert code_tool.value.code == ResponseCode.TOOL_OAUTH_NOT_SUPPORTED

    with pytest.raises(BusinessError) as too_long:
        oauth.ToolOAuthService._validate_authorization_server("a" * 501)
    assert too_long.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID

    with pytest.raises(BusinessError):
        oauth.ToolOAuthService._validate_authorization_server("")

    oauth.ToolOAuthService._validate_authorization_server(
        "https://as.example.test/tenant"
    )
    assert oauth._as_utc(None) is None


# ---------------------------------------------------------------------------
# Start authorization failure handling
# ---------------------------------------------------------------------------


async def test_start_rejects_row_removed_after_access_check(monkeypatch):
    async with _database():
        admin = await _user("admin")

        async def allow_manage(**kwargs):
            return None

        monkeypatch.setattr(ToolConnectionService, "assert_manage_access", allow_manage)
        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=uuid4()
            )
        assert missing.value.code == ResponseCode.TOOL_CONNECTION_NOT_FOUND


async def test_start_marks_corrupt_connection_for_reauth(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team, tool=tool, user=admin, status=ToolConnectionStatus.ACTIVE
        )
        await ToolConnection.filter(id=connection.id).update(
            encrypted_config="not-a-fernet-token"
        )

        started = await oauth.ToolOAuthService.start_authorization(
            actor=admin, connection_id=connection.id, redirect_path="/app"
        )

        assert started.provider_kind == ToolOAuthProviderKind.HTTP
        assert _query(started.authorization_url)["state"] == [started.state]
        connection = await ToolConnection.get(id=connection.id)
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert await ToolOAuthFlow.filter(connection_id=connection.id).count() == 1


async def test_start_rejects_connection_whose_tool_was_deleted(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team, tool=tool, user=admin, status=ToolConnectionStatus.ACTIVE
        )
        monkeypatch.setattr(
            oauth.Tool, "filter", classmethod(lambda cls, **kwargs: _MissingRow())
        )

        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService.start_authorization(
                actor=admin, connection_id=connection.id
            )
        assert missing.value.code == ResponseCode.TOOL_OAUTH_NOT_SUPPORTED
        assert await ToolOAuthFlow.filter(connection_id=connection.id).count() == 0


# ---------------------------------------------------------------------------
# Status / disconnect tolerance
# ---------------------------------------------------------------------------


async def test_status_tolerates_missing_rows_and_unreadable_secrets(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _connection(
            team=team, tool=tool, user=admin, status=ToolConnectionStatus.ACTIVE
        )

        async def allow_read(**kwargs):
            return None

        monkeypatch.setattr(ToolConnectionService, "get_connection", allow_read)
        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService.get_status(actor=admin, connection_id=uuid4())
        assert missing.value.code == ResponseCode.TOOL_CONNECTION_NOT_FOUND
        monkeypatch.undo()

        await ToolConnection.filter(id=connection.id).update(
            encrypted_config="not-a-fernet-token"
        )
        status = await oauth.ToolOAuthService.get_status(
            actor=admin, connection_id=connection.id
        )
        assert status.authorized is False
        assert status.needs_reauth is True
        assert status.provider_configured is True
        assert status.client_id == provider.client_id

        assert (
            await oauth.ToolOAuthService.get_status(
                actor=admin, connection_id=connection.id
            )
            == status
        )


async def test_disconnect_clears_tokens_even_when_secret_container_is_corrupt(
    monkeypatch,
):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        await _provider_for(tool)
        connection = await _connection(
            team=team, tool=tool, user=admin, status=ToolConnectionStatus.ACTIVE
        )
        await ToolConnection.filter(id=connection.id).update(
            encrypted_config="not-a-fernet-token"
        )

        result = await oauth.ToolOAuthService.disconnect(
            actor=admin, connection_id=connection.id
        )

        assert result.local_revoked is True
        assert result.remote_revocation == "unsupported"
        assert result.needs_reauth is True
        connection = await ToolConnection.get(id=connection.id)
        assert connection.status == ToolConnectionStatus.REAUTH_REQUIRED
        assert connection.secret_version == 1
        assert connection.encrypted_config == ""


async def test_disconnect_rejects_row_removed_after_access_check(monkeypatch):
    async with _database():
        admin = await _user("admin")

        async def allow_manage(**kwargs):
            return None

        monkeypatch.setattr(ToolConnectionService, "assert_manage_access", allow_manage)
        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService.disconnect(actor=admin, connection_id=uuid4())
        assert missing.value.code == ResponseCode.TOOL_CONNECTION_NOT_FOUND


async def test_disconnect_fails_closed_when_row_disappears_under_lock(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        connection = await _connection(
            team=team, tool=tool, user=admin, status=ToolConnectionStatus.ACTIVE
        )
        real_transaction = oauth.in_transaction

        @asynccontextmanager
        async def racing_transaction():
            await ToolConnection.filter(id=connection.id).delete()
            async with real_transaction() as db:
                yield db

        monkeypatch.setattr(oauth, "in_transaction", racing_transaction)

        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService.disconnect(
                actor=admin, connection_id=connection.id
            )
        assert missing.value.code == ResponseCode.TOOL_CONNECTION_NOT_FOUND
        assert await ToolConnection.filter(id=connection.id).exists() is False


# ---------------------------------------------------------------------------
# Provider setup boundaries
# ---------------------------------------------------------------------------


async def test_provider_setup_maps_endpoint_error_to_discovery_failure(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        async def fail(**kwargs):
            raise oauth._OAuthEndpointError("invalid_endpoint")

        monkeypatch.setattr(oauth.ToolOAuthService, "_ensure_http_provider", fail)
        with pytest.raises(BusinessError) as failed:
            await oauth.ToolOAuthService._ensure_provider(
                tool=tool,
                kind=ToolOAuthProviderKind.HTTP,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert failed.value.code == ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED


async def test_http_provider_revocation_endpoint_must_be_https(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(
            team,
            admin,
            oauth2={
                "authorization_endpoint": "https://auth.example.test/authorize",
                "token_endpoint": "https://auth.example.test/token",
                "revocation_endpoint": "https://auth.example.test/revoke",
                "client_id": "client-1",
            },
        )

        setup = await oauth.ToolOAuthService._ensure_http_provider(
            tool=tool,
            redirect_uri="https://api.example.test/callback",
            client_secret=None,
        )
        assert setup.provider.revocation_endpoint == "https://auth.example.test/revoke"

        tool.http_config = {
            **tool.http_config,
            "oauth2": {
                **tool.http_config["oauth2"],
                "revocation_endpoint": "http://auth.example.test/revoke",
            },
        }
        await tool.save()
        with pytest.raises(BusinessError) as insecure:
            await oauth.ToolOAuthService._ensure_http_provider(
                tool=tool,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert insecure.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID


async def test_mcp_provider_rejects_invalid_config_and_metadata(monkeypatch):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)

        reserved = await _mcp_tool(
            team,
            admin,
            oauth_config={"extra_authorization_params": {"state": "attacker"}},
        )
        with pytest.raises(BusinessError) as bad_config:
            await oauth.ToolOAuthService._ensure_mcp_provider(
                tool=reserved,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert bad_config.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID

        discovered = await _mcp_tool(team, admin)

        async def non_string_server(url):
            return {"authorization_servers": [123, "https://as.example.test"]}

        monkeypatch.setattr(
            oauth.ToolOAuthService, "_protected_resource_metadata", non_string_server
        )
        with pytest.raises(BusinessError) as unusable_server:
            await oauth.ToolOAuthService._ensure_mcp_provider(
                tool=discovered,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert unusable_server.value.code == ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED

        configured = await _mcp_tool(
            team,
            admin,
            oauth_config={
                "authorization_server": "https://as.example.test",
                "client_id": "client-1",
            },
        )

        async def bad_challenge_metadata(issuer):
            return {
                "issuer": issuer,
                "authorization_endpoint": "https://as.example.test/authorize",
                "token_endpoint": "https://as.example.test/token",
                "code_challenge_methods_supported": "S256",
            }

        monkeypatch.setattr(
            oauth.ToolOAuthService,
            "_authorization_server_metadata",
            bad_challenge_metadata,
        )
        with pytest.raises(BusinessError) as bad_challenge:
            await oauth.ToolOAuthService._ensure_mcp_provider(
                tool=configured,
                redirect_uri="https://api.example.test/callback",
                client_secret=None,
            )
        assert bad_challenge.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID

        async def good_metadata(issuer):
            return {
                "issuer": issuer,
                "authorization_endpoint": "https://as.example.test/authorize",
                "token_endpoint": "https://as.example.test/token",
                "code_challenge_methods_supported": ["S256"],
            }

        monkeypatch.setattr(
            oauth.ToolOAuthService, "_authorization_server_metadata", good_metadata
        )
        with pytest.raises(BusinessError) as public_client_secret:
            await oauth.ToolOAuthService._ensure_mcp_provider(
                tool=configured,
                redirect_uri="https://api.example.test/callback",
                client_secret="must-not-be-stored",
            )
        assert public_client_secret.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID


async def test_mcp_provider_accepts_empty_challenge_list_and_optional_endpoints(
    monkeypatch,
):
    _allow_ssrf(monkeypatch)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(
            team,
            admin,
            oauth_config={
                "authorization_server": "https://as.example.test/tenant",
                "client_id": "client-1",
                "token_endpoint_auth_method": "none",
            },
        )

        async def metadata(issuer):
            return {
                "issuer": issuer,
                "authorization_endpoint": "https://as.example.test/authorize",
                "token_endpoint": "https://as.example.test/token",
                "userinfo_endpoint": "https://as.example.test/userinfo",
                "revocation_endpoint": "https://as.example.test/revoke",
                "code_challenge_methods_supported": [],
            }

        monkeypatch.setattr(
            oauth.ToolOAuthService, "_authorization_server_metadata", metadata
        )

        setup = await oauth.ToolOAuthService._ensure_mcp_provider(
            tool=tool,
            redirect_uri="https://api.example.test/callback",
            client_secret=None,
        )
        assert setup.provider.code_challenge_methods == ["S256"]
        assert setup.provider.userinfo_endpoint == "https://as.example.test/userinfo"
        assert setup.provider.revocation_endpoint == "https://as.example.test/revoke"
        assert setup.provider.issuer == "https://as.example.test/tenant"


async def test_save_provider_recovers_from_concurrent_unique_conflict(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        existing = await _provider_for(tool)

        async def conflict(self):
            raise IntegrityError("duplicate provider")

        monkeypatch.setattr(ToolOAuthProvider, "save", conflict)
        candidate = ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=existing.provider_kind,
            authorization_server=existing.authorization_server,
            authorization_endpoint="https://as.example.test/authorize",
            token_endpoint="https://as.example.test/token",
            client_id="client-2",
        )
        recovered = await oauth.ToolOAuthService._save_provider(candidate)
        assert recovered.id == existing.id
        assert recovered.client_id == existing.client_id

        orphan = ToolOAuthProvider(
            id=uuid4(),
            tool_id=tool.id,
            provider_kind=existing.provider_kind,
            authorization_server="https://other.example.test",
            authorization_endpoint="https://other.example.test/authorize",
            token_endpoint="https://other.example.test/token",
            client_id="client-3",
        )
        with pytest.raises(IntegrityError):
            await oauth.ToolOAuthService._save_provider(orphan)


# ---------------------------------------------------------------------------
# Discovery metadata
# ---------------------------------------------------------------------------


async def test_protected_resource_metadata_falls_back_and_fails_closed(monkeypatch):
    async def probe(mcp_url):
        return "https://mcp.example.test/header-metadata"

    monkeypatch.setattr(oauth.ToolOAuthService, "_probe_resource_metadata_url", probe)
    seen: list[str] = []

    async def try_json(url):
        seen.append(url)
        if "header-metadata" in url:
            return None
        if url.endswith("/oauth-protected-resource/mcp"):
            return {"resource": "https://mcp.example.test/mcp"}
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_try_json", try_json)
    metadata = await oauth.ToolOAuthService._protected_resource_metadata(
        "https://mcp.example.test/mcp"
    )
    assert metadata == {"resource": "https://mcp.example.test/mcp"}
    assert seen == [
        "https://mcp.example.test/header-metadata",
        "https://mcp.example.test/.well-known/oauth-protected-resource/mcp",
    ]

    async def no_metadata(url):
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_try_json", no_metadata)
    with pytest.raises(BusinessError) as missing:
        await oauth.ToolOAuthService._protected_resource_metadata(
            "https://mcp.example.test/mcp"
        )
    assert missing.value.code == ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED


async def test_authorization_server_metadata_tries_path_scoped_candidates(
    monkeypatch,
):
    seen: list[str] = []

    async def try_json(url):
        seen.append(url)
        if (
            url
            == "https://as.example.test/.well-known/oauth-authorization-server/tenant"
        ):
            return None
        if url == "https://as.example.test/tenant/.well-known/openid-configuration":
            return {"issuer": "https://as.example.test/tenant/"}
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_try_json", try_json)
    metadata = await oauth.ToolOAuthService._authorization_server_metadata(
        "https://as.example.test/tenant"
    )
    assert metadata["issuer"] == "https://as.example.test/tenant/"
    assert seen == [
        "https://as.example.test/.well-known/oauth-authorization-server/tenant",
        "https://as.example.test/tenant/.well-known/openid-configuration",
    ]

    async def no_metadata(url):
        return None

    monkeypatch.setattr(oauth.ToolOAuthService, "_try_json", no_metadata)
    with pytest.raises(BusinessError) as missing:
        await oauth.ToolOAuthService._authorization_server_metadata(
            "https://as.example.test/tenant"
        )
    assert missing.value.code == ResponseCode.TOOL_OAUTH_DISCOVERY_FAILED


async def test_probe_ignores_non_bearer_and_insecure_metadata_hints(monkeypatch):
    _allow_ssrf(monkeypatch)
    handler_holder: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        return real_client(
            transport=httpx.MockTransport(handler_holder["handler"]),
            follow_redirects=False,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, content=b"not a challenge")
        return httpx.Response(401, headers={"www-authenticate": 'Basic realm="mcp"'})

    handler_holder["handler"] = handler
    assert (
        await oauth.ToolOAuthService._probe_resource_metadata_url(
            "https://mcp.example.test/mcp"
        )
        is None
    )

    def insecure_handler(request):
        return httpx.Response(
            401,
            headers={
                "www-authenticate": (
                    'Bearer resource_metadata="http://insecure.example/metadata"'
                )
            },
        )

    handler_holder["handler"] = insecure_handler
    assert (
        await oauth.ToolOAuthService._probe_resource_metadata_url(
            "https://mcp.example.test/mcp"
        )
        is None
    )


# ---------------------------------------------------------------------------
# Client authentication / token parsing
# ---------------------------------------------------------------------------


async def test_client_auth_rejects_unusable_client_secret(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)

        basic = await _provider_for(
            tool,
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_BASIC,
            client_secret_encrypted="",
        )
        with pytest.raises(BusinessError) as missing_basic:
            oauth.ToolOAuthService._client_auth(basic)
        assert missing_basic.value.code == ResponseCode.TOOL_OAUTH_CONFIG_INVALID
        assert missing_basic.value.msg_key == "tool_oauth_client_secret_required"

        post = await _provider_for(
            tool,
            authorization_server="https://post.example.test",
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_POST,
            client_secret_encrypted="",
        )
        with pytest.raises(BusinessError) as missing_post:
            oauth.ToolOAuthService._client_auth(post)
        assert missing_post.value.msg_key == "tool_oauth_client_secret_required"

        unreadable = await _provider_for(
            tool,
            authorization_server="https://broken.example.test",
            token_endpoint_auth_method=ToolOAuthClientAuthMethod.CLIENT_SECRET_POST,
            client_secret_encrypted="not-a-fernet-token",
        )
        with pytest.raises(BusinessError) as broken:
            oauth.ToolOAuthService._client_auth(unreadable)
        assert broken.value.code == ResponseCode.TOOL_CONNECTION_SECRET_UNREADABLE


async def test_token_response_rejects_invalid_refresh_and_ignores_bad_id_token():
    for refresh_token in (
        5,
        "",
        "r" * (oauth.MAX_REFRESH_TOKEN_LENGTH + 1),
    ):
        with pytest.raises(oauth._OAuthEndpointError) as invalid:
            oauth.ToolOAuthService._parse_token_response(
                {
                    "access_token": "access",
                    "expires_in": 60,
                    "refresh_token": refresh_token,
                }
            )
        assert invalid.value.error == "invalid_refresh_token"

    for id_token in (5, "x" * 32769):
        tokens = oauth.ToolOAuthService._parse_token_response(
            {"access_token": "access", "expires_in": 60, "id_token": id_token}
        )
        assert tokens.id_token is None

    tokens = oauth.ToolOAuthService._parse_token_response(
        {
            "access_token": "access",
            "expires_in": 60,
            "refresh_token": "refresh",
            "id_token": "eyJhbGciOiJub25lIn0.e30.sig",
        }
    )
    assert tokens.refresh_token == "refresh"
    assert tokens.id_token == "eyJhbGciOiJub25lIn0.e30.sig"


# ---------------------------------------------------------------------------
# Refresh / binding boundaries
# ---------------------------------------------------------------------------


async def test_refresh_for_mcp_sends_resource_and_uses_provider_scopes(monkeypatch):
    _allow_ssrf(monkeypatch)
    captured: dict[str, str] = {}

    async def fake_request_token(provider, data):
        captured.update(data)
        return _tokens(access_token="new-access", expires_in=900)

    monkeypatch.setattr(oauth.ToolOAuthService, "_request_token", fake_request_token)
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _mcp_tool(team, admin)
        provider = await _provider_for(
            tool,
            provider_kind=ToolOAuthProviderKind.MCP,
            resource="https://mcp.example.test/mcp",
            scopes=["read", "write"],
        )
        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            config={
                "oauth_access_token": "old-access",
                "oauth_expires_at": (now_utc() - timedelta(seconds=30)).isoformat(),
                "oauth_refresh_token": "refresh-old",
                "oauth_provider_id": str(provider.id),
            },
        )

        token = await oauth.ToolOAuthService.get_access_token(
            _resolved(connection, team.id, admin.id, tool.id)
        )

        assert token == "new-access"
        assert captured["grant_type"] == "refresh_token"
        assert captured["resource"] == "https://mcp.example.test/mcp"
        connection = await ToolConnection.get(id=connection.id)
        config = ToolConnectionService._decrypt_config(connection)
        assert config["oauth_scope"] == "read write"


async def test_provider_for_connection_falls_back_and_fails_closed(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        connection = await _connection(
            team=team,
            tool=tool,
            user=admin,
            config={"oauth_provider_id": "not-a-uuid"},
        )
        config = ToolConnectionService._decrypt_config(connection)

        assert (
            await oauth.ToolOAuthService._provider_for_connection(connection, config)
        ).id == provider.id

        builtin_connection = await _connection(team=team, user=admin)
        assert (
            await oauth.ToolOAuthService._provider_for_connection(
                builtin_connection, {"oauth_provider_id": "not-a-uuid"}
            )
            is None
        )


async def test_store_tokens_rejects_missing_revoked_or_stale_connections():
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(tool)
        tokens = _tokens(access_token="new-access")

        with pytest.raises(BusinessError) as missing:
            await oauth.ToolOAuthService._store_tokens(
                connection_id=uuid4(),
                provider=provider,
                tokens=tokens,
                expected_secret_version=1,
                allowed_scopes={"read"},
                bump_version=False,
                allow_userinfo=False,
            )
        assert missing.value.code == ResponseCode.TOOL_CONNECTION_NOT_FOUND

        revoked = await _connection(
            team=team,
            tool=tool,
            user=admin,
            status=ToolConnectionStatus.REVOKED,
            secret_version=1,
        )
        with pytest.raises(BusinessError) as inactive:
            await oauth.ToolOAuthService._store_tokens(
                connection_id=revoked.id,
                provider=provider,
                tokens=tokens,
                expected_secret_version=1,
                allowed_scopes={"read"},
                bump_version=False,
                allow_userinfo=False,
            )
        assert inactive.value.code == ResponseCode.TOOL_CONNECTION_INACTIVE

        stale = await _connection(
            team=team,
            tool=tool,
            user=admin,
            status=ToolConnectionStatus.ACTIVE,
            secret_version=1,
        )
        with pytest.raises(BusinessError) as conflict:
            await oauth.ToolOAuthService._store_tokens(
                connection_id=stale.id,
                provider=provider,
                tokens=tokens,
                expected_secret_version=2,
                allowed_scopes={"read"},
                bump_version=False,
                allow_userinfo=False,
            )
        assert conflict.value.code == ResponseCode.TOOL_CONNECTION_INVALID


async def test_resolve_identity_uses_userinfo_only_for_silent_tokens(monkeypatch):
    async with _database():
        admin = await _user("admin")
        team = await _team(admin)
        tool = await _http_tool(team, admin)
        provider = await _provider_for(
            tool, userinfo_endpoint="https://as.example.test/userinfo"
        )
        requests: list[dict] = []

        async def userinfo(url, *, method, headers=None, **kwargs):
            requests.append(
                {"url": url, "method": method, "headers": dict(headers or {})}
            )
            return {"sub": "external-1", "email": "user@example.test"}

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", userinfo)
        assert await oauth.ToolOAuthService._resolve_identity(
            provider, _tokens(access_token="access"), allow_userinfo=True
        ) == ("external-1", "user@example.test")
        assert requests[0]["url"] == "https://as.example.test/userinfo"
        assert requests[0]["headers"]["Authorization"] == "Bearer access"

        async def broken_userinfo(url, **kwargs):
            raise RuntimeError("userinfo unavailable")

        monkeypatch.setattr(oauth.ToolOAuthService, "_http_json", broken_userinfo)
        assert await oauth.ToolOAuthService._resolve_identity(
            provider, _tokens(access_token="access"), allow_userinfo=True
        ) == (None, None)


async def test_personal_flow_actor_skips_membership_and_superuser_bypasses(
    monkeypatch,
):
    async with _database():
        owner = await _user("owner")
        personal_flow = ToolOAuthFlow(user_id=owner.id, team_id=None)
        await oauth.ToolOAuthService._validate_flow_actor(personal_flow)

        superuser = await _user("root", superuser=True)
        team = await _team(owner)
        team_flow = ToolOAuthFlow(user_id=superuser.id, team_id=team.id)
        await oauth.ToolOAuthService._validate_flow_actor(team_flow)

        outsider = await _user("outsider")
        with pytest.raises(BusinessError) as denied:
            await oauth.ToolOAuthService._validate_flow_actor(
                ToolOAuthFlow(user_id=outsider.id, team_id=team.id)
            )
        assert denied.value.code == ResponseCode.TOOL_OAUTH_STATE_INVALID
