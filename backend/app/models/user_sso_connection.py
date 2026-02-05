from tortoise import fields, models


class UserSSOConnection(models.Model):
    """Links users to their SSO provider accounts"""

    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="sso_connections", on_delete=fields.CASCADE
    )
    provider = fields.ForeignKeyField(
        "models.SSOProvider", related_name="user_connections", on_delete=fields.CASCADE
    )

    # Provider-specific user identifier
    provider_user_id = fields.CharField(
        max_length=255, description="Provider user ID (sub, nameID, etc.)"
    )
    provider_username = fields.CharField(max_length=255, null=True)
    provider_email = fields.CharField(max_length=255, null=True)

    # Additional provider data (JSON)
    provider_data = fields.JSONField(
        default=dict, description="Store full profile data from provider"
    )

    # Metadata
    first_login = fields.DatetimeField(auto_now_add=True)
    last_login = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_sso_connections"
        unique_together = (("provider", "provider_user_id"),)

    def __str__(self):
        return f"{self.user} - {self.provider}"
