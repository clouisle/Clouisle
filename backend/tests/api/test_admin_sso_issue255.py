from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import sso
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.sso import SSOProviderCreate, SSOProviderUpdate


class Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.count_result = count

    def prefetch_related(self, *args):
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.count_result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def provider(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "name": "company-oidc",
        "protocol": "oidc",
        "display_name": "Company",
        "icon_url": None,
        "button_text": None,
        "config": {"issuer": "https://id.example.com"},
        "attribute_mapping": {},
        "is_enabled": True,
        "allow_signup": True,
        "require_approval": False,
        "default_role_id": None,
        "created_at": now,
        "updated_at": now,
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_data():
    return SSOProviderCreate(
        name="company-oidc",
        protocol="oidc",
        display_name="Company",
        config={"issuer": "https://id.example.com"},
    )


@pytest.mark.anyio
async def test_list_and_create_provider(monkeypatch):
    item, user, audit = provider(), SimpleNamespace(id=uuid4()), AsyncMock()
    monkeypatch.setattr(sso.SSOProvider, "all", AsyncMock(return_value=[item]))
    assert (await sso.list_providers_admin(user))["data"][0].id == item.id
    monkeypatch.setattr(sso.SSOProvider, "filter", MagicMock(return_value=Query()))
    monkeypatch.setattr(sso.SSOProvider, "create", AsyncMock(return_value=item))
    monkeypatch.setattr(sso.AuditLogService, "log", audit)
    assert (await sso.create_provider(MagicMock(), create_data(), user))[
        "data"
    ].name == item.name
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_create_rejects_duplicate_name(monkeypatch):
    monkeypatch.setattr(
        sso.SSOProvider, "filter", MagicMock(return_value=Query(provider()))
    )
    with pytest.raises(BusinessError) as caught:
        await sso.create_provider(MagicMock(), create_data(), SimpleNamespace())
    assert caught.value.code == ResponseCode.SSO_PROVIDER_NAME_EXISTS


@pytest.mark.anyio
async def test_update_validates_identity_and_persists_fields(monkeypatch):
    item, audit = provider(), AsyncMock()
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(side_effect=[None, item, item])
    )
    with pytest.raises(BusinessError) as missing:
        await sso.update_provider(
            uuid4(),
            MagicMock(),
            SSOProviderUpdate(display_name="New"),
            SimpleNamespace(),
        )
    assert missing.value.code == ResponseCode.SSO_PROVIDER_NOT_FOUND
    monkeypatch.setattr(
        sso.SSOProvider, "filter", MagicMock(return_value=Query(provider()))
    )
    with pytest.raises(BusinessError) as duplicate:
        await sso.update_provider(
            item.id,
            MagicMock(),
            SSOProviderUpdate(name="other-oidc"),
            SimpleNamespace(),
        )
    assert duplicate.value.code == ResponseCode.SSO_PROVIDER_NAME_EXISTS
    monkeypatch.setattr(sso.AuditLogService, "log", audit)
    result = await sso.update_provider(
        item.id,
        MagicMock(),
        SSOProviderUpdate(display_name="New", is_enabled=False),
        SimpleNamespace(id=uuid4()),
    )
    assert (item.display_name, item.is_enabled) == ("New", False)
    item.save.assert_awaited_once()
    assert result["data"].display_name == "New"
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_handles_missing_and_success(monkeypatch):
    item, audit = provider(), AsyncMock()
    monkeypatch.setattr(
        sso.SSOProvider, "get_or_none", AsyncMock(side_effect=[None, item])
    )
    monkeypatch.setattr(sso.AuditLogService, "log", audit)
    with pytest.raises(BusinessError) as missing:
        await sso.delete_provider(uuid4(), MagicMock(), SimpleNamespace())
    assert missing.value.code == ResponseCode.SSO_PROVIDER_NOT_FOUND
    assert (await sso.delete_provider(item.id, MagicMock(), SimpleNamespace()))[
        "code"
    ] == 0
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_connection_test_covers_success_and_safe_failure(monkeypatch):
    item = provider()
    instance = SimpleNamespace(
        get_authorization_url=AsyncMock(
            return_value=("https://id.example.com/authorize", "verifier", "challenge")
        )
    )
    monkeypatch.setattr(sso.SSOProvider, "get_or_none", AsyncMock(return_value=item))
    monkeypatch.setattr(
        sso.SSOService, "get_provider_instance", MagicMock(return_value=instance)
    )
    result = await sso.test_provider_connection(
        item.id, MagicMock(), SimpleNamespace(id=uuid4())
    )
    assert result["data"]["status"] == "success"
    assert result["data"]["authorization_url"].endswith("...")
    instance.get_authorization_url.return_value = ("url", "only-two")
    audit = AsyncMock()
    monkeypatch.setattr(sso.AuditLogService, "log", audit)
    failed = await sso.test_provider_connection(
        item.id, MagicMock(), SimpleNamespace(id=uuid4())
    )
    assert failed["data"]["status"] == "error"
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_connection_test_rejects_missing_provider(monkeypatch):
    monkeypatch.setattr(sso.SSOProvider, "get_or_none", AsyncMock(return_value=None))
    with pytest.raises(BusinessError) as caught:
        await sso.test_provider_connection(uuid4(), MagicMock(), SimpleNamespace())
    assert caught.value.code == ResponseCode.SSO_PROVIDER_NOT_FOUND


@pytest.mark.anyio
async def test_admin_disconnect_enforces_remaining_auth_method(monkeypatch):
    target = SimpleNamespace(id=uuid4(), hashed_password="")
    connection = SimpleNamespace(
        user=target, provider=SimpleNamespace(name="Company"), delete=AsyncMock()
    )
    monkeypatch.setattr(
        UserSSOConnection,
        "get_or_none",
        MagicMock(side_effect=[Query(None), Query(connection), Query(connection)]),
    )
    monkeypatch.setattr(
        UserSSOConnection,
        "filter",
        MagicMock(side_effect=[Query(count=1), Query(count=2)]),
    )
    with pytest.raises(BusinessError) as missing:
        await sso.admin_disconnect_sso(uuid4(), MagicMock(), SimpleNamespace())
    assert missing.value.code == ResponseCode.NOT_FOUND
    with pytest.raises(BusinessError) as forbidden:
        await sso.admin_disconnect_sso(uuid4(), MagicMock(), SimpleNamespace())
    assert forbidden.value.code == ResponseCode.FORBIDDEN
    audit = AsyncMock()
    monkeypatch.setattr(sso.AuditLogService, "log", audit)
    assert (
        await sso.admin_disconnect_sso(
            uuid4(), MagicMock(), SimpleNamespace(id=uuid4())
        )
    )["code"] == 0
    connection.delete.assert_awaited_once()
    audit.assert_awaited_once()
