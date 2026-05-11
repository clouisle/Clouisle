import logging
from typing import Any, Dict

from onelogin.saml2.auth import OneLogin_Saml2_Auth

from app.core.i18n import t
from app.sso.providers.base import BaseSSOProvider

logger = logging.getLogger(__name__)


class SAMLProvider(BaseSSOProvider):
    """SAML 2.0 provider implementation"""

    def _get_saml_settings(self, acs_url: str | None = None) -> dict:
        """Build SAML settings from provider config"""
        config = self.config

        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": config["sp_entity_id"],
                "assertionConsumerService": {
                    "url": acs_url or config["acs_url"],
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "singleLogoutService": {
                    "url": config.get("slo_url", ""),
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "NameIDFormat": config.get(
                    "name_id_format",
                    "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
                ),
            },
            "idp": {
                "entityId": config["idp_entity_id"],
                "singleSignOnService": {
                    "url": config["sso_url"],
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": config.get("idp_slo_url", ""),
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": config["x509_cert"],
            },
        }

    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> str:
        """
        Generate SAML AuthnRequest

        Args:
            state: Used as RelayState
            redirect_uri: ACS URL

        Returns:
            SAML SSO URL with AuthnRequest
        """
        settings = self._get_saml_settings(acs_url=redirect_uri)

        # Create SAML auth object
        auth = OneLogin_Saml2_Auth({}, settings)

        # Generate login URL with RelayState
        return auth.login(return_to=state)

    async def handle_callback(
        self, callback_data: Dict[str, Any], redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Process SAML response and extract user attributes

        Args:
            callback_data: {"SAMLResponse": "..."}
            redirect_uri: ACS URL

        Returns:
            User info with provider_user_id
        """
        saml_response = callback_data.get("SAMLResponse")
        if not saml_response:
            raise ValueError(t("sso_missing_saml_response"))

        settings = self._get_saml_settings(acs_url=redirect_uri)

        # Create request data for python3-saml
        request_data = {
            "http_host": "",
            "script_name": "",
            "get_data": {},
            "post_data": {"SAMLResponse": saml_response},
        }

        auth = OneLogin_Saml2_Auth(request_data, settings)
        auth.process_response()

        if not auth.is_authenticated():
            errors = auth.get_errors()
            error_reason = auth.get_last_error_reason()
            logger.warning(
                "SAML authentication failed: reason=%s errors=%s",
                error_reason,
                errors,
            )
            raise ValueError(t("sso_saml_authentication_failed"))

        # Extract user attributes
        attributes = auth.get_attributes()
        name_id = auth.get_nameid()
        session_index = auth.get_session_index()

        # Flatten attributes (SAML attributes are lists)
        flattened_attributes = {}
        for key, value in attributes.items():
            flattened_attributes[key] = (
                value[0] if isinstance(value, list) and value else value
            )

        # Build user info
        user_info = {
            "provider_user_id": name_id,
            "nameID": name_id,
            "session_index": session_index,
            "attributes": flattened_attributes,
        }

        # Merge flattened attributes into user_info for easier mapping
        user_info.update(flattened_attributes)

        return user_info
