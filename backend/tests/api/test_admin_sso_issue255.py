from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import integrations
from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value=None):
        self.value = value

    async def first(self):
        return self.value

    def prefetch_related(self, *_relations):
        return self

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


def integration(provider_type="oidc", **overrides):
    values = dict(
        id=uuid4(),
        name="company-oidc",
        provider_type=provider_type,
        display_name="Company",
        icon_url=None,
        button_text=None,
        config={"issuer": "https://id.example.com"},
        credentials={},
        attribute_mapping={},
        is_enabled=True,
        enabled_capabilities=["user_login"]
        if provider_type == "oidc"
        else ["notification"],
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


def create_data(**overrides):
    return IntegrationCreate(
        name="company-oidc",
        provider_type="oidc",
        display_name="Company",
        **overrides,
    )


@pytest.fixture(autouse=True)
def no_audit_writes(monkeypatch):
    monkeypatch.setattr(integrations.AuditLogService, "log", AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("domain,expected", [("login", "oidc"), ("settings", "email")])
async def test_list_and_catalog_filter_management_domains(
    monkeypatch, domain, expected
):
    items = [integration(), integration("email")]
    monkeypatch.setattr(integrations.Integration, "all", AsyncMock(return_value=items))
    current = user(f"admin:integrations:{domain}:read")
    result = await integrations.list_integrations(current)
    assert [item.provider_type for item in result["data"]] == [expected]
    catalog = (await integrations.list_integration_types(current))["data"]
    catalog_types = {item.provider_type for item in catalog}
    assert catalog
    assert expected in catalog_types
    # A login-capable type is not automatically login-domain-only: Feishu is a
    # builtin that also provides sign-in, so both domains may read it.
    assert ("feishu" in catalog_types) is True
    assert ("oidc" in catalog_types) == (domain == "login")
    assert ("email" in catalog_types) == (domain == "settings")


@pytest.mark.asyncio
async def test_list_denies_unprivileged_user(monkeypatch):
    query = AsyncMock()
    monkeypatch.setattr(integrations.Integration, "all", query)
    with pytest.raises(BusinessError) as exc:
        await integrations.list_integrations(user())
    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_encrypts_credentials_and_redacts_response_audit(monkeypatch):
    item = integration(credentials={"client_secret": encrypt_secret("sensitive")})
    create = AsyncMock(return_value=item)
    monkeypatch.setattr(
        integrations.Integration, "filter", MagicMock(return_value=Query())
    )
    monkeypatch.setattr(integrations.Integration, "create", create)
    result = await integrations.create_integration(
        MagicMock(),
        create_data(credentials={"client_secret": "sensitive"}),
        user("admin:integrations:login:update"),
    )
    assert (
        decrypt_secret(create.await_args.kwargs["credentials"]["client_secret"])
        == "sensitive"
    )
    assert result["data"].credentials_configured == ["client_secret"]
    assert "credentials" not in result["data"].model_dump()
    assert "sensitive" not in repr(integrations.AuditLogService.log.await_args)
    assert (
        "credentials"
        not in integrations.AuditLogService.log.await_args.kwargs["changes"]["after"]
    )


@pytest.mark.asyncio
async def test_create_rejects_duplicate_name(monkeypatch):
    monkeypatch.setattr(
        integrations.Integration, "filter", MagicMock(return_value=Query(integration()))
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.create_integration(
            MagicMock(), create_data(), user("admin:integrations:login:update")
        )
    assert exc.value.code == ResponseCode.SSO_PROVIDER_NAME_EXISTS


@pytest.mark.asyncio
async def test_update_preserves_blank_secret_and_merges_login_policy(monkeypatch):
    ciphertext = encrypt_secret("old-secret")
    item = integration(credentials={"client_secret": ciphertext})
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    result = await integrations.update_integration(
        item.id,
        MagicMock(),
        IntegrationUpdate(
            display_name="New",
            credentials={"client_secret": ""},
            login_config={"require_approval": True},
        ),
        user("admin:integrations:login:update"),
    )
    assert item.credentials["client_secret"] == ciphertext
    assert item.login_config == {
        "allow_signup": True,
        "require_approval": True,
        "default_role_id": None,
    }
    assert result["data"].display_name == "New"
    item.save.assert_awaited_once()
    assert "old-secret" not in repr(integrations.AuditLogService.log.await_args)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"enabled_capabilities": ["directory_sync"]},
        {"provider_type": "feishu"},
        {"provider_type": "unknown"},
        {"config": {"client_secret": "secret"}},
        {"credentials": {"wrong_secret": "secret"}},
        {"display_name": None},
        {"name": None},
        {"provider_type": None},
        {"config": None},
        {"credentials": None},
        {"login_config": None},
        {"attribute_mapping": None},
        {"enabled_capabilities": None},
        {"is_enabled": None},
    ],
)
async def test_update_rejects_invalid_capabilities_config_and_type(
    monkeypatch, payload
):
    item = integration()
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            item.id,
            MagicMock(),
            IntegrationUpdate(**payload),
            user("admin:integrations:login:update"),
        )
    assert exc.value.code == ResponseCode.VALIDATION_ERROR
    item.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_builtin_update_requires_settings_domain_and_disallows_login_policy(
    monkeypatch,
):
    item = integration("email")
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            item.id,
            MagicMock(),
            IntegrationUpdate(is_enabled=False),
            user("admin:integrations:login:update"),
        )
    assert exc.value.code == ResponseCode.PERMISSION_DENIED
    await integrations.update_integration(
        item.id,
        MagicMock(),
        IntegrationUpdate(is_enabled=False),
        user("admin:integrations:settings:update"),
    )
    assert not item.is_enabled
    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            item.id,
            MagicMock(),
            IntegrationUpdate(login_config={"allow_signup": False}),
            user("admin:integrations:settings:update"),
        )
    assert exc.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_builtin_delete_is_forbidden(monkeypatch):
    item = integration("email")
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.delete_integration(
            item.id, MagicMock(), user("admin:integrations:settings:update")
        )
    assert exc.value.msg_key == "integration_builtin_cannot_delete"
    item.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_login_integration_audits_safe_snapshot(monkeypatch):
    item = integration()
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    await integrations.delete_integration(
        item.id, MagicMock(), user("admin:integrations:login:update")
    )
    item.delete.assert_awaited_once()
    assert (
        integrations.AuditLogService.log.await_args.kwargs["resource_type"]
        == "integration"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result", [("https://example.com/secret", "pkce", "nonce"), "bad-response"]
)
async def test_connection_test_never_returns_authorization_url(monkeypatch, result):
    item = integration()
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    monkeypatch.setattr(
        integrations.SSOService,
        "get_provider_instance",
        MagicMock(
            return_value=SimpleNamespace(
                get_authorization_url=AsyncMock(return_value=result)
            )
        ),
    )
    response = await integrations.test_integration_connection(
        item.id, MagicMock(), user("admin:integrations:login:update")
    )
    assert response["data"]["status"] == (
        "success" if isinstance(result, tuple) else "error"
    )
    assert "authorization_url" not in response["data"]


