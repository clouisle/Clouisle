from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from typing import Any

import pytest
import pytest_asyncio

from app.services import kb_preview_cache as preview_module
from app.services.kb_preview_cache import (
    KBPreviewCache,
    KBPreviewCacheEntry,
    KBPreviewCacheEntryTooLarge,
    KBPreviewCacheError,
    KBPreviewCacheUnavailable,
    _Lease,
    _canonical_json,
    _entry_json,
    _reject_sensitive_value,
    _validate_json_value,
    get_kb_preview_cache,
)


class FakeRedis:
    """Small atomic Redis stand-in for cache behavior tests."""

    def __init__(self) -> None:
        self.values: dict[str, tuple[str, float | None]] = {}
        self.fail = False

    def _value(self, key: str) -> str | None:
        value = self.values.get(key)
        if value is None:
            return None
        content, expires_at = value
        if expires_at is not None and expires_at <= time.monotonic():
            del self.values[key]
            return None
        return content

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("redis unavailable")
        return self._value(key)

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if self.fail:
            raise ConnectionError("redis unavailable")
        if nx and self._value(key) is not None:
            return False
        self.values[key] = (
            value,
            time.monotonic() + ex if ex is not None else None,
        )
        return True

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        if self.fail:
            raise ConnectionError("redis unavailable")
        keys = args[:numkeys]
        values = args[numkeys:]
        if "redis.call('EXPIRE'" in script:
            key, token, ttl = keys[0], values[0], int(values[1])
            if self._value(key) != token:
                return 0
            content, _ = self.values[key]
            self.values[key] = (content, time.monotonic() + ttl)
            return 1
        if "for i = 1, #KEYS do" in script:
            deleted = 0
            for key, token in zip(keys, values, strict=True):
                if self._value(key) == token:
                    del self.values[key]
                    deleted += 1
            return deleted
        if "redis.call('SET', KEYS[3]" in script:
            lock_key, slot_key, cache_key = keys
            lock_token, slot_token, content, ttl = values
            if (
                self._value(lock_key) != lock_token
                or self._value(slot_key) != slot_token
            ):
                return 0
            self.values[cache_key] = (content, time.monotonic() + int(ttl))
            self.values.pop(lock_key, None)
            self.values.pop(slot_key, None)
            return 1
        raise AssertionError("Unexpected Redis script")


@pytest_asyncio.fixture
async def redis() -> FakeRedis:
    return FakeRedis()


def _cache(redis: FakeRedis, **options: Any) -> KBPreviewCache:
    async def redis_factory() -> FakeRedis:
        return redis

    defaults: dict[str, Any] = {
        "poll_interval_seconds": 0.001,
        "max_wait_seconds": 2,
        "compute_timeout_seconds": 1,
    }
    defaults.update(options)
    return KBPreviewCache(redis_factory=redis_factory, **defaults)


def _entry(text: str = "plain text") -> KBPreviewCacheEntry:
    return KBPreviewCacheEntry(
        enriched_text=text,
        image_metadata=[
            {
                "ocr_text": "visible words",
                "description": "A label",
                "mime_type": "image/jpeg",
                "width": 12,
                "height": 8,
            }
        ],
        metadata={
            "media_assets": [{"kind": "image"}],
            "warnings": [],
            "char_count": len(text),
        },
    )


async def _get(cache: KBPreviewCache, *, compute, **overrides: Any):
    values = {
        "user_id": "user-1",
        "knowledge_base_id": "kb-1",
        "document_id": "doc-1",
        "source": b"same document source",
        "clean_text": True,
        "model": "vision-model-1",
        "policy": "ocr-policy-v1",
        "compute": compute,
    }
    values.update(overrides)
    return await cache.get_or_create(**values)


@pytest.mark.asyncio
async def test_repeated_preview_reuses_enriched_text_and_image_metadata(
    redis: FakeRedis,
) -> None:
    cache = _cache(redis)
    compute = 0

    async def extract() -> KBPreviewCacheEntry:
        nonlocal compute
        compute += 1
        return _entry("OCR enriched text")

    first = await _get(cache, compute=extract)
    second = await _get(cache, compute=extract)

    assert compute == 1
    assert second == first
    assert second.enriched_text == "OCR enriched text"
    assert second.image_metadata[0]["ocr_text"] == "visible words"
    assert second.metadata["char_count"] == len(second.enriched_text)


