"""Feishu (Lark) web login, reusing the singleton Feishu app credentials."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any, Dict, Tuple

from app.core.i18n import t
from app.integrations.feishu import (
    DEFAULT_AUTHORIZATION_URL,
    DEFAULT_LOGIN_SCOPES,
    DEFAULT_TOKEN_URL,
    DEFAULT_USERINFO_URL,
    FeishuAPIError,
    build_authorization_url,
    exchange_user_access_token,
    fetch_user_info,
)
from app.sso.providers.base import BaseSSOProvider
from app.services.feishu_directory import placeholder_email


class FeishuProvider(BaseSSOProvider):
    """OAuth 2.0 authorization code + PKCE against the Feishu user endpoints."""

    async def get_authorization_url(
        self, state: str, redirect_uri: str, **kwargs
    ) -> Tuple[str, str, str]:
        """Return the authorization URL plus the PKCE verifier for the session."""
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        url = build_authorization_url(
            app_id=self._app_id(),
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            scopes=self._config_str("scopes") or DEFAULT_LOGIN_SCOPES,
            authorization_url=self._config_str("authorization_url")
            or DEFAULT_AUTHORIZATION_URL,
        )
        # Feishu has no OIDC nonce; the session column stays empty.
        return url, code_verifier, ""

    async def handle_callback(
        self, callback_data: Dict[str, Any], redirect_uri: str, **kwargs
    ) -> Dict[str, Any]:
        code = callback_data.get("code")
        if not code:
            raise ValueError(t("sso_missing_authorization_code"))

        user_access_token = await exchange_user_access_token(
            token_url=self._config_str("token_url") or DEFAULT_TOKEN_URL,
            app_id=self._app_id(),
            app_secret=self._app_secret(),
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=kwargs.get("code_verifier") or "",
        )
        raw = await fetch_user_info(
            userinfo_url=self._config_str("userinfo_url") or DEFAULT_USERINFO_URL,
            user_access_token=user_access_token,
        )
        return self._user_info(raw)

    def _user_info(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        # `union_id` survives an app replacement within the same developer account.
        provider_user_id = raw.get("union_id") or raw.get("open_id")
        if not isinstance(provider_user_id, str) or not provider_user_id.strip():
            raise FeishuAPIError(
                "Feishu user info returned neither union_id nor open_id"
            )

        email = raw.get("email") or raw.get("enterprise_email")
        email = (
            email.strip().lower() if isinstance(email, str) and email.strip() else None
        )
        if email is None:
            # Mirrors directory sync so both paths resolve to the same account.
            # Without `contact:user.employee_id:readonly` there is no user_id to
            # derive it from and the caller rejects the signup instead.
            feishu_user_id = raw.get("user_id")
            if isinstance(feishu_user_id, str) and feishu_user_id.strip():
                email = placeholder_email(feishu_user_id.strip())

        info = dict(raw)
        info.update(
            {
                "provider_user_id": provider_user_id.strip(),
                "username": raw.get("name") or raw.get("en_name"),
                "email": email,
                "avatar_url": raw.get("avatar_url"),
            }
        )
        return info

    def _config_str(self, key: str) -> str | None:
        value = self.config.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _app_id(self) -> str:
        app_id = self._config_str("app_id")
        if not app_id:
            raise FeishuAPIError(t("sso_invalid_configuration"))
        return app_id

    def _app_secret(self) -> str:
        secret = self.config.get("app_secret")
        if not isinstance(secret, str) or not secret:
            raise FeishuAPIError(t("sso_invalid_configuration"))
        return secret
