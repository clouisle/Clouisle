"""Server-side feature gates shared by messaging transports and business work."""

from app.models.integration import Integration
from app.schemas.response import BusinessError, ResponseCode


def active_features(integration: Integration | None) -> set[str]:
    """A missing or legacy-disabled record cannot grant a feature."""
    if integration is None or not integration.is_enabled:
        return set()
    return set(integration.enabled_capabilities or [])


async def enabled_features(provider_type: str) -> set[str]:
    return active_features(await Integration.get_or_none(provider_type=provider_type))


async def require_feature(provider_type: str, capability: str) -> None:
    await require_any_feature(provider_type, (capability,))


async def require_any_feature(
    provider_type: str, capabilities: tuple[str, ...]
) -> None:
    if not (await enabled_features(provider_type)).intersection(capabilities):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="integration_feature_disabled",
            status_code=403,
        )
