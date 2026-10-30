from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
import pytest_asyncio

from app.services.kb_preview_cache import (
    KBPreviewCache,
    KBPreviewCacheEntry,
    KBPreviewCacheEntryTooLarge,
    KBPreviewCacheError,
    KBPreviewCacheUnavailable,
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

    return KBPreviewCache(
        redis_factory=redis_factory,
        poll_interval_seconds=0.001,
        max_wait_seconds=2,
        compute_timeout_seconds=1,
        **options,
    )


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