@pytest.mark.asyncio
async def test_cache_isolated_by_user_document_source_and_configuration(
    redis: FakeRedis,
) -> None:
    cache = _cache(redis)
    computes: list[str] = []

    async def extract() -> KBPreviewCacheEntry:
        computes.append("called")
        return _entry(str(len(computes)))

    await _get(cache, compute=extract)
    await _get(cache, compute=extract, user_id="user-2")
    await _get(cache, compute=extract, knowledge_base_id="kb-2")
    await _get(cache, compute=extract, document_id="doc-2")
    await _get(cache, compute=extract, source=b"changed source")
    await _get(cache, compute=extract, clean_text=False)
    await _get(cache, compute=extract, model="vision-model-2")
    await _get(cache, compute=extract, policy="ocr-policy-v2")
    await _get(cache, compute=extract)

    assert len(computes) == 8


@pytest.mark.asyncio
async def test_expired_preview_is_recomputed(redis: FakeRedis) -> None:
    cache = _cache(redis, ttl_seconds=1)
    count = 0

    async def extract() -> KBPreviewCacheEntry:
        nonlocal count
        count += 1
        return _entry(f"run {count}")

    assert (await _get(cache, compute=extract)).enriched_text == "run 1"
    await asyncio.sleep(1.05)
    assert (await _get(cache, compute=extract)).enriched_text == "run 2"
    assert count == 2


@pytest.mark.asyncio
async def test_separate_cache_instances_share_cross_worker_single_flight(
    redis: FakeRedis,
) -> None:
    worker_a = _cache(redis)
    worker_b = _cache(redis)
    started = asyncio.Event()
    count = 0

    async def extract() -> KBPreviewCacheEntry:
        nonlocal count
        count += 1
        started.set()
        await asyncio.sleep(0.03)
        return _entry("single flight")

    task_a = asyncio.create_task(_get(worker_a, compute=extract))
    await started.wait()
    task_b = asyncio.create_task(_get(worker_b, compute=extract))
    result_a, result_b = await asyncio.gather(task_a, task_b)

    assert count == 1
    assert result_a == result_b


@pytest.mark.asyncio
async def test_get_existing_returns_match_without_compute_and_misses_on_changes(
    redis: FakeRedis,
) -> None:
    cache = _cache(redis)
    compute_count = 0

    async def extract() -> KBPreviewCacheEntry:
        nonlocal compute_count
        compute_count += 1
        return _entry("reused preview")

    values = {
        "user_id": "user-1",
        "knowledge_base_id": "kb-1",
        "document_id": "doc-1",
        "source": b"same document source",
        "clean_text": True,
        "model": "vision-model-1",
        "policy": "ocr-policy-v1",
    }
    await cache.get_or_create(**values, compute=extract)

    assert await cache.get_existing(**values) == _entry("reused preview")
    assert await cache.get_existing(**{**values, "user_id": "user-2"}) is None
    assert await cache.get_existing(**{**values, "source": b"new source"}) is None
    assert compute_count == 1


@pytest.mark.asyncio
async def test_cache_unavailability_fails_closed_without_computing(
    redis: FakeRedis,
) -> None:
    redis.fail = True
    cache = _cache(redis)
    compute = False

    async def extract() -> KBPreviewCacheEntry:
        nonlocal compute
        compute = True
        return _entry()

    with pytest.raises(KBPreviewCacheUnavailable):
        await _get(cache, compute=extract)
    assert compute is False


@pytest.mark.asyncio
async def test_oversize_and_sensitive_metadata_are_never_cached(
    redis: FakeRedis,
) -> None:
    cache = _cache(redis)

    async def oversize() -> KBPreviewCacheEntry:
        return _entry("x" * (5 * 1024 * 1024 + 1))

    with pytest.raises(KBPreviewCacheEntryTooLarge):
        await _get(cache, compute=oversize)
    assert not any(key.endswith(":entry") for key in redis.values)

    async def sensitive() -> KBPreviewCacheEntry:
        return KBPreviewCacheEntry(
            enriched_text="text",
            metadata={"media_assets": [{"data_uri": "data:image/png;base64,abc"}]},
        )

    with pytest.raises(KBPreviewCacheError):
        await _get(cache, compute=sensitive)
    assert not any(key.endswith(":entry") for key in redis.values)


