"""Shared sandbox cache-key, package-source, and installation-lock helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_LOCKS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def build_cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_package_source_url(url: str | None) -> str | None:
    if url is None:
        return None
    normalized = url.strip()
    if not normalized:
        return None

    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
    )


@asynccontextmanager
async def acquire_async_cache_lock(scope: str, key: str):
    """Wait for a shared cache lock without blocking the event loop."""
    lock = _LOCKS[f"{scope}:{key}"]
    acquire_task = asyncio.create_task(asyncio.to_thread(lock.acquire))
    try:
        await asyncio.shield(acquire_task)
    except asyncio.CancelledError:
        await acquire_task
        lock.release()
        raise

    try:
        yield
    finally:
        lock.release()
