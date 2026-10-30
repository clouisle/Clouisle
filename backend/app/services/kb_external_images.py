"""Opt-in, SSRF-safe fetching of external images for knowledge bases."""

from __future__ import annotations

import asyncio
import io
import socket
import warnings
from collections.abc import Iterable
from typing import Any

import aiohttp
from yarl import URL

from app.core.network_security import (
    get_ssrf_allowed_targets,
    validate_external_http_url,
)
from app.models.site_setting import SiteSetting

EXTERNAL_IMAGE_FETCH_SETTING = "kb_image_understanding_allow_external"
MAX_EXTERNAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_EXTERNAL_IMAGE_REDIRECTS = 5
EXTERNAL_IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)
_ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)
_IMAGE_FORMAT_TO_MIME = {
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _address_records(
    host: str,
    port: int,
    resolved: list[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Convert checked getaddrinfo results to aiohttp resolver records."""
    records: list[dict[str, Any]] = []
    for family, socktype, proto, _canonname, sockaddr in resolved:
        if (
            family not in (socket.AF_INET, socket.AF_INET6)
            or socktype != socket.SOCK_STREAM
        ):
            continue
        records.append(
            {
                "hostname": host,
                "host": sockaddr[0],
                "port": port,
                "family": family,
                "proto": proto,
                "flags": 0,
            }
        )
    return records


class _PinnedResolver:
    """Resolver returning only the already-validated addresses for one origin."""

    def __init__(self, host: str, port: int, records: list[dict[str, Any]]):
        self._host = host.lower().rstrip(".")
        self._port = port
        self._records = records

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_UNSPEC,
    ) -> list[dict[str, Any]]:
        if host.lower().rstrip(".") != self._host or port != self._port:
            raise OSError("Pinned resolver cannot resolve a different destination")
        records = self._records
        if family != socket.AF_UNSPEC:
            records = [record for record in records if record["family"] == family]
        if not records:
            raise OSError("No validated address is available for this destination")
        return records

    async def close(self) -> None:
        return None


async def _resolve_and_validate(
    destination: URL, allowlist: Iterable[str]
) -> tuple[str, int, list[dict[str, Any]]]:
    host = destination.raw_host
    if not host:
        raise ValueError("External image URL has no hostname")
    port = destination.port

    try:
        resolved = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        # Keep DNS failures on the same error path and vocabulary as the shared
        # network security validator.
        from app.schemas.response import BusinessError

        raise BusinessError(msg_key="http_tool_url_host_cannot_be_resolved") from exc

    if not resolved:
        from app.schemas.response import BusinessError

        raise BusinessError(msg_key="http_tool_url_host_cannot_be_resolved")

    # The validator receives exactly the DNS answer that will be used by the
    # connector. It checks every address using the central block/allowlist rules.
    validate_external_http_url(
        str(destination),
        getaddrinfo=lambda *_args, **_kwargs: resolved,
        allowlist=allowlist,
    )
    records = _address_records(host, port, resolved)
    if not records:
        from app.schemas.response import BusinessError

        raise BusinessError(msg_key="http_tool_url_host_cannot_be_resolved")
    return host, port, records


def _normalize_destination(value: str | URL) -> URL:
    try:
        destination = value if isinstance(value, URL) else URL(value)
        if destination.scheme not in {"http", "https"} or not destination.raw_host:
            raise ValueError("External image URL must use HTTP or HTTPS")
        if destination.user is not None or destination.password is not None:
            raise ValueError("External image URL credentials are not allowed")
        # aiohttp ignores fragments; remove them before validating and fetching
        # so the central validator and client operate on the same URL.
        return destination.with_fragment(None)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid external image URL") from exc


async def fetch_external_image(
    url: str,
    *,
    max_image_bytes: int = MAX_EXTERNAL_IMAGE_BYTES,
    max_image_pixels: int = 40_000_000,
) -> tuple[bytes, str]:
    """Fetch one external image after explicit opt-in and central SSRF validation.

    Every redirect is resolved and validated independently. The checked DNS
    answers are pinned into that request's connector, while aiohttp retains the
    URL hostname for TLS certificate validation and SNI.
    """
    if max_image_bytes <= 0:
        raise ValueError("External image byte limit must be positive")
    if max_image_pixels <= 0:
        raise ValueError("External image pixel limit must be positive")

    if not await SiteSetting.get_value(EXTERNAL_IMAGE_FETCH_SETTING, False):
        raise PermissionError("External image fetching is disabled")

    allowlist = await get_ssrf_allowed_targets()
    if allowlist is None:
        # Do not let a globally disabled SSRF policy turn this feature's
        # separately opted-in image fetch into an unrestricted private-network
        # transport. Fail closed rather than weakening the shared policy.
        raise PermissionError("External image fetching requires SSRF protection")

    current = _normalize_destination(url)
    for redirect_number in range(MAX_EXTERNAL_IMAGE_REDIRECTS + 1):
        host, port, records = await _resolve_and_validate(current, allowlist)
        resolver = _PinnedResolver(host, port, records)
        connector = aiohttp.TCPConnector(
            resolver=resolver,
            use_dns_cache=False,
            force_close=True,
            limit=1,
        )
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=EXTERNAL_IMAGE_TIMEOUT,
            trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar(),
            headers={"Accept": ", ".join(sorted(_ALLOWED_IMAGE_MIMES))},
        ) as session:
            async with session.get(
                current,
                allow_redirects=False,
                proxy=None,
            ) as response:
                if response.status in _REDIRECT_STATUSES:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("External image redirect has no destination")
                    if redirect_number >= MAX_EXTERNAL_IMAGE_REDIRECTS:
                        raise ValueError("External image redirect limit exceeded")
                    try:
                        current = _normalize_destination(current.join(URL(location)))
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Invalid external image redirect") from exc
                    continue

                response.raise_for_status()
                mime_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                mime_type = mime_type.strip().lower()
                if mime_type not in _ALLOWED_IMAGE_MIMES:
                    raise ValueError("External response is not a supported image type")

                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError as exc:
                        raise ValueError(
                            "Invalid external image content length"
                        ) from exc
                    if declared_size < 0 or declared_size > max_image_bytes:
                        raise ValueError("External image exceeds the size limit")
                content = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if len(content) + len(chunk) > max_image_bytes:
                        raise ValueError("External image exceeds the size limit")
                    content.extend(chunk)

                from PIL import Image, UnidentifiedImageError

                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", Image.DecompressionBombWarning)
                        with Image.open(io.BytesIO(content)) as image:
                            if image.width * image.height > max_image_pixels:
                                raise ValueError(
                                    "External image exceeds the pixel limit"
                                )
                            actual_mime = _IMAGE_FORMAT_TO_MIME.get(image.format or "")
                            image.verify()
                except (
                    Image.DecompressionBombError,
                    Image.DecompressionBombWarning,
                ) as exc:
                    raise ValueError(
                        "External image exceeds Pillow's safety limit"
                    ) from exc
                except (UnidentifiedImageError, OSError) as exc:
                    raise ValueError(
                        "External response contains invalid image data"
                    ) from exc
                if actual_mime != mime_type:
                    raise ValueError(
                        "External image content does not match its MIME type"
                    )
                return bytes(content), mime_type

    raise ValueError("External image redirect limit exceeded")