@pytest.mark.asyncio
async def test_preview_source_must_be_bytes(redis: FakeRedis) -> None:
    cache = _cache(redis)

    async def extract() -> KBPreviewCacheEntry:
        return _entry()

    with pytest.raises(KBPreviewCacheError):
        await _get(cache, compute=extract, source="not bytes")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sensitive_value",
    [
        "data:image/jpeg;base64,QUJD",
        "Bearer abc.def-123",
        "https://example.invalid/path?api_key=secret-value",
    ],
)
async def test_sensitive_payload_values_are_rejected_before_cache_write(
    redis: FakeRedis, sensitive_value: str
) -> None:
    cache = _cache(redis)

    async def extract() -> KBPreviewCacheEntry:
        return KBPreviewCacheEntry(
            enriched_text="text",
            metadata={"media_assets": [{"source": sensitive_value}]},
        )

    with pytest.raises(KBPreviewCacheError):
        await _get(cache, compute=extract)
    assert not any(key.endswith(":entry") for key in redis.values)


@pytest.mark.asyncio
async def test_media_asset_urls_are_cacheable(redis: FakeRedis) -> None:
    cache = _cache(redis)
    metadata = {
        "media_assets": [
            {
                "url": "/api/v1/knowledge-bases/kb/documents/doc/media/a.png",
                "path": "documents/kb/media/doc/a.png",
                "content_type": "image/png",
            }
        ]
    }

    async def compute() -> KBPreviewCacheEntry:
        return KBPreviewCacheEntry(
            enriched_text="![a](/api/v1/knowledge-bases/kb/documents/doc/media/a.png)",
            metadata=metadata,
        )

    entry = await _get(cache, compute=compute)
    assert entry.metadata["media_assets"][0]["url"].endswith("/media/a.png")


def test_canonical_json_and_sensitive_value_validation():
    with pytest.raises(KBPreviewCacheError, match="canonical JSON"):
        _canonical_json({1, 2})
    with pytest.raises(KBPreviewCacheError, match="URL credentials"):
        _reject_sensitive_value("https://user:pass@example.test/a")
    with pytest.raises(KBPreviewCacheError, match="URL credentials"):
        _reject_sensitive_value("https://example.test/a?token=secret")
    with pytest.raises(KBPreviewCacheError, match="invalid URI"):
        _reject_sensitive_value("http://[invalid")


def test_json_value_validation_limits(monkeypatch):
    with pytest.raises(KBPreviewCacheEntryTooLarge, match="nesting"):
        _validate_json_value(
            "x", budget=[100, 100], depth=preview_module._MAX_METADATA_DEPTH + 1
        )
    with pytest.raises(KBPreviewCacheEntryTooLarge, match="too many values"):
        _validate_json_value("x", budget=[0, 100])
    assert _reject_sensitive_value("Data: quarterly results") is None
    with pytest.raises(KBPreviewCacheError, match="binary URI"):
        _reject_sensitive_value("data:image/png;base64,abc")
    with pytest.raises(KBPreviewCacheError, match="non-finite"):
        _validate_json_value(float("inf"), budget=[100, 100])
    with pytest.raises(KBPreviewCacheError, match="forbidden field"):
        _validate_json_value({"api-key": "x"}, budget=[100, 100])
    with pytest.raises(KBPreviewCacheError, match="keys must be strings"):
        _validate_json_value({1: "x"}, budget=[100, 100])
    with pytest.raises(KBPreviewCacheError, match="JSON values only"):
        _validate_json_value({1, 2}, budget=[100, 100])
    with pytest.raises(KBPreviewCacheError, match="invalid Unicode"):
        _validate_json_value("\ud800", budget=[100, 100])
    with pytest.raises(KBPreviewCacheEntryTooLarge, match="cache limit"):
        _validate_json_value("long", budget=[100, 2])
    assert _validate_json_value(1.5, budget=[100, 100]) is None


def test_entry_json_validates_shape():
    with pytest.raises(KBPreviewCacheError, match="invalid entry"):
        _entry_json("not an entry")
    with pytest.raises(KBPreviewCacheError, match="must be a string"):
        _entry_json(KBPreviewCacheEntry(enriched_text=None))
    with pytest.raises(KBPreviewCacheError, match="list of JSON"):
        _entry_json(KBPreviewCacheEntry(enriched_text="x", image_metadata=["x"]))
    with pytest.raises(KBPreviewCacheError, match="JSON object"):
        _entry_json(KBPreviewCacheEntry(enriched_text="x", metadata=[]))


