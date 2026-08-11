"""Authenticated client for the internal upload gateway."""

from __future__ import annotations

import httpx

from app.core.config import settings


class UploadGatewayError(RuntimeError):
    """A transient failure while a worker calls the API upload gateway."""


def client() -> httpx.AsyncClient:
    """Create an authenticated client for the internal uploads API."""
    return httpx.AsyncClient(
        base_url=settings.API_INTERNAL_BASE_URL.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.get_internal_api_token()}"},
        timeout=60.0,
    )


async def read(key: str) -> bytes:
    """Stream an upload through the gateway, preserving missing-file semantics."""
    try:
        async with client() as gateway:
            async with gateway.stream(
                "GET", "/internal/uploads/read", params={"key": key}
            ) as response:
                if response.status_code == 404:
                    raise FileNotFoundError(key)
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                return bytes(content)
    except FileNotFoundError:
        raise
    except httpx.HTTPError as exc:
        raise UploadGatewayError("Unable to read upload through api gateway") from exc
