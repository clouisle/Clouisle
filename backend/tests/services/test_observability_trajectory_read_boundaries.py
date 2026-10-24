"""Read/retention boundaries for observability trajectory detail.

Each test asserts a consumer-visible result: which spans the inspector may
show, whether a payload can be claimed complete, and how far bounded cleanup
progresses per cycle. No assertions on generated SQL or private defaults.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.models.observability import ObservabilityRun
from app.models.observability_payload import ObservabilityTrajectoryEntry
from app.services import observability_v2
from app.services.observability_v2 import trajectory_detail


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.fixture(autouse=True)
def isolated_telemetry_start(monkeypatch):
    monkeypatch.setattr(observability_v2, "_TELEMETRY_START", None)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_telemetry_start_caches_horizon_and_refreshes_after_ttl(
    monkeypatch, database
):
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(observability_v2, "monotonic", lambda: clock["now"])

    first_run_id = uuid4()
    first_submitted = datetime(2026, 10, 1, 12, tzinfo=UTC)
    await ObservabilityRun.create(
        id=first_run_id,
        source="agent",
        status="completed",
        submitted_at=first_submitted,
    )

    assert _utc(await observability_v2._telemetry_start()) == first_submitted

    # A run with older telemetry is recorded after the horizon was sampled.
    older_submitted = first_submitted - timedelta(hours=2)
    await ObservabilityRun.create(
        id=uuid4(),
        source="agent",
        status="completed",
        submitted_at=older_submitted,
    )

    clock["now"] += 1
    assert _utc(await observability_v2._telemetry_start()) == first_submitted

    # Once the sample expires the refreshed horizon includes the older run, so
    # coverage windows are no longer marked partial by a stale bound.
    clock["now"] += observability_v2._TELEMETRY_START_TTL_SECONDS + 1
    assert _utc(await observability_v2._telemetry_start()) == older_submitted


@pytest.mark.asyncio
async def test_telemetry_start_read_failure_degrades_to_unknown_horizon(monkeypatch):
    def unavailable(awaitable):
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise RuntimeError("telemetry store unavailable")

    monkeypatch.setattr(observability_v2, "run_bounded", unavailable)

    # An unreadable horizon must not break snapshot reads; it is reported as
    # unknown so the window is described as partial instead of fresh.
    assert await observability_v2._telemetry_start() is None
    assert observability_v2._TELEMETRY_START is None


@pytest.mark.asyncio
async def test_agent_trajectory_skips_spans_already_shown_as_captured_entries(
    monkeypatch, database
):
    captured_id = str(uuid4())
    captured = {
        "id": captured_id,
        "parent_id": None,
        "kind": "tool",
        "name": "read_asset",
        "status": "completed",
        "started_at": "2026-10-08T12:00:02+00:00",
        "finished_at": None,
        "duration_ms": 5,
        "model": None,
        "token_usage": None,
        "tool_call_ids": ["call-1"],
        "payload_state": "recorded",
        "preview": None,
        "_input_recorded": True,
    }

    async def captured_entries(_run_id, _limit):
        return [dict(captured)]

    monkeypatch.setattr(
        "app.services.observability_trajectory.trajectory_entries",
        captured_entries,
    )

    covered_by_call = {
        "span_id": str(uuid4()),
        "kind": "tool",
        "name": "http",
        "tool_call_id": "call-1",
        "status": "completed",
        "started_at": "2026-10-08T12:00:00+00:00",
    }
    covered_by_span = {
        "span_id": captured_id,
        "kind": "retrieval",
        "name": "search",
        "status": "completed",
        "started_at": "2026-10-08T12:00:01+00:00",
    }
    uncaptured = {
        "span_id": str(uuid4()),
        "kind": "tool",
        "name": "http",
        "tool_call_id": "call-2",
        "status": "completed",
        "started_at": "2026-10-08T11:59:59+00:00",
    }

    entries, truncated = await observability_v2._agent_trajectory(
        uuid4(),
        {"call-2": {"partial": False}},
        [covered_by_call, covered_by_span, uncaptured],
    )

    assert truncated is False
    # A dependency span already covered by a captured call id or entry id is
    # not duplicated; the uncaptured span still appears with output-only
    # context (request arguments were never recorded).
    assert [entry["id"] for entry in entries] == [
        uncaptured["span_id"],
        captured_id,
    ]
    assert entries[0]["payload_state"] == "partial"
    assert entries[1]["payload_state"] == "partial"
    assert all("_input_recorded" not in entry for entry in entries)


@pytest.mark.asyncio
async def test_agent_historical_span_detail_is_partial_and_never_recorded(database):
    run_id = uuid4()
    span_without_tool = uuid4()
    span_with_tool = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="agent",
        status="failed",
        submitted_at=datetime.now(UTC),
        dependency_metrics=[
            {
                "span_id": str(span_without_tool),
                "kind": "retrieval",
                "name": "search",
                "status": "failed",
                "duration_ms": 17,
                "error_category": "timeout",
            },
            {
                "span_id": str(span_with_tool),
                "kind": "tool",
                "name": "http",
                "tool_call_id": "call-9",
                "status": "completed",
                "duration_ms": 3,
            },
        ],
    )

    # Historical runs only kept dependency metrics, so no captured entry row
    # exists and the span is still addressable by its metric id.
    detail = await trajectory_detail("agent", run_id, str(span_without_tool))
    assert detail == {
        "id": str(span_without_tool),
        "kind": "retrieval",
        "input": None,
        "output": {
            "status": "failed",
            "duration_ms": 17,
            "error_category": "timeout",
        },
        "partial": True,
        "recorded": False,
    }

    with_tool = await trajectory_detail("agent", run_id, str(span_with_tool))
    assert with_tool["kind"] == "tool"
    assert with_tool["input"] == {"tool_call_id": "call-9", "name": "http"}
    assert with_tool["output"]["status"] == "completed"
    assert with_tool["output"]["duration_ms"] == 3
    assert with_tool["partial"] is True
    # Request arguments were never stored for legacy spans, so completeness
    # cannot be claimed even when the call id is known.
    assert with_tool["recorded"] is False


@pytest.mark.asyncio
async def test_agent_trajectory_detail_only_serves_spans_belonging_to_the_run(database):
    run_id = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="agent",
        status="completed",
        submitted_at=datetime.now(UTC),
    )

    # A well-formed id that is neither a captured entry nor a recorded
    # dependency span of this run is a not-found, not an empty payload.
    assert await trajectory_detail("agent", run_id, str(uuid4())) is None
    # Malformed ids are rejected the same way rather than surfacing an error.
    assert await trajectory_detail("agent", run_id, "not-a-uuid") is None

    # A span recorded under a different run cannot be read through this run id.
    foreign_span = str(uuid4())
    await ObservabilityRun.create(
        id=uuid4(),
        source="agent",
        status="failed",
        submitted_at=datetime.now(UTC),
        dependency_metrics=[
            {
                "span_id": foreign_span,
                "kind": "tool",
                "name": "http",
                "status": "failed",
            }
        ],
    )
    assert await trajectory_detail("agent", run_id, foreign_span) is None
    # The same run id under another source is a separate telemetry record.
    assert await trajectory_detail("workflow", run_id, foreign_span) is None


@pytest.mark.asyncio
async def test_tool_entry_with_corrupt_input_returns_raw_text_as_partial(database):
    run_id = uuid4()
    entry_id = uuid4()
    await ObservabilityRun.create(
        id=run_id,
        source="agent",
        status="completed",
        submitted_at=datetime.now(UTC),
    )
    await ObservabilityTrajectoryEntry.create(
        id=entry_id,
        run_id=run_id,
        sequence=1,
        kind="tool",
        name="http",
        status="completed",
        tool_call_ids=["call-1"],
        input_text="{not-json",
    )

    detail = await trajectory_detail("agent", run_id, str(entry_id))

    # Unparseable stored arguments are shown verbatim and cannot be presented
    # as a complete recorded exchange.
    assert detail["input"] == "{not-json"
    assert detail["output"] == {"status": "completed", "duration_ms": None}
    assert detail["partial"] is True
    assert detail["recorded"] is False


@pytest.mark.asyncio
async def test_retention_cycle_deletes_full_batches_until_cycle_limit(
    monkeypatch, database
):
    monkeypatch.setattr(observability_v2, "RETENTION_BATCH_SIZE", 2)
    monkeypatch.setattr(observability_v2, "RETENTION_BATCHES_PER_CYCLE", 2)
    cutoff = datetime.now(UTC) - timedelta(days=30)
    expired_at = cutoff - timedelta(minutes=5)
    entry_ids = [uuid4() for _ in range(4)]
    for sequence, entry_id in enumerate(entry_ids):
        await ObservabilityTrajectoryEntry.create(
            id=entry_id,
            run_id=uuid4(),
            sequence=sequence,
            kind="model",
            name="model",
            status="completed",
        )
    await ObservabilityTrajectoryEntry.all().update(created_at=expired_at)

    deleted = await observability_v2._retain_expired_trajectory(cutoff)

    # Two full batches fit in one cycle; the cycle ends on its bounded limit
    # rather than reading an empty batch, leaving nothing stale behind here.
    assert deleted == 4
    assert await ObservabilityTrajectoryEntry.all().count() == 0


@pytest.mark.asyncio
async def test_retention_cycle_without_expired_rows_keeps_recent_entries(database):
    cutoff = datetime.now(UTC) - timedelta(days=30)
    recent_id = uuid4()
    await ObservabilityTrajectoryEntry.create(
        id=recent_id,
        run_id=uuid4(),
        sequence=1,
        kind="model",
        name="model",
        status="completed",
    )

    # An empty first batch ends cleanup immediately; rows inside the window
    # are never touched.
    assert await observability_v2._retain_expired_trajectory(cutoff) == 0
    assert await ObservabilityTrajectoryEntry.filter(id=recent_id).exists() is True