def test_cache_constructor_validates_timing():
    with pytest.raises(ValueError, match="positive"):
        KBPreviewCache(ttl_seconds=0)
    with pytest.raises(ValueError, match="shorter than"):
        KBPreviewCache(lease_seconds=10, lease_renew_interval_seconds=10)
    with pytest.raises(ValueError, match="timing limits"):
        KBPreviewCache(poll_interval_seconds=0)


@pytest.mark.asyncio
async def test_get_entry_rejects_oversize_identity_and_expiry(monkeypatch):
    cache = _cache(FakeRedis())
    monkeypatch.setattr(preview_module, "_MAX_CACHE_BYTES", 2)
    with pytest.raises(KBPreviewCacheEntryTooLarge):
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(return_value=b"xxxx")),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )
    with pytest.raises(KBPreviewCacheEntryTooLarge):
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(return_value=123)),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )
    monkeypatch.setattr(preview_module, "_MAX_CACHE_BYTES", 5 * 1024 * 1024)
    record = {
        "identity": {
            "user_id": "other",
            "knowledge_base_id": "kb",
            "document_id": "d",
            "fingerprint": "f",
        },
        "expires_at": time.time() + 10,
        "entry": {"enriched_text": "x", "image_metadata": [], "metadata": {}},
    }
    with pytest.raises(KBPreviewCacheUnavailable, match="identity"):
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(return_value=json.dumps(record))),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )

    record["identity"]["user_id"] = "u"
    record["expires_at"] = 0
    assert (
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(return_value=json.dumps(record))),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )
        is None
    )

    assert (
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(return_value=None)),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )
        is None
    )

    with pytest.raises(KBPreviewCacheUnavailable, match="read failed"):
        await cache._get_entry(
            SimpleNamespace(get=AsyncMock(side_effect=ConnectionError())),
            "k",
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            fingerprint="f",
        )


@pytest.mark.asyncio
async def test_get_existing_and_get_or_create_validate_inputs():
    cache = _cache(FakeRedis())
    common = {
        "user_id": "u",
        "knowledge_base_id": "kb",
        "document_id": "d",
        "source": b"x",
        "clean_text": True,
        "model": None,
        "policy": "p",
    }
    with pytest.raises(KBPreviewCacheError, match="clean_text"):
        await cache.get_existing(**{**common, "clean_text": "yes"})
    with pytest.raises(KBPreviewCacheError, match="model"):
        await cache.get_existing(**{**common, "model": 1})
    with pytest.raises(KBPreviewCacheError, match="policy"):
        await cache.get_existing(**{**common, "policy": None})
    with pytest.raises(KBPreviewCacheError, match="IDs are required"):
        await cache.get_existing(**{**common, "user_id": ""})

    async def compute():
        return _entry()

    with pytest.raises(KBPreviewCacheError, match="clean_text"):
        await cache.get_or_create(**{**common, "clean_text": "yes"}, compute=compute)
    with pytest.raises(KBPreviewCacheError, match="model"):
        await cache.get_or_create(**{**common, "model": 1}, compute=compute)
    with pytest.raises(KBPreviewCacheError, match="policy"):
        await cache.get_or_create(**{**common, "policy": None}, compute=compute)
    with pytest.raises(KBPreviewCacheError, match="IDs are required"):
        await cache.get_or_create(**{**common, "document_id": ""}, compute=compute)


@pytest.mark.asyncio
async def test_release_and_acquire_slot_edges(redis: FakeRedis, monkeypatch):
    cache = _cache(redis)
    await cache._release(redis, [], "owner")
    await cache._release(
        SimpleNamespace(eval=AsyncMock(side_effect=ConnectionError())), ["k"], "o"
    )

    redis.fail = True
    with pytest.raises(KBPreviewCacheUnavailable, match="acquisition"):
        await cache._acquire_slot(redis, "o")
    redis.fail = False


@pytest.mark.asyncio
async def test_acquire_slot_exhaustion_and_existing_singleton(redis: FakeRedis):
    cache = _cache(redis, max_concurrent_ocr=1)
    await redis.set("kb:preview:ocr:v1:slot:0", "other")
    assert await cache._acquire_slot(redis, "owner") is None
    assert isinstance(get_kb_preview_cache(), KBPreviewCache)


