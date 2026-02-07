from typing import Dict, Any, Tuple

from app.core.timezone import now_utc
from app.models.site_setting import SiteSetting
from app.models.sso_provider import SSOProvider
from app.models.user import User, Role
from app.models.user_sso_connection import UserSSOConnection
from app.schemas.response import BusinessError, ResponseCode
from app.sso.providers.base import BaseSSOProvider
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider
from app.sso.providers.saml import SAMLProvider


class SSOService:
    """SSO business logic service"""

    @staticmethod
    def get_provider_instance(provider: SSOProvider) -> BaseSSOProvider:
        """
        Factory method to get provider instance

        Args:
            provider: SSOProvider model instance

        Returns:
            Provider implementation instance

        Raises:
            ValueError: If protocol is not supported
        """
        protocol = provider.protocol.lower()

        if protocol in ["oauth2", "oidc"]:
            return OIDCProvider(provider)
        elif protocol == "saml2":
            return SAMLProvider(provider)
        elif protocol == "cas":
            return CASProvider(provider)
        else:
            raise ValueError(f"Unsupported protocol: {provider.protocol}")

    @staticmethod
    async def find_or_create_user(
        provider: SSOProvider,
        provider_user_id: str,
        user_info: Dict[str, Any],
    ) -> Tuple[User, bool]:
        """
        Find existing user or create new one based on SSO data

        Args:
            provider: SSO provider
            provider_user_id: Provider's user identifier
            user_info: User information from provider

        Returns:
            Tuple of (User, is_new_user)

        Raises:
            BusinessError: If registration is disabled or other errors
        """
        # Check if SSO connection already exists
        connection = (
            await UserSSOConnection.filter(
                provider=provider, provider_user_id=provider_user_id
            )
            .prefetch_related("user")
            .first()
        )

        if connection:
            # Update last login and provider data
            connection.last_login = now_utc()
            connection.provider_data = user_info
            await connection.save()
            return connection.user, False

        # Check if we should match by email
        match_by_email = await SiteSetting.get_value("sso_match_by_email", True)
        email = user_info.get("email")

        existing_user = None
        if match_by_email and email:
            existing_user = await User.filter(email=email).first()

        if existing_user:
            # Link existing user to SSO provider
            await UserSSOConnection.create(
                user=existing_user,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_username=user_info.get("username"),
                provider_email=email,
                provider_data=user_info,
            )
            return existing_user, False

        # Create new user
        auto_create = await SiteSetting.get_value("sso_auto_create_users", True)
        if not auto_create and not provider.allow_signup:
            raise BusinessError(
                code=ResponseCode.SSO_REGISTRATION_DISABLED,
                msg_key="sso_registration_disabled",
            )

        require_approval = await SiteSetting.get_value("sso_require_approval", False)
        if provider.require_approval:
            require_approval = True

        # Generate username if not provided
        username = user_info.get("username")
        if not username and email:
            username = email.split("@")[0]
        elif not username:
            username = f"user_{provider_user_id[:8]}"

        # Ensure username is unique
        base_username = username
        counter = 1
        while await User.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        # Ensure email is provided
        if not email:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="email_required",
            )

        # Create new user
        default_language = await SiteSetting.get_value("default_language", "en")
        new_user = await User.create(
            username=username,
            email=email,
            hashed_password="",  # No password for SSO users
            auth_source=provider.name,
            is_active=not require_approval,
            email_verified=True,  # Trust SSO provider
            avatar_url=user_info.get("picture") or user_info.get("avatar_url"),
            locale=default_language,
        )

        # Assign default role if configured
        if provider.default_role_id:
            role = await Role.get_or_none(id=provider.default_role_id)
            if role:
                await new_user.roles.add(role)

        # Create SSO connection
        await UserSSOConnection.create(
            user=new_user,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_username=user_info.get("username"),
            provider_email=email,
            provider_data=user_info,
        )

        return new_user, True

    @staticmethod
    async def cleanup_expired_sessions():
        """Clean up expired SSO sessions"""
        from app.models.sso_session import SSOSession

        expired_sessions = await SSOSession.filter(expires_at__lt=now_utc())
        await expired_sessions.delete()
