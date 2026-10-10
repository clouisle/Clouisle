"""Stored-result decoding and cancellation boundaries, not Redis wiring copies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.sandbox import result_store
from app.services.sandbox.models import SandboxTaskStatus


def test_status_decodes_raw_redis_bytes(sandbox_runtime, monkeypatch):
    r = sandbox_runtime
    redis = SimpleNamespace(get=AsyncMock(return_value=b"queued"))
    monkeypatch.setattr(result_store, "get_redis", AsyncMock(return_value=redis))

    assert r.run(r.results.get_status("job")) == SandboxTaskStatus.QUEUED


def test_missing_and_invalid_stored_values(sandbox_runtime):
    r = sandbox_runtime
    assert r.run(r.results.get_result("missing")) is None
    assert r.run(r.results.get_status("missing")) is None
    r.redis.set("sandbox:job:invalid:status", "unknown")
    with pytest.raises(ValueError):
        r.run(r.results.get_status("invalid"))


def test_failure_can_be_published_without_preexisting_result(sandbox_runtime):
    r = sandbox_runtime
    failed = r.run(
        r.results.update_status("job", SandboxTaskStatus.FAILED, error="failed")
    )
    assert failed.error == "failed"
    assert failed.metadata.status == SandboxTaskStatus.FAILED
    cancelled = r.run(r.gateway.cancel("job", "late cancellation"))
    assert cancelled.status == SandboxTaskStatus.FAILED
    assert cancelled.error == "failed"


def test_cancelled_result_keeps_its_completed_timing(sandbox_runtime):
    r = sandbox_runtime
    r.run(r.results.create_queued_result("job"))
    cancelled = r.run(r.gateway.cancel("job", "cancelled"))
    assert cancelled.status == SandboxTaskStatus.CANCELLED
    assert cancelled.metadata.completed_at is not None
    assert cancelled.metadata.total_ms is not None
    r.run(r.results.update_status("job", SandboxTaskStatus.RUNNING, success=True))
    assert r.run(r.results.get_result("job")) == cancelled
