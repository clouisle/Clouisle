"""Transport settings never expose credentials or control user routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import feishu
from app.services import integration_config


@pytest.mark.asyncio
async def test_transport_update_preserves_secrets_and_does_not_change_user_selection(
    monkeypatch,
):
    integration = SimpleNamespace(
        id=uuid4(),
        name="feishu",
        config={"app_id": "cli_test"},
        credentials={
            "event_verification_token": "private-token",
            "event_encrypt_key": "private-key",
        },
        is_enabled=True,
        enabled_capabilities=["agent_chat"],
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        feishu, "get_builtin_integration", AsyncMock(return_value=integration)
    )
    monkeypatch.setattr(
        integration_config,
        "get_builtin_integration",
        AsyncMock(return_value=integration),
    )
    monkeypatch.setattr(feishu.AuditLogService, "log", AsyncMock())
    user = SimpleNamespace(id=uuid4())
    response = await feishu.update_agent_chat_config(
        request=MagicMock(),
        data=feishu.FeishuAgentChatConfigUpdate(connection_mode="long_connection"),
        current_user=user,
    )
    assert response["data"]["connection_mode"] == "long_connection"
    assert "agent_ids" not in response["data"]
    assert "private-token" not in str(response)
    assert "private-key" not in str(response)
    await feishu.update_agent_chat_config(
        request=MagicMock(),
        data=feishu.FeishuAgentChatConfigUpdate(),
        current_user=user,
    )
    assert integration.config == {
        "app_id": "cli_test",
        "agent_chat_connection_mode": "long_connection",
    }
    assert integration.credentials == {
        "event_verification_token": "private-token",
        "event_encrypt_key": "private-key",
    }


@pytest.mark.parametrize(
    "data",
    [
        {"agent_ids": []},
        {"connection_mode": "websocket"},
        {"event_encrypt_key": "short"},
    ],
)
def test_transport_contract_rejects_retired_selection_and_invalid_config(data):
    with pytest.raises(ValueError):
        feishu.FeishuAgentChatConfigUpdate.model_validate(data)
