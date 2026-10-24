from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import integrations
from app.api.v1.endpoints import sso as sso_endpoints
from app.integrations.credentials import encrypt_secret
from app.schemas.integration import IntegrationUpdate
from app.schemas.response import BusinessError, ResponseCode
from app.services import integration_config


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value

    async def all(self):
        return self.value

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


def row(provider_type, **overrides):
    capabilities = {
        "oidc": ["user_login"],
        "email": ["notification"],
        "feishu": ["directory_sync"],
    }[provider_type]
    values = dict(
        id=uuid4(),
        name=provider_type,
        provider_type=provider_type,
        display_name=provider_type,
        icon_url=None,
        button_text=None,
        config={},
        credentials={},
        attribute_mapping={},
        is_enabled=True,
        enabled_capabilities=capabilities,
        login_config={
            "allow_signup": True,
            "require_approval": False,
            "default_role_id": None,
        },
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def feishu(**overrides):
    values = dict(
        name="feishu",
        display_name="Feishu",
        config={"app_id": "cli_1", "department_ids": []},
        credentials={"app_secret": encrypt_secret("secret")},
    )
    values.update(overrides)
    return row("feishu", **values)


def user(*permissions):
    return SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        roles=[
            SimpleNamespace(
                permissions=[SimpleNamespace(code=code) for code in permissions]
            )
        ],
    )


settings_admin = user(
    "admin:integrations:settings:read", "admin:integrations:settings:update"
)
login_admin = user("admin:integrations:login:read", "admin:integrations:login:update")


@pytest.fixture(autouse=True)
def no_audit_writes(monkeypatch):
    monkeypatch.setattr(integrations.AuditLogService, "log", AsyncMock())


def test_feishu_answers_to_both_management_domains():
    assert integrations._domains("feishu") == ("settings", "login")
    assert integrations._domains("oidc") == ("login",)
    assert integrations._domains("email") == ("settings",)


def test_update_domains_are_charged_per_field():
    instance = feishu()

    assert integrations._required_domains(instance, {"config": {"app_id": "x"}}) == {
        "settings"
    }
    assert integrations._required_domains(
        instance, {"credentials": {"app_secret": "x"}}
    ) == {"settings"}
    # Opting into login is a login-domain change even when the payload re-sends
    # the capability that is already on.
    assert integrations._required_domains(
        instance, {"enabled_capabilities": ["directory_sync", "user_login"]}
    ) == {"login"}
    # Dropping the directory capability is a settings-domain change.
    assert integrations._required_domains(
        instance, {"enabled_capabilities": ["user_login"]}
    ) == {
        "settings",
        "login",
    }
    # A no-op capability list cannot be used to bypass authorization.
    assert integrations._required_domains(
        instance, {"enabled_capabilities": ["directory_sync"]}
    ) == {
        "settings",
        "login",
    }
    # The instance master switch gates every capability it carries.
    assert integrations._required_domains(instance, {"is_enabled": False}) == {
        "settings",
        "login",
    }
    assert integrations._required_domains(instance, {"button_text": "Sign in"}) == {
        "login"
    }
    assert integrations._required_domains(instance, {"login_config": {}}) == {"login"}
    # Single-domain types keep today's behavior.
    assert integrations._required_domains(
        SimpleNamespace(provider_type="oidc", enabled_capabilities=["user_login"]),
        {"config": {}},
    ) == {"login"}
    assert integrations._required_domains(
        SimpleNamespace(provider_type="oidc", enabled_capabilities=["user_login"]),
        {"is_enabled": False},
    ) == {"login"}
    assert integrations._required_domains(
        SimpleNamespace(provider_type="email", enabled_capabilities=["notification"]),
        {"is_enabled": False},
    ) == {"settings"}


@pytest.mark.asyncio
async def test_settings_admin_cannot_opt_feishu_into_login(monkeypatch):
    instance = feishu()
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )

    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            instance.id,
            MagicMock(),
            IntegrationUpdate(enabled_capabilities=["user_login"]),
            settings_admin,
        )

    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    instance.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_admin_cannot_rewrite_builtin_credentials(monkeypatch):
    instance = feishu()
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )

    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            instance.id,
            MagicMock(),
            IntegrationUpdate(config={"app_id": "cli_other"}),
            login_admin,
        )

    assert exc.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_login_admin_opts_feishu_into_login_without_dropping_directory_sync(
    monkeypatch,
):
    instance = feishu()
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )

    result = await integrations.update_integration(
        instance.id,
        MagicMock(),
        IntegrationUpdate(
            enabled_capabilities=["directory_sync", "user_login"],
            button_text="Sign in with Feishu",
        ),
        login_admin,
    )

    assert instance.enabled_capabilities == ["directory_sync", "user_login"]
    assert instance.button_text == "Sign in with Feishu"
    assert result["data"].enabled_capabilities == ["directory_sync", "user_login"]
    instance.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_settings_admin_still_configures_the_feishu_app(monkeypatch):
    instance = feishu()
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )

    result = await integrations.update_integration(
        instance.id,
        MagicMock(),
        IntegrationUpdate(config={"app_id": "cli_2", "department_ids": ["od_1"]}),
        settings_admin,
    )

    assert instance.config == {"app_id": "cli_2", "department_ids": ["od_1"]}
    assert result["data"].provider_type == "feishu"


