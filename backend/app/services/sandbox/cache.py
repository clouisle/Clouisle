"""Sandbox cache helpers scaffold."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from contextlib import contextmanager
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


@contextmanager
def acquire_cache_lock(scope: str, key: str):
    lock = _LOCKS[f"{scope}:{key}"]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
