"""Load and update the one persisted configuration for a builtin integration."""

from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.integrations.registry import (
    IntegrationCapability,
    implicit_builtin_capabilities,
    integration_registry,
)
from app.models.integration import Integration


def get_runtime_config(integration: Integration) -> dict:
    config = dict(integration.config)
    config.update(
        {key: decrypt_secret(value) for key, value in integration.credentials.items()}
    )
    return config


async def get_builtin_integration(provider_type: str) -> Integration:
    definition = integration_registry.get(provider_type)
    if not definition.singleton:
        raise ValueError(f"Not a builtin integration: {provider_type}")
    integration = await Integration.get_or_none(provider_type=provider_type)
    if integration is None:
        raise ValueError(f"Builtin integration not initialized: {provider_type}")
    return integration


async def update_builtin_config(
    provider_type: str,
    config: dict,
    secret_values: dict | None = None,
    enabled: bool | None = None,
) -> Integration:
    definition = integration_registry.get(provider_type)
    if set(config) & set(definition.secret_fields):
        raise ValueError(
            "Credentials must be stored separately from integration config"
        )
    if secret_values and not set(secret_values).issubset(definition.secret_fields):
        raise ValueError("Unsupported integration credential field")
    integration = await get_builtin_integration(provider_type)
    integration.config = {**integration.config, **config}
    credentials = dict(integration.credentials)
    for key, value in (secret_values or {}).items():
        if value:
            credentials[key] = encrypt_secret(value)
    integration.credentials = credentials
    if enabled is not None:
        integration.is_enabled = enabled
        # Login stays an explicit opt-in; disabling the instance stops every
        # capability without discarding that choice.
        opted_in_login = [
            capability
            for capability in integration.enabled_capabilities or []
            if capability == IntegrationCapability.USER_LOGIN
        ]
        integration.enabled_capabilities = (
            [*implicit_builtin_capabilities(definition), *opted_in_login]
            if enabled
            else opted_in_login
        )
    await integration.save()
    return integration
