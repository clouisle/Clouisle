import logging
from typing import Any, Dict
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

import httpx

from app.core.i18n import t
from app.sso.providers.base import BaseSSOProvider

logger = logging.getLogger(__name__)


class CASProvider(BaseSSOProvider):
    """CAS protocol provider implementation"""

    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> str:
        """
        Generate CAS login URL

        Args:
            state: Not used in CAS (stored in session)
            redirect_uri: Service URL (callback URL)

        Returns:
            CAS login URL
        """
        server_url = self.config["server_url"]
        params = {"service": redirect_uri}
        return f"{server_url}/login?{urlencode(params)}"

    async def handle_callback(
        self, callback_data: Dict[str, Any], redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Validate CAS ticket and get user info

        Args:
            callback_data: {"ticket": "..."}
            redirect_uri: Service URL

        Returns:
            User info with provider_user_id
        """
        ticket = callback_data.get("ticket")
        if not ticket:
            raise ValueError(t("sso_missing_cas_ticket"))

        # Validate ticket
        user_info = await self._validate_ticket(ticket, redirect_uri)

        return user_info

    async def _validate_ticket(self, ticket: str, service_url: str) -> Dict[str, Any]:
        """
        Validate CAS ticket and get user info

        Args:
            ticket: CAS ticket from callback
            service_url: Service URL

        Returns:
            User info dict
        """
        server_url = self.config["server_url"]
        version = self.config.get("version", "3")

        # Choose validation endpoint based on CAS version
        if version == "1":
            validate_url = f"{server_url}/validate"
        elif version == "2":
            validate_url = f"{server_url}/serviceValidate"
        else:  # version 3
            validate_url = f"{server_url}/p3/serviceValidate"

        params = {
            "ticket": ticket,
            "service": service_url,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(validate_url, params=params)
            response.raise_for_status()

            # Parse XML response
            return self._parse_cas_response(response.text, version)

    def _parse_cas_response(self, xml_response: str, version: str) -> Dict[str, Any]:
        """
        Parse CAS XML response

        Args:
            xml_response: XML response from CAS server
            version: CAS version (1, 2, or 3)

        Returns:
            User info dict
        """
        try:
            root = ET.fromstring(xml_response)

            # Define namespace
            ns = {"cas": "http://www.yale.edu/tp/cas"}

            if version == "1":
                # CAS 1.0: Simple yes/no response
                lines = xml_response.strip().split("\n")
                if lines[0] == "yes":
                    username = lines[1] if len(lines) > 1 else ""
                    return {
                        "provider_user_id": username,
                        "username": username,
                    }
                else:
                    logger.warning("CAS validation failed without explicit error details")
                    raise ValueError(t("sso_cas_validation_failed"))

            else:
                # CAS 2.0/3.0: XML response
                success = root.find(".//cas:authenticationSuccess", ns)
                if success is None:
                    failure = root.find(".//cas:authenticationFailure", ns)
                    error_msg = (
                        failure.text
                        if failure is not None and failure.text is not None
                        else "Unknown error"
                    )
                    logger.warning("CAS validation failed: %s", error_msg)
                    raise ValueError(t("sso_cas_validation_failed"))

                # Extract user
                user_elem = success.find("cas:user", ns)
                username = (
                    user_elem.text
                    if user_elem is not None and user_elem.text is not None
                    else ""
                )

                user_info: Dict[str, Any] = {
                    "provider_user_id": username,
                    "username": username,
                }

                # Extract attributes (CAS 3.0)
                if version == "3":
                    attributes = success.find("cas:attributes", ns)
                    if attributes is not None:
                        for attr in attributes:
                            # Remove namespace prefix from tag
                            tag = (
                                attr.tag.split("}")[-1] if "}" in attr.tag else attr.tag
                            )
                            user_info[tag] = attr.text or ""

                return user_info

        except ET.ParseError as e:
            logger.warning("Failed to parse CAS response: %s", e)
            raise ValueError(t("sso_cas_response_parse_failed"))
