from unittest.mock import AsyncMock, call

import pytest

from app.services.sandbox import result_store
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.result_store import SandboxResultStore


@pytest.fixture
def redis():
    return AsyncMock()


@pytest.fixture
def store(redis, monkeypatch):
    monkeypatch.setattr(result_store, "get_redis", AsyncMock(return_value=redis))
    return SandboxResultStore()


@pytest.mark.asyncio
async def test_save_and_load_result_with_explicit_ttl(store, redis):
    result = SandboxResult(
        job_id="job-1",
        status=SandboxTaskStatus.COMPLETED,
        metadata=SandboxExecutionMetadata(),
    )

    await store.save_result(result, ttl_seconds=60)

    assert result.metadata.status is SandboxTaskStatus.COMPLETED
    redis.setex.assert_has_awaits(
        [
            call("sandbox:job:job-1", 60, result.model_dump_json()),
            call("sandbox:job:job-1:status", 60, "completed"),
        ]
    )

    redis.get.return_value = result.model_dump_json()
    assert await store.get_result("job-1") == result

    redis.get.return_value = None
    assert await store.get_result("missing") is None


@pytest.mark.asyncio
async def test_status_lookup_and_delete(store, redis):
    redis.get.side_effect = [None, "running"]

    assert await store.get_status("missing") is None
    assert await store.get_status("job-1") is SandboxTaskStatus.RUNNING

    await store.delete("job-1")
    redis.delete.assert_awaited_once_with(
        "sandbox:job:job-1", "sandbox:job:job-1:status"
    )


@pytest.mark.asyncio
async def test_create_and_update_results(store):
    store.save_result = AsyncMock()

    queued = await store.create_queued_result("queued")
    assert queued.status is SandboxTaskStatus.QUEUED
    assert queued.metadata.status is SandboxTaskStatus.QUEUED

    existing = SandboxResult(job_id="existing")
    store.get_result = AsyncMock(side_effect=[existing, None])

    updated = await store.update_status(
        "existing",
        SandboxTaskStatus.COMPLETED,
        success=True,
        result={"ok": True},
    )
    replacement_metadata = SandboxExecutionMetadata()
    created = await store.update_status(
        "new",
        SandboxTaskStatus.FAILED,
        metadata=replacement_metadata,
        error="failed",
    )

    assert updated is existing
    assert updated.success is True
    assert updated.result == {"ok": True}
    assert updated.metadata.status is SandboxTaskStatus.COMPLETED
    assert created.status is SandboxTaskStatus.FAILED
    assert created.metadata is replacement_metadata
    assert replacement_metadata.status is SandboxTaskStatus.FAILED
    assert created.error == "failed"
    assert store.save_result.await_count == 3