@pytest.mark.asyncio
async def test_connection_test_redacts_exception_audit(monkeypatch):
    item = integration()
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    monkeypatch.setattr(
        integrations.SSOService,
        "get_provider_instance",
        MagicMock(side_effect=ValueError("credential-secret")),
    )
    await integrations.test_integration_connection(
        item.id, MagicMock(), user("admin:integrations:login:update")
    )
    assert "credential-secret" not in repr(integrations.AuditLogService.log.await_args)


@pytest.mark.asyncio
async def test_admin_disconnect_preserves_only_authentication_method(monkeypatch):
    target = SimpleNamespace(id=uuid4(), hashed_password="")
    connection = SimpleNamespace(
        user=target, integration=SimpleNamespace(name="Company"), delete=AsyncMock()
    )
    monkeypatch.setattr(
        integrations.UserSSOConnection,
        "get_or_none",
        MagicMock(return_value=Query(connection)),
    )
    monkeypatch.setattr(
        integrations.UserSSOConnection,
        "filter",
        MagicMock(return_value=SimpleNamespace(count=AsyncMock(return_value=1))),
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.admin_disconnect_sso(
            uuid4(), MagicMock(), user("admin:integrations:login:update")
        )
    assert exc.value.code == ResponseCode.FORBIDDEN
    connection.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_duplicate_race_is_reported_as_name_conflict(monkeypatch):
    from tortoise.exceptions import IntegrityError

    monkeypatch.setattr(
        integrations.Integration,
        "filter",
        MagicMock(
            return_value=SimpleNamespace(
                first=AsyncMock(return_value=None), exists=AsyncMock(return_value=True)
            )
        ),
    )
    monkeypatch.setattr(
        integrations.Integration,
        "create",
        AsyncMock(side_effect=IntegrityError("unique constraint")),
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.create_integration(
            MagicMock(), create_data(), user("admin:integrations:login:update")
        )
    assert exc.value.msg_key == "integration_name_exists"


@pytest.mark.asyncio
async def test_update_duplicate_race_is_reported_as_name_conflict(monkeypatch):
    from tortoise.exceptions import IntegrityError

    item = integration(save=AsyncMock(side_effect=IntegrityError("unique constraint")))
    query = SimpleNamespace(
        first=AsyncMock(return_value=None),
        exclude=MagicMock(
            return_value=SimpleNamespace(exists=AsyncMock(return_value=True))
        ),
    )
    monkeypatch.setattr(
        integrations.Integration, "get_or_none", AsyncMock(return_value=item)
    )
    monkeypatch.setattr(
        integrations.Integration, "filter", MagicMock(return_value=query)
    )
    with pytest.raises(BusinessError) as exc:
        await integrations.update_integration(
            item.id,
            MagicMock(),
            IntegrationUpdate(name="raced-name"),
            user("admin:integrations:login:update"),
        )
    assert exc.value.msg_key == "integration_name_exists"
