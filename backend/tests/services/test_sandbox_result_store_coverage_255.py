from unittest.mock import AsyncMock

import pytest

from app.services.sandbox import result_store as result_store_module
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.result_store import SandboxResultStore


@pytest.fixture
def redis(monkeypatch):
    client = AsyncMock()
    monkeypatch.setattr(
        result_store_module, "get_redis", AsyncMock(return_value=client)
    )
    return client


@pytest.mark.asyncio
async def test_save_and_load_result_with_explicit_ttl(redis):
    store = SandboxResultStore()
    result = SandboxResult(job_id="job-1", status=SandboxTaskStatus.COMPLETED)

    await store.save_result(result, ttl_seconds=30)
    payload = redis.setex.await_args_list[0].args[2]
    redis.get.return_value = payload

    assert (await store.get_result("job-1")).status is SandboxTaskStatus.COMPLETED
    assert result.metadata.status is SandboxTaskStatus.COMPLETED
    assert [call.args[:2] for call in redis.setex.await_args_list] == [
        ("sandbox:job:job-1", 30),
        ("sandbox:job:job-1:status", 30),
    ]


@pytest.mark.asyncio
async def test_missing_and_invalid_stored_values(redis):
    store = SandboxResultStore()
    redis.get.return_value = None

    assert await store.get_result("missing") is None
    assert await store.get_status("missing") is None

    redis.get.return_value = "unknown"
    with pytest.raises(ValueError):
        await store.get_status("job-1")


@pytest.mark.asyncio
async def test_create_and_update_results(monkeypatch):
    store = SandboxResultStore()
    save = AsyncMock()
    monkeypatch.setattr(store, "save_result", save)

    queued = await store.create_queued_result("job-1")
    assert queued.status is SandboxTaskStatus.QUEUED

    metadata = SandboxExecutionMetadata()
    monkeypatch.setattr(store, "get_result", AsyncMock(return_value=queued))
    completed = await store.update_status(
        "job-1",
        SandboxTaskStatus.COMPLETED,
        metadata=metadata,
        success=True,
        result={"value": 1},
    )
    assert completed.success is True
    assert completed.result == {"value": 1}
    assert completed.metadata is metadata
    assert metadata.status is SandboxTaskStatus.COMPLETED

    monkeypatch.setattr(store, "get_result", AsyncMock(return_value=None))
    failed = await store.update_status(
        "job-2", SandboxTaskStatus.FAILED, error="failed"
    )
    assert failed.error == "failed"
    assert failed.metadata.status is SandboxTaskStatus.FAILED

    without_metadata = SandboxResult.model_construct(job_id="job-3", metadata=None)
    monkeypatch.setattr(store, "get_result", AsyncMock(return_value=without_metadata))
    running = await store.update_status("job-3", SandboxTaskStatus.RUNNING)
    assert running.metadata is None
    assert save.await_count == 4


@pytest.mark.asyncio
async def test_status_lookup_and_delete(redis):
    store = SandboxResultStore()
    redis.get.return_value = "running"

    assert await store.get_status("job-1") is SandboxTaskStatus.RUNNING
    await store.delete("job-1")

    redis.delete.assert_awaited_once_with(
        "sandbox:job:job-1", "sandbox:job:job-1:status"
    )


@pytest.mark.asyncio
async def test_save_result_skips_metadata_status_when_metadata_is_none(redis):
    store = SandboxResultStore()
    result = SandboxResult(job_id="job-none", status=SandboxTaskStatus.COMPLETED)
    result.metadata = None

    await store.save_result(result, ttl_seconds=30)

    assert redis.setex.await_count == 2
    assert result.metadata is None