@pytest.mark.asyncio
async def test_login_test_requires_the_login_domain(monkeypatch):
    instance = feishu(enabled_capabilities=["directory_sync", "user_login"])
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )

    with pytest.raises(BusinessError) as exc:
        await integrations.test_integration_connection(
            instance.id, MagicMock(), settings_admin
        )
    assert exc.value.code == ResponseCode.PERMISSION_DENIED

    checked = await integrations.test_integration_connection(
        instance.id, MagicMock(), login_admin
    )
    assert checked["data"]["status"] == "success"


@pytest.mark.asyncio
async def test_login_readers_see_feishu_but_only_their_own_domains(monkeypatch):
    items = [feishu(), row("email"), row("oidc")]
    monkeypatch.setattr(integrations.Integration, "all", AsyncMock(return_value=items))

    login_only = await integrations.list_integrations(
        user("admin:integrations:login:read")
    )
    assert {item.provider_type for item in login_only["data"]} == {"feishu", "oidc"}

    settings_only = await integrations.list_integrations(
        user("admin:integrations:settings:read")
    )
    assert {item.provider_type for item in settings_only["data"]} == {"feishu", "email"}


def test_feishu_is_login_capable_only_when_opted_in():
    assert not sso_endpoints._supports_login(feishu())
    assert sso_endpoints._supports_login(
        feishu(enabled_capabilities=["directory_sync", "user_login"])
    )


@pytest.mark.asyncio
async def test_public_listing_only_offers_enabled_login_integrations(monkeypatch):
    login_feishu = feishu(enabled_capabilities=["directory_sync", "user_login"])
    monkeypatch.setattr(
        sso_endpoints.SiteSetting, "get_value", AsyncMock(return_value=True)
    )
    query = MagicMock(return_value=Query([login_feishu]))
    monkeypatch.setattr(sso_endpoints.Integration, "filter", query)

    listing = await sso_endpoints.list_public_integrations()

    assert query.call_args.kwargs["is_enabled"] is True
    assert [item.provider_type for item in listing["data"]] == ["feishu"]
    assert "config" not in listing["data"][0].model_dump()
    assert "app_id" not in str(listing["data"][0].model_dump())


@pytest.mark.asyncio
async def test_public_listing_is_empty_while_sso_is_disabled(monkeypatch):
    monkeypatch.setattr(
        sso_endpoints.SiteSetting, "get_value", AsyncMock(return_value=False)
    )
    query = MagicMock()
    monkeypatch.setattr(sso_endpoints.Integration, "filter", query)

    listing = await sso_endpoints.list_public_integrations()

    assert listing["data"] == []
    query.assert_not_called()


@pytest.mark.asyncio
async def test_enabling_the_builtin_never_grants_login(monkeypatch):
    instance = feishu(enabled_capabilities=[])
    monkeypatch.setattr(
        integration_config, "get_builtin_integration", AsyncMock(return_value=instance)
    )

    await integration_config.update_builtin_config("feishu", {}, enabled=True)

    assert instance.enabled_capabilities == ["directory_sync"]


@pytest.mark.asyncio
async def test_disabling_the_builtin_keeps_the_login_opt_in_inert(monkeypatch):
    instance = feishu(enabled_capabilities=["directory_sync", "user_login"])
    monkeypatch.setattr(
        integration_config, "get_builtin_integration", AsyncMock(return_value=instance)
    )

    await integration_config.update_builtin_config("feishu", {}, enabled=False)

    assert instance.is_enabled is False
    assert instance.enabled_capabilities == ["user_login"]


@pytest.mark.asyncio
async def test_sso_login_dispatches_feishu_through_the_pkce_branch(monkeypatch):
    instance = feishu(enabled_capabilities=["directory_sync", "user_login"])
    monkeypatch.setattr(
        sso_endpoints.Integration, "get_or_none", AsyncMock(return_value=instance)
    )
    monkeypatch.setattr(sso_endpoints.SSOSession, "create", AsyncMock())
    monkeypatch.setattr(
        sso_endpoints, "_backend_url", lambda _request: "https://api.example"
    )
    monkeypatch.setattr(
        "app.sso.providers.feishu.exchange_user_access_token",
        AsyncMock(return_value="u-token"),
    )
    request = MagicMock()
    request.base_url = "https://api.example/"

    response = await sso_endpoints.sso_login("feishu", request, redirect="/app/kb")

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith(
        "https://accounts.feishu.cn/open-apis/authen/v1/authorize?"
    )
    assert "code_challenge_method=S256" in location
    session = sso_endpoints.SSOSession.create.await_args.kwargs
    assert session["integration"] is instance
    assert session["code_verifier"]
    assert session["redirect_url"] == "/app/kb"


@pytest.mark.asyncio
async def test_sso_login_ignores_feishu_without_the_login_capability(monkeypatch):
    instance = feishu()
    monkeypatch.setattr(
        sso_endpoints.Integration, "get_or_none", AsyncMock(return_value=instance)
    )
    monkeypatch.setattr(
        sso_endpoints,
        "SiteSetting",
        SimpleNamespace(get_value=AsyncMock(return_value="")),
    )

    request = MagicMock()
    request.base_url = "https://api.example/"

    response = await sso_endpoints.sso_login("feishu", request, redirect=None)

    assert "error=sso_provider_not_found" in response.headers["location"]