@pytest.mark.asyncio
async def test_compute_with_lease_rejects_non_async_and_lost_lease(redis: FakeRedis):
    cache = _cache(redis)
    lease = _Lease(redis, "owner")
    lease.lost.set()
    with pytest.raises(KBPreviewCacheUnavailable, match="lost"):
        await cache._compute_with_lease(lease, lambda: _entry())

    lease = _Lease(redis, "owner")
    with pytest.raises(KBPreviewCacheError, match="asynchronous"):
        await cache._compute_with_lease(lease, lambda: _entry())


@pytest.mark.asyncio
async def test_lease_renewal_marks_lost_when_token_expires(monkeypatch):
    monkeypatch.setattr(preview_module, "_LEASE_RENEW_INTERVAL_SECONDS", 0)
    redis = SimpleNamespace(eval=AsyncMock(side_effect=[1, 1, 0]))
    lease = _Lease(redis, "owner")
    lease.add("a")
    lease.add("b")
    await lease._renew()
    assert lease.lost.is_set()


@pytest.mark.asyncio
async def test_get_entry_accepts_valid_bytes_and_returns_entry(redis: FakeRedis):
    cache = _cache(redis)
    entry = _entry("cached")
    identity = {
        "user_id": "u",
        "knowledge_base_id": "kb",
        "document_id": "d",
        "fingerprint": "f",
    }
    record = {
        "identity": identity,
        "expires_at": time.time() + 10,
        "entry": {
            "enriched_text": entry.enriched_text,
            "image_metadata": entry.image_metadata,
            "metadata": entry.metadata,
        },
    }
    result = await cache._get_entry(
        SimpleNamespace(get=AsyncMock(return_value=json.dumps(record).encode())),
        "k",
        user_id="u",
        knowledge_base_id="kb",
        document_id="d",
        fingerprint="f",
    )
    assert result == entry


@pytest.mark.asyncio
async def test_compute_with_lease_lost_and_timeout(redis: FakeRedis):
    cache = _cache(redis)
    lease = _Lease(redis, "owner")
    started = asyncio.Event()

    async def blocked():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(cache._compute_with_lease(lease, blocked))
    await started.wait()
    lease.lost.set()
    with pytest.raises(KBPreviewCacheUnavailable, match="lost"):
        await task

    async def never():
        await asyncio.Event().wait()

    fast = _cache(redis, compute_timeout_seconds=0.01)
    with pytest.raises(KBPreviewCacheUnavailable, match="timed out"):
        await fast._compute_with_lease(_Lease(redis, "owner"), never)


@pytest.mark.asyncio
async def test_compute_with_lease_marks_lost_after_result(redis: FakeRedis):
    cache = _cache(redis)
    lease = _Lease(redis, "owner")

    async def compute():
        lease.lost.set()
        return _entry()

    with pytest.raises(KBPreviewCacheUnavailable, match="lost"):
        await cache._compute_with_lease(lease, compute)


@pytest.mark.asyncio
async def test_get_existing_rejects_non_bytes_source(redis: FakeRedis):
    cache = _cache(redis)
    with pytest.raises(KBPreviewCacheError, match="source must be bytes"):
        await cache.get_existing(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source="text",
            clean_text=True,
            model=None,
            policy="p",
        )


@pytest.mark.asyncio
async def test_get_or_create_returns_entry_found_after_lock(
    redis: FakeRedis, monkeypatch
):
    cache = _cache(redis)
    cached = _entry("second read")

    async def compute():
        return _entry("computed")

    monkeypatch.setattr(cache, "_get_entry", AsyncMock(side_effect=[None, cached]))
    assert (
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=compute,
        )
        == cached
    )


@pytest.mark.asyncio
async def test_get_or_create_slot_wait_and_success(redis: FakeRedis, monkeypatch):
    cache = _cache(redis)
    entry = _entry("slot")
    monkeypatch.setattr(cache, "_get_entry", AsyncMock(side_effect=[None, None]))

    async def acquire(_redis, token):
        await redis.set("slot", token)
        return "slot"

    calls = 0

    async def acquire_slot(_redis, token):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await acquire(_redis, token)

    monkeypatch.setattr(cache, "_acquire_slot", acquire_slot)
    result = await cache.get_or_create(
        user_id="u",
        knowledge_base_id="kb",
        document_id="d",
        source=b"x",
        clean_text=True,
        model=None,
        policy="p",
        compute=AsyncMock(return_value=entry),
    )
    assert result == entry


