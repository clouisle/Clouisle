from tortoise import fields, models


class SSOSession(models.Model):
    """Temporary SSO session state (for OAuth2/OIDC state parameter, SAML RelayState)"""

    id = fields.UUIDField(pk=True)
    session_id = fields.CharField(
        max_length=255, unique=True, description="Random state/RelayState"
    )
    provider = fields.ForeignKeyField(
        "models.SSOProvider", related_name="sessions", on_delete=fields.CASCADE
    )

    # OAuth2/OIDC specific
    code_verifier = fields.CharField(
        max_length=255, null=True, description="PKCE code verifier"
    )
    nonce = fields.CharField(max_length=255, null=True, description="OIDC nonce")

    # Redirect after login
    redirect_url = fields.CharField(max_length=512, null=True)

    # Metadata
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(description="Session expiry (10 minutes)")

    class Meta:
        table = "sso_sessions"

    def __str__(self):
        return f"Session {self.session_id}"
