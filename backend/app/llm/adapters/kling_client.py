"""
Shared Kling API client for video adapters.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)


class KlingClient:
    """Thin async client for Kling AI video generation APIs."""

    def __init__(self, model_config: Any):
        self.model_config = model_config
        self.provider = "kling"
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.config = getattr(model_config, "config", None) or {}
        self.base_url = (
            model_config.base_url or "https://api.klingai.com"
        ).rstrip("/")
        self.timeout = float(self.config.get("timeout", 180))
        self.poll_interval = max(float(self.config.get("poll_interval_seconds", 5)), 1)
        self.task_timeout = max(float(self.config.get("task_timeout_seconds", 300)), 5)

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    self._build_url(path),
                    json=json,
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(
                message="Kling request timeout",
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"Kling request failed: {exc}",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        if response.status_code == 401:
            raise AuthenticationError(
                message="Invalid Kling API key",
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 404 and method.upper() == "GET":
            raise TaskNotFoundError(
                message="Kling task not found",
                task_id=path.rsplit("/", 1)[-1],
                provider=self.provider,
            )
        if response.status_code == 404:
            raise InvalidRequestError(
                message="Kling endpoint not found",
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message="Kling rate limit exceeded",
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code >= 400:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}
            message = (
                error_data.get("message")
                or error_data.get("error")
                or response.text
                or "Kling API error"
            )
            raise ProviderError(
                message=message,
                status_code=response.status_code,
                provider=self.provider,
                model=self.model_id,
            )

        return response.json()

    async def create_task(
        self, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/v1/videos/text2video/{task_id}"
        )

    async def wait_for_task(self, task_id: str) -> dict[str, Any]:
        elapsed = 0.0
        while elapsed <= self.task_timeout:
            task = await self.get_task(task_id)
            status = str(task.get("task_status", "")).lower()
            if status in {"succeed", "failed"}:
                return task

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        raise ProviderError(
            message="Kling task polling timed out",
            provider=self.provider,
            model=self.model_id,
        )
