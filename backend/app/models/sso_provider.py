from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import User


class SSOProvider(models.Model):
    """SSO Provider Configuration"""

    id = fields.UUIDField(pk=True)
    name = fields.CharField(
        max_length=100, unique=True, description="Unique provider identifier"
    )
    protocol = fields.CharField(max_length=20, description="Protocol: oidc, saml2, cas")

    # Display settings
    display_name = fields.CharField(max_length=100, description="User-facing name")
    icon_url = fields.CharField(
        max_length=512, null=True, description="Provider icon URL"
    )
    button_text = fields.CharField(
        max_length=50,
        null=True,
        description="Button text (e.g., 'Sign in with Google')",
    )

    # Configuration (JSON field)
    config: dict = fields.JSONField(description="Protocol-specific configuration")  # type: ignore[assignment]
    # OIDC: {client_id, client_secret, issuer_url, authorization_url, token_url, userinfo_url, scopes}
    # SAML: {sp_entity_id, idp_entity_id, sso_url, slo_url, x509_cert, acs_url}
    # CAS: {server_url, service_url, version}

    # Attribute mapping (JSON field)
    attribute_mapping: dict = fields.JSONField(
        default=dict,
        description="Maps provider attributes to user fields (e.g., {'email': 'email', 'username': 'preferred_username'})",
    )  # type: ignore[assignment]

    # Settings
    is_enabled = fields.BooleanField(
        default=True, description="Enable/disable provider"
    )
    allow_signup = fields.BooleanField(
        default=True, description="Allow auto-creation of users"
    )
    require_approval = fields.BooleanField(
        default=False, description="Require admin approval for new users"
    )
    default_role_id = fields.UUIDField(
        null=True, description="Default role for new SSO users"
    )

    # Metadata
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_sso_providers",
        null=True,
        on_delete=fields.SET_NULL,
    )

    class Meta:
        table = "sso_providers"

    def __str__(self):
        return self.name
