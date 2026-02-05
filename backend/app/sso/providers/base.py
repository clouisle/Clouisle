from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from app.models.sso_provider import SSOProvider


class BaseSSOProvider(ABC):
    """Base class for all SSO providers"""

    def __init__(self, provider: SSOProvider):
        self.provider = provider
        self.config = provider.config

    @abstractmethod
    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> str | Tuple[str, ...]:
        """
        Generate authorization URL for user redirect

        Args:
            state: CSRF protection state parameter
            redirect_uri: Callback URL after authentication

        Returns:
            Authorization URL (or tuple with additional data for OIDC)
        """
        pass

    @abstractmethod
    async def handle_callback(
        self, callback_data: Dict[str, Any], redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Handle callback from SSO provider and extract user info

        Args:
            callback_data: Data from callback (code, SAMLResponse, ticket, etc.)
            redirect_uri: Callback URL

        Returns:
            Dict with user info including provider_user_id
        """
        pass

    def map_user_attributes(self, provider_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map provider attributes to user fields

        Args:
            provider_data: Raw data from provider

        Returns:
            Mapped user data
        """
        mapping = self.provider.attribute_mapping
        user_data = {}

        for user_field, provider_field in mapping.items():
            value = self._get_nested_value(provider_data, provider_field)
            if value:
                user_data[user_field] = value

        return user_data

    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """
        Get nested dictionary value using dot notation

        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., "user.profile.email")

        Returns:
            Value at path or None
        """
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
