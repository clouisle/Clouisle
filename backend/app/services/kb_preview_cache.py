"""Cross-worker, temporary cache for knowledge-base OCR preprocessing.

Only enriched text and bounded JSON metadata are stored. Source bytes and model
configuration are represented by hashes; image bytes, data URIs, credentials,
and provider payloads are never accepted as cached metadata.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from app.core.redis import get_redis

_CACHE_PREFIX = "kb:preview:ocr:v1"
_CACHE_TTL_SECONDS = 15 * 60
_MAX_CACHE_BYTES = 5 * 1024 * 1024
_MAX_METADATA_DEPTH = 12
_MAX_METADATA_NODES = 20_000
_MAX_STRING_BYTES = _MAX_CACHE_BYTES
_MAX_CONCURRENT_OCR = 4
_LEASE_SECONDS = 30
_LEASE_RENEW_INTERVAL_SECONDS = 10
_POLL_INTERVAL_SECONDS = 0.05
_MAX_WAIT_SECONDS = 300.0
_COMPUTE_TIMEOUT_SECONDS = 300.0

_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_SCRIPT = """
local deleted = 0
for i = 1, #KEYS do
    if redis.call('GET', KEYS[i]) == ARGV[i] then
        deleted = deleted + redis.call('DEL', KEYS[i])
    end
