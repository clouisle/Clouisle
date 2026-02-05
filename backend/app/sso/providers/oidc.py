import base64
import hashlib
import secrets
from typing import Any, Dict, Tuple

import httpx
from authlib.jose import jwt

from app.sso.providers.base import BaseSSOProvider


class OIDCProvider(BaseSSOProvider):
    """OAuth2/OIDC provider implementation"""

    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> Tuple[str, str, str]:
        """
        Generate authorization URL with PKCE

        Returns:
            Tuple of (authorization_url, code_verifier, nonce)
        """
        # Generate PKCE code verifier and challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        # Generate nonce for OIDC
        nonce = secrets.token_urlsafe(32)

        # Build authorization URL
        scopes = self.config.get("scopes", "openid email profile")
        params = {
            "client_id": self.config["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "nonce": nonce,
        }

        # Build query string
        query_string = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
        authorization_url = f"{self.config['authorization_url']}?{query_string}"

        return authorization_url, code_verifier, nonce

    async def handle_callback(
        self, callback_data: Dict[str, Any], redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Handle OAuth2/OIDC callback

        Args:
            callback_data: {"code": "...", "code_verifier": "..."}
            redirect_uri: Callback URL

        Returns:
            User info with provider_user_id
        """
        code = callback_data.get("code")
        code_verifier = kwargs.get("code_verifier")

        if not code:
            raise ValueError("Missing authorization code")

        # Exchange code for tokens
        token_data = await self._exchange_code(code, redirect_uri, code_verifier)

        # Get user info
        user_info = await self._get_user_info(token_data["access_token"])

        # Add provider_user_id
        # Standard OIDC uses "sub", but some providers (like GitHub) use "id"
        provider_user_id = user_info.get("sub") or user_info.get("id")
        if provider_user_id:
            # Convert to string to ensure consistency
            user_info["provider_user_id"] = str(provider_user_id)
        else:
            user_info["provider_user_id"] = None

        return user_info

    async def _exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> Dict[str, Any]:
        """Exchange authorization code for tokens"""
        token_url = self.config["token_url"]
        client_id = self.config["client_id"]
        client_secret = self.config.get("client_secret")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        if client_secret:
            data["client_secret"] = client_secret

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=data,
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()

            # Try to parse as JSON first, fallback to form-encoded
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            else:
                # Parse form-encoded response (e.g., GitHub OAuth)
                from urllib.parse import parse_qs
                parsed = parse_qs(response.text)
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetch user information from userinfo endpoint"""
        userinfo_url = self.config["userinfo_url"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()

    async def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Validate and decode ID token

        Note: For production, should fetch JWKS from provider and validate signature
        """
        # For now, decode without verification (should be improved)
        claims = jwt.decode(id_token, self.config.get("client_secret", ""))
        return claims
