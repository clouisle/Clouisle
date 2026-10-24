"""Feature switches cannot reactivate capabilities owned by another admin domain."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.admin.endpoints import integrations
from app.schemas.integration import IntegrationUpdate
from app.schemas.response import BusinessError, ResponseCode
from tests.api.test_admin_integration_domains import feishu, login_admin, settings_admin


@pytest.mark.asyncio
async def test_disabled_feishu_cannot_reactivate_login_through_settings_only_update(
    monkeypatch,
):
    instance = feishu(
        is_enabled=False, enabled_capabilities=["user_login", "agent_chat"]
    )
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )
    with pytest.raises(BusinessError) as denied:
        await integrations.update_integration(
            instance.id,
            MagicMock(),
            IntegrationUpdate(enabled_capabilities=["user_login", "agent_chat"]),
            settings_admin,
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED
    instance.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_feishu_can_enable_only_requested_feature_without_login_permission(
    monkeypatch,
):
    instance = feishu(is_enabled=False, enabled_capabilities=["user_login"])
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )
    monkeypatch.setattr(integrations.AuditLogService, "log", AsyncMock())
    result = await integrations.update_integration(
        instance.id,
        MagicMock(),
        IntegrationUpdate(enabled_capabilities=["agent_chat"]),
        settings_admin,
    )
    assert result["data"].is_enabled is True
    assert result["data"].enabled_capabilities == ["agent_chat"]


@pytest.mark.asyncio
async def test_login_only_admin_cannot_reactivate_stored_agent_chat(monkeypatch):
    instance = feishu(is_enabled=False, enabled_capabilities=["agent_chat"])
    monkeypatch.setattr(
        integrations, "_get_integration", AsyncMock(return_value=instance)
    )
    with pytest.raises(BusinessError) as denied:
        await integrations.update_integration(
            instance.id,
            MagicMock(),
            IntegrationUpdate(enabled_capabilities=["user_login", "agent_chat"]),
            login_admin,
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED
    instance.save.assert_not_awaited()
