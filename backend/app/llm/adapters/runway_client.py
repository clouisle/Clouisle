"""
Shared Runway API client for image/video task adapters.
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


class RunwayClient:
    """Thin async client for Runway's task-based API."""

    def __init__(self, model_config: Any):
        self.model_config = model_config
        self.provider = "runway"
        self.model_id = model_config.model_id
        self.api_key = model_config.api_key
        self.config = getattr(model_config, "config", None) or {}
        self.base_url = (
            model_config.base_url or "https://api.dev.runwayml.com"
        ).rstrip("/")
        self.api_version = self.config.get("runway_api_version", "2024-11-06")
        self.timeout = float(self.config.get("timeout", 180))
        self.poll_interval = max(float(self.config.get("poll_interval_seconds", 5)), 1)
        self.task_timeout = max(float(self.config.get("task_timeout_seconds", 300)), 5)

    def _build_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        if self.base_url.endswith("/v1") and normalized.startswith("/v1/"):
            normalized = normalized[3:]
        return f"{self.base_url}{normalized}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": str(self.api_version),
        }
        return headers

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
                message="Runway request timeout",
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"Runway request failed: {exc}",
                provider=self.provider,
                model=self.model_id,
            ) from exc

        if response.status_code == 401:
            raise AuthenticationError(
                message="Invalid Runway API key",
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 404 and method.upper() == "GET":
            raise TaskNotFoundError(
                message="Runway task not found",
                task_id=path.rsplit("/", 1)[-1],
                provider=self.provider,
            )
        if response.status_code == 404:
            raise InvalidRequestError(
                message="Runway endpoint not found",
                provider=self.provider,
                model=self.model_id,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message="Runway rate limit exceeded",
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
                or "Runway API error"
            )
            raise ProviderError(
                message=message,
                status_code=response.status_code,
                provider=self.provider,
                model=self.model_id,
            )

        return response.json()

    async def create_task(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/tasks/{task_id}")

    async def wait_for_task(self, task_id: str) -> dict[str, Any]:
        elapsed = 0.0
        while elapsed <= self.task_timeout:
            task = await self.get_task(task_id)
            status = str(task.get("status", "")).upper()
            if status in {"SUCCEEDED", "FAILED", "CANCELLED", "CANCELED"}:
                return task

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        raise ProviderError(
            message="Runway task polling timed out",
            provider=self.provider,
            model=self.model_id,
        )
