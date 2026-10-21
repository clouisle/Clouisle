"""Explicit capability catalog; configuration cannot invent provider features."""

from dataclasses import dataclass
from enum import StrEnum


class IntegrationCapability(StrEnum):
    USER_LOGIN = "user_login"
    DIRECTORY_SYNC = "directory_sync"
    NOTIFICATION = "notification"
    AGENT_CHAT = "agent_chat"
    KNOWLEDGE_COLLECTION = "knowledge_collection"


@dataclass(frozen=True)
class IntegrationDefinition:
    provider_type: str
    display_name: str
    capabilities: tuple[str, ...]
    secret_fields: tuple[str, ...] = ()
    singleton: bool = False


def implicit_builtin_capabilities(definition: IntegrationDefinition) -> list[str]:
    """Capabilities a builtin's `is_enabled` flag grants on its own.

    Login, Feishu notifications, and Feishu agent chat remain explicit opt-ins
    so enabling an integration cannot silently change sign-in, messaging, or
    which Agents answer external chat messages.
    """
    return [
        capability
        for capability in definition.capabilities
        if capability != IntegrationCapability.USER_LOGIN
        and not (
            definition.provider_type == "feishu"
            and capability
            in (
                IntegrationCapability.NOTIFICATION,
                IntegrationCapability.AGENT_CHAT,
            )
        )
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
            "wechat",
            "WeChat iLink",
            (
                IntegrationCapability.AGENT_CHAT,
                IntegrationCapability.KNOWLEDGE_COLLECTION,
            ),
            singleton=True,
        ),
        IntegrationDefinition(
            "feishu",
            "Feishu",
            (
                IntegrationCapability.DIRECTORY_SYNC,
                IntegrationCapability.USER_LOGIN,
                IntegrationCapability.NOTIFICATION,
                IntegrationCapability.AGENT_CHAT,
            ),
            (
                "app_secret",
                "event_verification_token",
                "event_encrypt_key",
            ),
            True,
        ),
    )
)