@pytest.mark.asyncio
async def test_get_or_create_lease_lost_while_waiting_for_slot(
    redis: FakeRedis, monkeypatch
):
    class LostLease(_Lease):
        def start(self):
            self.lost.set()

    monkeypatch.setattr(preview_module, "_Lease", LostLease)
    cache = _cache(redis)
    with pytest.raises(KBPreviewCacheUnavailable, match="lost"):
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=AsyncMock(return_value=_entry()),
        )


@pytest.mark.asyncio
async def test_get_or_create_capacity_wait_timeout(redis: FakeRedis, monkeypatch):
    cache = _cache(redis, max_wait_seconds=0.0001)
    monkeypatch.setattr(cache, "_get_entry", AsyncMock(return_value=None))
    monkeypatch.setattr(cache, "_acquire_slot", AsyncMock(return_value=None))
    with pytest.raises(KBPreviewCacheUnavailable, match="capacity wait timed out"):
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=AsyncMock(return_value=_entry()),
        )


@pytest.mark.asyncio
async def test_get_or_create_rejects_oversize_encoded_record(
    redis: FakeRedis, monkeypatch
):
    cache = _cache(redis)
    monkeypatch.setattr(preview_module, "_MAX_CACHE_BYTES", 100)
    with pytest.raises(KBPreviewCacheEntryTooLarge, match="Serialized preview"):
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=AsyncMock(return_value=_entry("x" * 10)),
        )


@pytest.mark.asyncio
async def test_get_or_create_publish_not_committed(redis: FakeRedis):
    class Uncommitted(FakeRedis):
        async def eval(self, script, numkeys, *args):
            if "redis.call('SET', KEYS[3]" in script:
                return 0
            return await super().eval(script, numkeys, *args)

    cache = _cache(Uncommitted())
    with pytest.raises(KBPreviewCacheUnavailable, match="before publish"):
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=AsyncMock(return_value=_entry()),
        )


@pytest.mark.asyncio
async def test_get_or_create_single_flight_timeout(redis: FakeRedis, monkeypatch):
    cache = _cache(redis, max_wait_seconds=0.0001)
    monkeypatch.setattr(cache, "_get_entry", AsyncMock(return_value=None))
    monkeypatch.setattr(redis, "set", AsyncMock(return_value=False))
    with pytest.raises(KBPreviewCacheUnavailable, match="single-flight wait timed out"):
        await cache.get_or_create(
            user_id="u",
            knowledge_base_id="kb",
            document_id="d",
            source=b"x",
            clean_text=True,
            model=None,
            policy="p",
            compute=AsyncMock(return_value=_entry()),
        )


def test_get_kb_preview_cache_returns_singleton():
    first = get_kb_preview_cache()
    assert get_kb_preview_cache() is first


@pytest.mark.asyncio
async def test_compute_with_lease_lost_after_compute(redis: FakeRedis, monkeypatch):
    cache = _cache(redis)
    lease = _Lease(redis, "owner")

    async def compute():
        lease.lost.set()
        return _entry()

    async def fake_wait(tasks, **_kwargs):
        return {task for task in tasks if task.get_coro().__name__ == "compute"}, set()

    monkeypatch.setattr(preview_module.asyncio, "wait", fake_wait)
    with pytest.raises(KBPreviewCacheUnavailable, match="lost"):
        await cache._compute_with_lease(lease, compute)


@pytest.mark.asyncio
async def test_enriched_text_may_contain_data_uris_and_bearer_strings(redis: FakeRedis):
    cache = _cache(redis)

    async def compute():
        return KBPreviewCacheEntry(
            enriched_text="See data:image/png;base64,abc and Bearer token123"
        )

    entry = await _get(cache, compute=compute)
    assert "data:image/png" in entry.enriched_text


@pytest.mark.asyncio
async def test_refresh_recomputes_cached_entry(redis: FakeRedis):
    cache = _cache(redis)

    async def first():
        return _entry("old")

    async def second():
        return _entry("new")

    assert (await _get(cache, compute=first)).enriched_text == "old"
    assert (
        await cache.get_or_create(
            user_id="user-1",
            knowledge_base_id="kb-1",
            document_id="doc-1",
            source=b"same document source",
            clean_text=True,
            model="vision-model-1",
            policy="ocr-policy-v1",
            compute=second,
            refresh=True,
        )
    ).enriched_text == "new"
