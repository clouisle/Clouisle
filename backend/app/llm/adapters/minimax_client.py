"""Shared MiniMax API client for media adapters."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.i18n import t
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InsufficientQuotaError,
    InvalidRequestError,
    LLMError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


class MiniMaxClient:
    """Thin async client for MiniMax media APIs."""

    def __init__(self, model_config: Any):
        self.provider = "minimax"
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.config = getattr(model_config, "config", None) or {}
        self.base_url = (model_config.base_url or "https://api.minimax.chat/v1").rstrip(
            "/"
        )
        self.timeout = float(self.config.get("timeout", 300))

    def _build_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        if self.base_url.endswith("/v1") and normalized.startswith("/v1/"):
            normalized = normalized[3:]
        return f"{self.base_url}{normalized}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    self._build_url(path),
                    json=json,
                    params=params,
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message=t("minimax_request_timeout"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=t("minimax_api_error"),
                provider=self.provider,
                model=self.model_id,
            ) from exc

        if response.status_code == 401:
            raise AuthenticationError(
                message=t("invalid_minimax_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 404 and task_id:
            raise TaskNotFoundError(
                message=t("minimax_task_not_found"),
                task_id=task_id,
                provider=self.provider,
            )
        if response.status_code == 404:
            raise InvalidRequestError(
                message=t("minimax_endpoint_not_found"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=t("minimax_rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code >= 400:
            raise ProviderError(
                message=t("minimax_api_error"),
                status_code=response.status_code,
                provider=self.provider,
                model=self.model_id,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError(
                message=t("minimax_invalid_response"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        if not isinstance(data, dict):
            raise ProviderError(
                message=t("minimax_invalid_response"),
                provider=self.provider,
                model=self.model_id,
            )
        self._raise_for_application_error(data)
        return data

    def _raise_for_application_error(self, data: dict[str, Any]) -> None:
        base_resp = data.get("base_resp")
        if not isinstance(base_resp, dict):
            return
        status_code = base_resp.get("status_code", 0)
        try:
            code = int(status_code)
        except (TypeError, ValueError):
            code = -1
        if code == 0:
            return

        error: LLMError
        if code in {1004, 2049}:
            error = AuthenticationError(
                message=t("invalid_minimax_api_key"),
                provider=self.provider,
                model=self.model_id,
            )
        elif code in {1002, 1039}:
            error = RateLimitError(
                message=t("minimax_rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            )
        elif code == 1008:
            error = InsufficientQuotaError(
                message=t("minimax_insufficient_balance"),
                provider=self.provider,
                model=self.model_id,
            )
        elif code in {1026, 1027}:
            error = ContentFilterError(
                message=t("minimax_content_filtered"),
                provider=self.provider,
                model=self.model_id,
            )
        elif code == 2013:
            error = InvalidRequestError(
                message=t("minimax_invalid_request"),
                provider=self.provider,
                model=self.model_id,
            )
        else:
            error = ProviderError(
                message=t("minimax_api_error"),
                status_code=code,
                provider=self.provider,
                model=self.model_id,
            )
        raise error
