"""Builtin integration configuration validation and persistence behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import integration_config


@pytest.mark.asyncio
async def test_get_builtin_integration_rejects_non_singleton_and_missing_instance(
    monkeypatch,
):
    definition = SimpleNamespace(singleton=False)
    monkeypatch.setattr(
        integration_config.integration_registry,
        "get",
        lambda _provider: definition,
    )

    with pytest.raises(ValueError, match="Not a builtin integration"):
        await integration_config.get_builtin_integration("custom")

    definition.singleton = True
    monkeypatch.setattr(
        integration_config.Integration, "get_or_none", AsyncMock(return_value=None)
    )
    with pytest.raises(ValueError, match="not initialized"):
        await integration_config.get_builtin_integration("custom")


@pytest.mark.asyncio
async def test_update_builtin_config_validates_and_encrypts_only_nonempty_secrets(
    monkeypatch,
):
    definition = SimpleNamespace(secret_fields={"app_secret"})
    monkeypatch.setattr(
        integration_config.integration_registry,
        "get",
        lambda _provider: definition,
    )
    instance = SimpleNamespace(
        config={"existing": "kept"},
        credentials={"old_secret": "encrypted-old"},
        enabled_capabilities=[],
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        integration_config, "get_builtin_integration", AsyncMock(return_value=instance)
    )
    monkeypatch.setattr(
        integration_config, "encrypt_secret", lambda value: f"encrypted:{value}"
    )

    with pytest.raises(ValueError, match="stored separately"):
        await integration_config.update_builtin_config("feishu", {"app_secret": "raw"})
    with pytest.raises(ValueError, match="Unsupported integration credential"):
        await integration_config.update_builtin_config("feishu", {}, {"unknown": "raw"})

    await integration_config.update_builtin_config(
        "feishu", {"new": "value"}, {"app_secret": "secret"}
    )

    assert instance.config == {"existing": "kept", "new": "value"}
    assert instance.credentials == {
        "old_secret": "encrypted-old",
        "app_secret": "encrypted:secret",
    }
    instance.save.assert_awaited_once()
