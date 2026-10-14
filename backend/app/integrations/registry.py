"""Explicit capability catalog; configuration cannot invent provider features."""

from dataclasses import dataclass
from enum import StrEnum


class IntegrationCapability(StrEnum):
    USER_LOGIN = "user_login"
    DIRECTORY_SYNC = "directory_sync"
    NOTIFICATION = "notification"


@dataclass(frozen=True)
class IntegrationDefinition:
    provider_type: str
    display_name: str
    capabilities: tuple[str, ...]
    secret_fields: tuple[str, ...] = ()
    singleton: bool = False


def implicit_builtin_capabilities(definition: IntegrationDefinition) -> list[str]:
    """Capabilities a builtin's `is_enabled` flag grants on its own.

    Login is deliberately excluded: turning on a builtin must not silently add a
    new way to sign in. An administrator opts into `user_login` explicitly.
    """
    return [
        capability
        for capability in definition.capabilities
        if capability != IntegrationCapability.USER_LOGIN
    ]


class IntegrationRegistry:
    def __init__(self, definitions: tuple[IntegrationDefinition, ...]):
        self._definitions = {}
        for definition in definitions:
            if definition.provider_type in self._definitions:
                raise ValueError(
                    f"Duplicate integration type: {definition.provider_type}"
                )
            self._definitions[definition.provider_type] = definition

    def get(self, provider_type: str) -> IntegrationDefinition:
        try:
            return self._definitions[provider_type]
        except KeyError as exc:
            raise ValueError(f"Unknown integration type: {provider_type}") from exc

    def all(self) -> tuple[IntegrationDefinition, ...]:
        return tuple(self._definitions.values())


integration_registry = IntegrationRegistry(
    (
        IntegrationDefinition(
            "oauth2",
            "OAuth 2.0",
            (IntegrationCapability.USER_LOGIN,),
            ("client_secret",),
        ),
        IntegrationDefinition(
            "oidc",
            "OpenID Connect",
            (IntegrationCapability.USER_LOGIN,),
            ("client_secret",),
        ),
        IntegrationDefinition(
            "saml2",
            "SAML 2.0",
            (IntegrationCapability.USER_LOGIN,),
            ("sp_private_key",),
        ),
        IntegrationDefinition("cas", "CAS", (IntegrationCapability.USER_LOGIN,)),
        IntegrationDefinition(
            "email",
            "Email",
            (IntegrationCapability.NOTIFICATION,),
            ("smtp_password",),
            True,
        ),
        IntegrationDefinition(
            "webhook",
            "Webhook",
            (IntegrationCapability.NOTIFICATION,),
            ("webhook_secret", "webhook_headers"),
            True,
        ),
        IntegrationDefinition(
            "feishu",
            "Feishu",
            (IntegrationCapability.DIRECTORY_SYNC, IntegrationCapability.USER_LOGIN),
            ("app_secret",),
            True,
        ),
    )
)