end
return deleted
"""
_PUBLISH_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] or redis.call('GET', KEYS[2]) ~= ARGV[2] then
    return 0
end
redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""
_SENSITIVE_KEY_PARTS = (
    "base64",
    "image_bytes",
    "normalized_bytes",
    "data_uri",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "secret",
    "credential",
    "password",
)
_SENSITIVE_QUERY_NAMES = frozenset(
    {
        "token",
        "access_token",
        "key",
        "api_key",
        "signature",
        "sig",
        "secret",
        "password",
        "authorization",
    }
)
_DATA_URI_RE = re.compile(r"(?i)\bdata:[a-z0-9.+-]+/[a-z0-9.+-]+(?:;base64)?,")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/-]+=*")


class KBPreviewCacheError(RuntimeError):
    """A preview cache result is invalid or cannot be safely stored."""


class KBPreviewCacheUnavailable(KBPreviewCacheError):
    """Redis, its lease, or the cross-worker cache operation is unavailable."""


class KBPreviewCacheEntryTooLarge(KBPreviewCacheError):
    """The serialized OCR preview exceeds the fixed cache payload limit."""


@dataclass(frozen=True, slots=True)
class KBPreviewCacheEntry:
    """Reusable extraction output, split into document text and image metadata."""

    enriched_text: str
    image_metadata: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


ComputePreview = Callable[[], Awaitable[KBPreviewCacheEntry]]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise KBPreviewCacheError("Preview cache input is not canonical JSON") from exc


def _reject_sensitive_value(value: str) -> None:
    if _DATA_URI_RE.search(value) or _BEARER_RE.search(value):
        raise KBPreviewCacheError(
            "Preview metadata contains a binary URI or credential"
        )
    try:
        parsed = urlsplit(value)
        if parsed.scheme and (parsed.username or parsed.password):
            raise KBPreviewCacheError("Preview metadata contains URL credentials")
        if any(
            name.lower() in _SENSITIVE_QUERY_NAMES
            for name, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise KBPreviewCacheError("Preview metadata contains URL credentials")
    except ValueError as exc:
        raise KBPreviewCacheError("Preview metadata contains an invalid URI") from exc


def _validate_json_value(
    value: Any,
    *,
    budget: list[int],
    depth: int = 0,
    reject_sensitive: bool = True,
) -> None:
    if depth > _MAX_METADATA_DEPTH:
        raise KBPreviewCacheEntryTooLarge("Preview metadata nesting is too deep")
    budget[0] -= 1
    if budget[0] < 0:
        raise KBPreviewCacheEntryTooLarge("Preview metadata has too many values")

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KBPreviewCacheError("Preview metadata contains a non-finite number")
        return
    if isinstance(value, str):
        if reject_sensitive:
            _reject_sensitive_value(value)
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise KBPreviewCacheError(
                "Preview metadata contains invalid Unicode"
            ) from exc
        budget[1] -= size
        if budget[1] < 0:
            raise KBPreviewCacheEntryTooLarge(
                "Preview metadata exceeds the cache limit"
            )
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, budget=budget, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise KBPreviewCacheError("Preview metadata keys must be strings")
            normalized_key = key.lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise KBPreviewCacheError("Preview metadata contains a forbidden field")
            _validate_json_value(
                key,
                budget=budget,
                depth=depth + 1,
                reject_sensitive=reject_sensitive,
            )
            _validate_json_value(
                item,
                budget=budget,
                depth=depth + 1,
                reject_sensitive=reject_sensitive,
            )
        return
    raise KBPreviewCacheError("Preview metadata must contain JSON values only")


def preview_version(entry: KBPreviewCacheEntry) -> str:
    """Return a stable version for the exact preview entry content."""
    return hashlib.sha256(_canonical_json(_entry_json(entry))).hexdigest()


def _entry_json(entry: KBPreviewCacheEntry) -> dict[str, Any]:
    if not isinstance(entry, KBPreviewCacheEntry):
        raise KBPreviewCacheError("Preview computation returned an invalid entry")
    if not isinstance(entry.enriched_text, str):
        raise KBPreviewCacheError("Enriched preview text must be a string")
    if not isinstance(entry.image_metadata, list) or any(
        not isinstance(item, dict) for item in entry.image_metadata
    ):
        raise KBPreviewCacheError("Image metadata must be a list of JSON objects")
    if not isinstance(entry.metadata, dict):
        raise KBPreviewCacheError("Preview metadata must be a JSON object")

    budget = [_MAX_METADATA_NODES, _MAX_STRING_BYTES]
    _validate_json_value(entry.enriched_text, budget=budget, reject_sensitive=False)
    _validate_json_value(entry.image_metadata, budget=budget)
    _validate_json_value(entry.metadata, budget=budget)
    return {
        "enriched_text": entry.enriched_text,
        "image_metadata": entry.image_metadata,
        "metadata": entry.metadata,
    }


class _Lease:
    def __init__(self, redis: Any, owner_token: str) -> None:
        self.redis = redis
        self.owner_token = owner_token
        self.keys: list[str] = []
        self.lost = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def add(self, key: str) -> None:
        self.keys.append(key)

    def start(self) -> None:
        self._task = asyncio.create_task(self._renew())

    async def _renew(self) -> None:
        try:
            while True:
                await asyncio.sleep(_LEASE_RENEW_INTERVAL_SECONDS)
                for key in tuple(self.keys):
                    renewed = await self.redis.eval(
                        _RENEW_SCRIPT,
                        1,
                        key,
                        self.owner_token,
                        _LEASE_SECONDS,
                    )
                    if not renewed:
                        self.lost.set()
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            self.lost.set()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


class KBPreviewCache:
    """Redis-backed temporary cache with distributed single-flight and a global cap."""

    def __init__(
        self,
        *,
        ttl_seconds: int = _CACHE_TTL_SECONDS,
        max_concurrent_ocr: int = _MAX_CONCURRENT_OCR,
        lease_seconds: int = _LEASE_SECONDS,
        lease_renew_interval_seconds: int = _LEASE_RENEW_INTERVAL_SECONDS,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
        max_wait_seconds: float = _MAX_WAIT_SECONDS,
        compute_timeout_seconds: float = _COMPUTE_TIMEOUT_SECONDS,
        redis_factory: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        if min(ttl_seconds, max_concurrent_ocr, lease_seconds) <= 0:
            raise ValueError("Cache TTL, concurrency, and lease must be positive")
        if not 0 < lease_renew_interval_seconds < lease_seconds:
            raise ValueError("Lease renewal interval must be shorter than the lease")
        if min(poll_interval_seconds, max_wait_seconds, compute_timeout_seconds) <= 0:
            raise ValueError("Cache timing limits must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_concurrent_ocr = max_concurrent_ocr
        self.lease_seconds = lease_seconds
        self.lease_renew_interval_seconds = lease_renew_interval_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds
        self.compute_timeout_seconds = compute_timeout_seconds
        self.redis_factory = redis_factory or get_redis

    def _keys(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        source: bytes,
        clean_text: bool,
        model: str | None,
        policy: str,
    ) -> tuple[str, str, str]:
        source_hash = hashlib.sha256(source).hexdigest()
        configuration_hash = hashlib.sha256(
            _canonical_json(
                {"clean_text": clean_text, "model": model, "policy": policy}
            )
        ).hexdigest()
        identity = {
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "source_hash": source_hash,
            "configuration_hash": configuration_hash,
        }
        fingerprint = hashlib.sha256(_canonical_json(identity)).hexdigest()
        prefix = f"{_CACHE_PREFIX}:{fingerprint}"
        return f"{prefix}:entry", f"{prefix}:lock", fingerprint

    async def _get_entry(
        self,
        redis: Any,
        cache_key: str,
        *,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        fingerprint: str,
    ) -> KBPreviewCacheEntry | None:
        try:
            raw = await redis.get(cache_key)
        except Exception as exc:
            raise KBPreviewCacheUnavailable("Preview cache read failed") from exc
        if raw is None:
            return None
        try:
            if isinstance(raw, bytes):
                if len(raw) > _MAX_CACHE_BYTES:
                    raise KBPreviewCacheEntryTooLarge(
                        "Cached preview exceeds the limit"
                    )
                raw = raw.decode("utf-8")
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_CACHE_BYTES:
                raise KBPreviewCacheEntryTooLarge("Cached preview exceeds the limit")
            record = json.loads(raw)
            expected_identity = {
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "fingerprint": fingerprint,
            }
            if record.get("identity") != expected_identity:
                raise KBPreviewCacheUnavailable("Cached preview identity mismatch")
            if float(record["expires_at"]) <= time.time():
                return None
            entry_data = record["entry"]
            entry = KBPreviewCacheEntry(
                enriched_text=entry_data["enriched_text"],
                image_metadata=entry_data["image_metadata"],
                metadata=entry_data["metadata"],
            )
            _entry_json(entry)
            return entry
        except KBPreviewCacheError:
            raise
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise KBPreviewCacheUnavailable("Cached preview record is invalid") from exc

    async def _acquire_slot(self, redis: Any, owner_token: str) -> str | None:
        try:
            for index in range(self.max_concurrent_ocr):
                key = f"{_CACHE_PREFIX}:slot:{index}"
                acquired = await redis.set(
                    key, owner_token, ex=self.lease_seconds, nx=True
                )
                if acquired:
                    return key
        except Exception as exc:
            raise KBPreviewCacheUnavailable(
                "Global OCR lease acquisition failed"
            ) from exc
        return None

    async def _compute_with_lease(
        self, lease: _Lease, compute: ComputePreview
    ) -> KBPreviewCacheEntry:
        if lease.lost.is_set():
            raise KBPreviewCacheUnavailable("Preview cache lease was lost")
        try:
            compute_task = asyncio.create_task(compute())
        except Exception as exc:
            raise KBPreviewCacheError(
                "Preview computation must be asynchronous"
            ) from exc
        lost_task = asyncio.create_task(lease.lost.wait())
        try:
            done, _ = await asyncio.wait(
                {compute_task, lost_task},
                timeout=self.compute_timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if lost_task in done or lease.lost.is_set():
                compute_task.cancel()
                try:
                    await compute_task
                except BaseException:
                    pass
                raise KBPreviewCacheUnavailable("Preview cache lease was lost")
            if compute_task not in done:
                compute_task.cancel()
                try:
                    await compute_task
                except BaseException:
                    pass
                raise KBPreviewCacheUnavailable("Preview computation timed out")
            result = await compute_task
            if lease.lost.is_set():
                raise KBPreviewCacheUnavailable("Preview cache lease was lost")
            return result
        finally:
            if not compute_task.done():
                compute_task.cancel()
            try:
                await compute_task
            except BaseException:
                pass
            lost_task.cancel()
            try:
                await lost_task
            except asyncio.CancelledError:
                pass

    async def _release(self, redis: Any, keys: list[str], owner_token: str) -> None:
        if not keys:
            return
        try:
            await redis.eval(
                _RELEASE_SCRIPT,
                len(keys),
                *keys,
                *(owner_token for _ in keys),
            )
        except Exception:
            # Leases expire automatically; cleanup must not mask the real result.
            return

    async def get_existing(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        source: bytes,
        clean_text: bool,
        model: str | None,
        policy: str,
    ) -> KBPreviewCacheEntry | None:
        """Return only a source/config-matching entry, without computing."""
        if not isinstance(source, bytes):
            raise KBPreviewCacheError("Preview source must be bytes")
        if not isinstance(clean_text, bool):
            raise KBPreviewCacheError("clean_text must be a boolean")
        if model is not None and not isinstance(model, str):
            raise KBPreviewCacheError("model must be a string or None")
        if not isinstance(policy, str):
            raise KBPreviewCacheError("policy must be a string")
        identifiers = (user_id, knowledge_base_id, document_id)
        if any(not str(value) for value in identifiers):
            raise KBPreviewCacheError(
                "User, knowledge base, and document IDs are required"
            )
        user_id, knowledge_base_id, document_id = map(str, identifiers)
        cache_key, _, fingerprint = self._keys(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            source=source,
            clean_text=clean_text,
            model=model,
            policy=policy,
        )
        try:
            redis = await self.redis_factory()
        except Exception as exc:
            raise KBPreviewCacheUnavailable("Preview cache is unavailable") from exc
        return await self._get_entry(
            redis,
            cache_key,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            fingerprint=fingerprint,
        )

    async def get_or_create(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        document_id: str,
        source: bytes,
        clean_text: bool,
        model: str | None,
        policy: str,
        compute: ComputePreview,
        refresh: bool = False,
    ) -> KBPreviewCacheEntry:
        """Return a matching entry or compute/publish it under distributed leases.

        Redis failures, lease loss, lock wait exhaustion, computation timeout,
        and oversize results raise explicitly; there is no local-cache bypass.
        """
        if not isinstance(source, bytes):
            raise KBPreviewCacheError("Preview source must be bytes")
        if not isinstance(clean_text, bool):
            raise KBPreviewCacheError("clean_text must be a boolean")
        if model is not None and not isinstance(model, str):
            raise KBPreviewCacheError("model must be a string or None")
        if not isinstance(policy, str):
            raise KBPreviewCacheError("policy must be a string")
        identifiers = (user_id, knowledge_base_id, document_id)
        if any(not str(value) for value in identifiers):
            raise KBPreviewCacheError(
                "User, knowledge base, and document IDs are required"
            )
        user_id, knowledge_base_id, document_id = map(str, identifiers)
        cache_key, lock_key, fingerprint = self._keys(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            source=source,
            clean_text=clean_text,
            model=model,
            policy=policy,
        )
        try:
            redis = await self.redis_factory()
        except Exception as exc:
            raise KBPreviewCacheUnavailable("Preview cache is unavailable") from exc

        deadline = asyncio.get_running_loop().time() + self.max_wait_seconds
        identity = {
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "document_id": document_id,
            "fingerprint": fingerprint,
        }

        while True:
            cached = await self._get_entry(
                redis,
                cache_key,
                user_id=user_id,
                knowledge_base_id=knowledge_base_id,
                document_id=document_id,
                fingerprint=fingerprint,
            )
            if cached is not None and not refresh:
                return cached

            owner_token = secrets.token_urlsafe(24)
            try:
                acquired = await redis.set(
                    lock_key, owner_token, ex=self.lease_seconds, nx=True
                )
            except Exception as exc:
                raise KBPreviewCacheUnavailable(
                    "Preview single-flight lock failed"
                ) from exc

            if acquired:
                lease = _Lease(redis, owner_token)
                lease.add(lock_key)
                lease.start()
                slot_key: str | None = None
                published = False
                try:
                    # A preceding owner may have committed between the first read
                    # and lock acquisition; check again before spending model quota.
                    cached = await self._get_entry(
                        redis,
                        cache_key,
                        user_id=user_id,
                        knowledge_base_id=knowledge_base_id,
                        document_id=document_id,
                        fingerprint=fingerprint,
                    )
                    if cached is not None and not refresh:
                        return cached

                    while slot_key is None:
                        if lease.lost.is_set():
                            raise KBPreviewCacheUnavailable(
                                "Preview cache lease was lost"
                            )
                        slot_key = await self._acquire_slot(redis, owner_token)
                        if slot_key is not None:
                            lease.add(slot_key)
                            break
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise KBPreviewCacheUnavailable(
                                "Global OCR capacity wait timed out"
                            )
                        await asyncio.sleep(min(self.poll_interval_seconds, remaining))

                    result = await self._compute_with_lease(lease, compute)
                    entry = _entry_json(result)
                    record = {
                        "identity": identity,
                        "expires_at": time.time() + self.ttl_seconds,
                        "entry": entry,
                    }
                    encoded = _canonical_json(record)
                    if len(encoded) > _MAX_CACHE_BYTES:
                        raise KBPreviewCacheEntryTooLarge(
                            "Serialized preview exceeds the 5 MiB cache limit"
                        )

                    # Stop renewal only for the short atomic commit. The script
                    # verifies both lease tokens before writing or releasing either.
                    await lease.stop()
                    try:
                        committed = await redis.eval(
                            _PUBLISH_SCRIPT,
                            3,
                            lock_key,
                            slot_key,
                            cache_key,
                            owner_token,
                            owner_token,
                            encoded.decode("utf-8"),
                            self.ttl_seconds,
                        )
                    except Exception as exc:
                        raise KBPreviewCacheUnavailable(
                            "Preview cache publish failed"
                        ) from exc
                    if not committed:
                        raise KBPreviewCacheUnavailable(
                            "Preview cache lease was lost before publish"
                        )
                    published = True
                    return result
                finally:
                    await lease.stop()
                    if not published:
                        await self._release(
                            redis,
                            [lock_key, *([slot_key] if slot_key is not None else [])],
                            owner_token,
                        )

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise KBPreviewCacheUnavailable("Preview single-flight wait timed out")
            await asyncio.sleep(min(self.poll_interval_seconds, remaining))


_cache: KBPreviewCache | None = None


def get_kb_preview_cache() -> KBPreviewCache:
    """Return the process-level facade; all data and leases remain in Redis."""
    global _cache
    if _cache is None:
        _cache = KBPreviewCache()
    return _cache
