import asyncio
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import uuid4

import pytest

from app.services import observability_v2
from app.services.observability_v2 import (
    _decode_cursor,
    _encode_cursor,
    _meta_for,
    _percentile,
)


@pytest.fixture(autouse=True)
def isolated_instance_registry(monkeypatch):
    from app.services import observability_instances

    monkeypatch.setattr(
        observability_instances,
        "list_api_instances",
        AsyncMock(return_value={"available": True, "instances": []}),
    )


class _AwaitableQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filter_calls = []
        self.order_fields = ()
        self.limit_value = None

    def filter(self, *args, **kwargs):
        self.filter_calls.append((args, kwargs))
        return self

    def order_by(self, *fields):
        self.order_fields = fields
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def test_keyset_cursor_round_trips_timestamp_and_identity():
    timestamp = datetime(2026, 10, 8, 12, 30, tzinfo=UTC)
    cursor = _encode_cursor(timestamp, "run-id")
    assert _decode_cursor(cursor) == (timestamp, "run-id")


def test_invalid_keyset_cursor_is_rejected():
    with pytest.raises(ValueError, match="Invalid cursor"):
        _decode_cursor("not-a-cursor")


def test_percentiles_are_null_for_empty_samples():
    assert _percentile([], 0.95) is None


def test_percentiles_use_continuous_interpolation():
    assert _percentile([10, 20, 30, 40], 0.5) == 25
    assert _percentile([10, 20, 30, 40], 0.95) == 39


def test_metadata_does_not_fabricate_fresh_data_without_samples():
    start = datetime(2026, 10, 8, 12, tzinfo=UTC)
    end = datetime(2026, 10, 8, 13, tzinfo=UTC)
    assert _meta_for(start, end, 0)["state"] == "no_data"


@pytest.mark.asyncio
async def test_record_dependency_metrics_appends_and_preserves_truncation():
    run_id = uuid4()
    existing = [{"span_id": "existing"}]
    query = MagicMock()
    query.limit.return_value = query
    values = _AwaitableQuery(
        [
            {
                "dependency_metrics": existing,
                "dependency_metrics_truncated": False,
            }
        ]
    )
    query.values.return_value = values
    query.update = AsyncMock(return_value=1)
    metric = {"span_id": "new", "kind": "tool", "status": "completed"}

    with patch.object(observability_v2.ObservabilityRun, "filter", return_value=query):
        await observability_v2.record_dependency_metrics(
            run_id, [metric], truncated=True
        )

    query.update.assert_awaited_once_with(
        dependency_metrics=existing + [metric], dependency_metrics_truncated=True
    )
    query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_record_dependency_metrics_never_exceeds_run_cap():
    existing = [{"span_id": str(index)} for index in range(128)]
    query = MagicMock()
    query.limit.return_value = query
    values = _AwaitableQuery(
        [
            {
                "dependency_metrics": existing,
                "dependency_metrics_truncated": False,
            }
        ]
    )
    query.values.return_value = values
    query.update = AsyncMock(return_value=1)

    with patch.object(observability_v2.ObservabilityRun, "filter", return_value=query):
        await observability_v2.record_dependency_metrics(
            uuid4(), [{"span_id": "overflow"}]
        )

    stored = query.update.await_args.kwargs["dependency_metrics"]
    assert len(stored) == 128
    assert stored[-1]["span_id"] == "127"
    assert query.update.await_args.kwargs["dependency_metrics_truncated"] is True
    query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_dependencies_aggregate_tool_and_retrieval_outcomes():
    query = MagicMock()
    query.exclude.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.values.return_value = query
    model_rows = [
        {
            "model_name": "provider/model",
            "status": "completed",
            "execution_duration_ms": 100,
            "first_token_ms": 25,
            "total_tokens": 42,
        }
    ]
    dependency_rows = [
        {
            "dependency_metrics": [
                {
                    "kind": "tool",
                    "name": "http",
                    "status": "completed",
                    "duration_ms": 10,
                },
                {"kind": "tool", "name": "http", "status": "failed", "duration_ms": 30},
                {
                    "kind": "retrieval",
                    "name": "knowledge_search",
                    "status": "completed",
                    "duration_ms": 20,
                },
            ]
        }
    ]

    with (
        patch.object(
            observability_v2,
            "window",
            return_value=(
                datetime(2026, 10, 8, tzinfo=UTC),
                datetime(2026, 10, 9, tzinfo=UTC),
            ),
        ),
        patch.object(observability_v2.ObservabilityRun, "filter", return_value=query),
        patch.object(
            observability_v2,
            "run_bounded",
            new=AsyncMock(side_effect=[model_rows, dependency_rows]),
        ),
    ):
        result = await observability_v2._dependencies_snapshot("1h", None)

    tool = result["tools"][0]
    assert (tool["name"], tool["requests"], tool["completed"], tool["failed"]) == (
        "http",
        2,
        1,
        1,
    )
    assert tool["success_rate"] == 0.5
    assert (tool["p50_ms"], tool["p95_ms"]) == (20, 29)
    assert tool["tokens"] is None
    retrieval = result["retrieval"][0]
    assert retrieval["name"] == "knowledge_search"
    assert retrieval["success_rate"] == 1.0
    assert retrieval["p95_ms"] == 20

    model = result["models"][0]
    assert (model["name"], model["requests"], model["completed"], model["failed"]) == (
        "provider/model",
        1,
        1,
        0,
    )
    assert (model["p50_ms"], model["p95_ms"], model["first_token_p95_ms"]) == (
        100,
        100,
        25,
    )
    assert model["tokens"] == 42


@pytest.mark.asyncio
async def test_agent_run_detail_includes_dependency_spans_and_truncation():
    run_id = uuid4()
    submitted_at = datetime(2026, 10, 8, tzinfo=UTC)
    span = {
        "span_id": "dependency-1",
        "kind": "retrieval",
        "name": "knowledge_search",
        "status": "failed",
        "started_at": submitted_at.isoformat(),
        "finished_at": submitted_at.isoformat(),
        "duration_ms": 17,
        "error_category": "tool_error",
    }
    row = SimpleNamespace(
        id=run_id,
        source="agent",
        resource_id="agent-id",
        resource_name="Agent",
        team_id="team-id",
        team_name="Team",
        status="failed",
        submitted_at=submitted_at,
        started_at=submitted_at,
        message_started_at=None,
        finished_at=submitted_at,
        queue_duration_ms=0,
        execution_duration_ms=17,
        total_duration_ms=17,
        first_token_ms=None,
        total_tokens=0,
        error_category="execution",
        error_code="tool_error",
        trace_available=True,
        trace_complete=False,
        dependency_metrics=[span],
        dependency_metrics_truncated=True,
        model_name="provider/model",
    )
    with patch.object(
        observability_v2.ObservabilityRun,
        "get_or_none",
        new=AsyncMock(return_value=row),
    ):
        detail = await observability_v2.run_detail("agent", run_id)

    assert detail["trace"]["truncated"] is True
    dependency_span = detail["spans"][1]
    assert dependency_span["parent_span_id"] == str(run_id)
    assert dependency_span["kind"] == "retrieval"
    assert dependency_span["status"] == "failed"
    assert dependency_span["duration_ms"] == 17


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


def _install_alert_evaluation(
    monkeypatch, statuses, active, *, locked_rule_enabled=True
):
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    connection = object()
    rule = SimpleNamespace(
        id="agent-failure-rate",
        name="Agent failure rate",
        threshold=0.2,
        enabled=True,
        evaluation_window_seconds=300,
        recovery_window_seconds=600,
    )
    rules_query = MagicMock()
    rules_query.limit = AsyncMock(return_value=[rule])
    locked_rule_query = MagicMock()
    locked_rule_query.using_db.return_value = locked_rule_query
    locked_rule_query.select_for_update.return_value = locked_rule_query
    locked_rule = SimpleNamespace(**vars(rule))
    locked_rule.enabled = locked_rule_enabled
    locked_rule_query.first = AsyncMock(return_value=locked_rule)

    def filter_rules(**kwargs):
        return rules_query if kwargs == {"enabled": True} else locked_rule_query

    monkeypatch.setattr(
        observability_v2.ObservabilityAlertRule,
        "filter",
        MagicMock(side_effect=filter_rules),
    )
    event_query = MagicMock()
    event_query.using_db.return_value = event_query
    event_query.first = AsyncMock(return_value=active)
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent,
        "filter",
        MagicMock(return_value=event_query),
    )
    monkeypatch.setattr(observability_v2, "utcnow", lambda: now)
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", MagicMock())
    monkeypatch.setattr(
        observability_v2,
        "run_bounded",
        AsyncMock(
            return_value=[
                SimpleNamespace(source="agent", status=status, submitted_at=now)
                for status in statuses
            ]
        ),
    )
    monkeypatch.setattr(
        "tortoise.transactions.in_transaction", lambda: _Transaction(connection)
    )
    create_event = AsyncMock()
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "create", create_event
    )
    return now, create_event, connection


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected_events"),
    [
        (["failed"] * 9, 0),
        (["failed"] * 2 + ["completed"] * 8, 1),
        (["failed"] + ["completed"] * 9, 0),
    ],
)
async def test_alert_opens_only_after_minimum_sample_and_threshold(
    monkeypatch, statuses, expected_events
):
    _, create_event, _ = _install_alert_evaluation(monkeypatch, statuses, active=None)

    await observability_v2.evaluate_alert_rules()

    assert create_event.await_count == expected_events
    if expected_events:
        event = create_event.await_args.kwargs
        assert event["status"] == "active"
        assert event["affected_count"] == 2


@pytest.mark.asyncio
async def test_alert_evaluation_does_not_duplicate_active_event(monkeypatch):
    active = SimpleNamespace(status="active")
    _, create_event, _ = _install_alert_evaluation(
        monkeypatch, ["failed"] * 10, active=active
    )

    await observability_v2.evaluate_alert_rules()

    create_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected_status"),
    [
        (["completed"] * 9, "active"),
        (["completed"] * 9 + ["failed"], "active"),
        (["completed"] * 10, "resolved"),
    ],
)
async def test_active_alert_resolves_only_after_ten_clean_outcomes(
    monkeypatch, statuses, expected_status
):
    active = SimpleNamespace(status="active", resolved_at=None, save=AsyncMock())
    now, _, connection = _install_alert_evaluation(monkeypatch, statuses, active=active)

    await observability_v2.evaluate_alert_rules()

    assert active.status == expected_status
    if expected_status == "resolved":
        assert active.resolved_at == now
        active.save.assert_awaited_once_with(
            using_db=connection, update_fields=["status", "resolved_at"]
        )
    else:
        active.save.assert_not_awaited()


def _workflow_observability_row(run_id):
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    return SimpleNamespace(
        id=run_id,
        source="workflow",
        resource_id="workflow-id",
        resource_name="Published workflow",
        team_id="team-id",
        team_name="Team",
        status="completed",
        submitted_at=now,
        started_at=now,
        message_started_at=None,
        finished_at=now,
        queue_duration_ms=0,
        execution_duration_ms=30,
        total_duration_ms=30,
        model_name=None,
        first_token_ms=None,
        total_tokens=0,
        error_category=None,
        error_code=None,
        trace_available=True,
        trace_complete=False,
        dependency_metrics=[],
        dependency_metrics_truncated=False,
    )


def _workflow_node_row(node_id, order, name):
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    return {
        "id": node_id,
        "node_type": "tool",
        "node_name": name,
        "execution_order": order,
        "status": "completed",
        "queued_at": now,
        "started_at": now,
        "finished_at": now,
        "queue_duration_ms": 0,
        "execution_duration_ms": 30,
        "model_used": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "error_type": None,
        "retry_count": 0,
    }


@pytest.mark.asyncio
async def test_workflow_detail_uses_persisted_execution_names(monkeypatch):
    run_id = uuid4()
    row = _workflow_observability_row(run_id)
    workflow_query = MagicMock()
    workflow_query.values.return_value.first = AsyncMock(
        return_value={"total_nodes": 1}
    )
    node_query = MagicMock()
    node_query.order_by.return_value = node_query
    node_query.limit.return_value = node_query
    node_query.values.return_value = node_query
    node_rows = [_workflow_node_row(uuid4(), 1, "Name saved when this run executed")]
    node_rows[0]["status"] = SimpleNamespace(value="completed")

    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "get_or_none",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.models.workflow.WorkflowRun.filter", MagicMock(return_value=workflow_query)
    )
    monkeypatch.setattr(
        "app.models.workflow.NodeExecution.filter", MagicMock(return_value=node_query)
    )
    monkeypatch.setattr(
        observability_v2, "run_bounded", AsyncMock(return_value=node_rows)
    )

    detail = await observability_v2.run_detail("workflow", run_id)

    assert detail["spans"][1]["name"] == "Name saved when this run executed"
    assert detail["spans"][1]["status"] == "completed"
    assert detail["spans"][1]["metadata"]["node_type"] == "tool"
    assert detail["trace"] == {
        "complete": True,
        "expired": False,
        "truncated": False,
        "recorded_count": 2,
    }


@pytest.mark.asyncio
async def test_workflow_detail_marks_pruned_execution_rows_expired(monkeypatch):
    run_id = uuid4()
    row = _workflow_observability_row(run_id)
    workflow_query = MagicMock()
    workflow_query.values.return_value.first = AsyncMock(return_value=None)
    node_filter = MagicMock()

    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "get_or_none",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.models.workflow.WorkflowRun.filter", MagicMock(return_value=workflow_query)
    )
    monkeypatch.setattr("app.models.workflow.NodeExecution.filter", node_filter)

    detail = await observability_v2.run_detail("workflow", run_id)

    assert detail["trace"]["expired"] is True
    assert detail["trace"]["complete"] is False
    assert len(detail["spans"]) == 1
    node_filter.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_detail_caps_node_rows_and_marks_trace_truncated(monkeypatch):
    run_id = uuid4()
    row = _workflow_observability_row(run_id)
    workflow_query = MagicMock()
    workflow_query.values.return_value.first = AsyncMock(
        return_value={"total_nodes": 101}
    )
    node_query = MagicMock()
    node_query.order_by.return_value = node_query
    node_query.limit.return_value = node_query
    node_query.values.return_value = node_query
    node_rows = [
        _workflow_node_row(uuid4(), index, f"Node {index}") for index in range(101)
    ]

    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "get_or_none",
        AsyncMock(return_value=row),
    )
    monkeypatch.setattr(
        "app.models.workflow.WorkflowRun.filter", MagicMock(return_value=workflow_query)
    )
    monkeypatch.setattr(
        "app.models.workflow.NodeExecution.filter", MagicMock(return_value=node_query)
    )
    monkeypatch.setattr(
        observability_v2, "run_bounded", AsyncMock(return_value=node_rows)
    )

    detail = await observability_v2.run_detail("workflow", run_id)

    assert len(detail["spans"]) == 101
    assert detail["trace"]["recorded_count"] == 101
    assert detail["trace"]["truncated"] is True
    assert detail["trace"]["complete"] is False
    node_query.limit.assert_called_once_with(101)


@pytest.mark.asyncio
async def test_workflow_submission_updates_one_summary_for_repeated_events(monkeypatch):
    run_id = uuid4()
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    query = MagicMock()
    query.update = AsyncMock(return_value=1)
    create = AsyncMock()
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2.ObservabilityRun, "create", create)
    run = SimpleNamespace(
        id=run_id,
        workflow_id=uuid4(),
        status="pending",
        created_at=now,
        started_at=None,
        finished_at=None,
        total_duration_ms=None,
    )
    workflow = SimpleNamespace(name="Workflow", team_id=uuid4())

    await observability_v2.record_workflow_submission(run, workflow)
    await observability_v2.record_workflow_submission(run, workflow)

    assert query.update.await_count == 2
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_page_fetches_only_one_extra_row_and_encodes_next_cursor(monkeypatch):
    start = datetime(2026, 10, 8, 11, tzinfo=UTC)
    submitted_at = datetime(2026, 10, 8, 12, tzinfo=UTC)
    rows = [_workflow_observability_row(uuid4()) for _ in range(3)]
    for row in rows:
        row.submitted_at = submitted_at
    query = MagicMock()
    query.order_by.return_value = query
    query.limit.return_value = query
    bounded = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        observability_v2,
        "window",
        lambda _period, _start=None, _end=None: (start, submitted_at),
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "filter",
        MagicMock(return_value=query),
    )
    monkeypatch.setattr(observability_v2, "run_bounded", bounded)

    page = await observability_v2.list_runs(
        period="1h",
        team_id=None,
        source="all",
        status=None,
        error_category=None,
        run_id=None,
        cursor=None,
        limit=2,
    )

    assert len(page["items"]) == 2
    assert _decode_cursor(page["next_cursor"]) == (submitted_at, str(rows[1].id))
    query.limit.assert_called_once_with(3)
    bounded.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_caps_database_sample_and_marks_partial(monkeypatch):
    start = datetime(2026, 10, 8, 11, tzinfo=UTC)
    end = datetime(2026, 10, 8, 12, tzinfo=UTC)
    rows = [_workflow_observability_row(uuid4()) for _ in range(3)]
    query = MagicMock()
    query.order_by.return_value = query
    query.limit.return_value = query
    monkeypatch.setattr(observability_v2, "DB_QUERY_LIMIT", 2)
    monkeypatch.setattr(
        observability_v2, "window", lambda _period, _start=None, _end=None: (start, end)
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "filter",
        MagicMock(return_value=query),
    )
    monkeypatch.setattr(observability_v2, "run_bounded", AsyncMock(return_value=rows))

    summary = await observability_v2._summary_snapshot("1h", None)

    query.limit.assert_called_once_with(3)
    assert summary["workflows"]["submitted"] == 2
    assert summary["meta"]["sample_count"] == 2
    assert summary["meta"]["state"] == "partial"


@pytest.mark.asyncio
async def test_dependency_queries_cap_rows_and_mark_partial_samples(monkeypatch):
    models = [
        {
            "model_name": "provider/model",
            "status": "completed",
            "execution_duration_ms": 20,
            "first_token_ms": 5,
            "total_tokens": 10,
        }
        for _ in range(3)
    ]
    dependency_rows = [
        {
            "dependency_metrics": [
                {
                    "kind": "tool",
                    "name": "http",
                    "status": "completed",
                    "duration_ms": 3,
                }
            ]
        }
        for _ in range(3)
    ]
    query = MagicMock()
    query.exclude.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.values.return_value = query
    bounded = AsyncMock(side_effect=[models, dependency_rows])
    monkeypatch.setattr(observability_v2, "DB_QUERY_LIMIT", 2)
    monkeypatch.setattr(observability_v2, "DEPENDENCY_RUN_LIMIT", 2)
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2, "run_bounded", bounded)

    result = await observability_v2._dependencies_snapshot("1h", None)

    assert [args.args for args in query.limit.call_args_list] == [(3,), (3,)]
    assert result["models"][0]["requests"] == 2
    assert result["tools"][0]["requests"] == 2
    assert result["meta"]["state"] == "partial"


@pytest.mark.asyncio
async def test_retention_batches_expired_rows_and_preserves_active_alerts(monkeypatch):
    run_ids = [[uuid4(), uuid4()], [uuid4()]]
    run_select = MagicMock()
    run_select.order_by.return_value = run_select
    run_select.limit.return_value = run_select
    run_select.values_list = AsyncMock(side_effect=run_ids)
    run_delete = MagicMock()
    run_delete.delete = AsyncMock(side_effect=[2, 1])
    run_filter = MagicMock(
        side_effect=lambda **values: (
            run_select if "submitted_at__lt" in values else run_delete
        )
    )

    alert_id = uuid4()
    alert_select = MagicMock()
    alert_select.order_by.return_value = alert_select
    alert_select.limit.return_value = alert_select
    alert_select.values_list = AsyncMock(return_value=[alert_id])
    alert_delete = MagicMock()
    alert_delete.delete = AsyncMock(return_value=1)
    alert_filter = MagicMock(
        side_effect=lambda **values: (
            alert_select if "opened_at__lt" in values else alert_delete
        )
    )
    monkeypatch.setattr(observability_v2, "RETENTION_BATCH_SIZE", 2)
    monkeypatch.setattr(observability_v2, "RETENTION_BATCHES_PER_CYCLE", 2)
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", run_filter)
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "filter", alert_filter
    )

    deleted = await observability_v2.retain()

    assert deleted == 4
    assert run_select.values_list.await_count == 2
    assert run_delete.delete.await_count == 2
    assert alert_select.values_list.await_count == 1
    assert alert_filter.call_args_list[0].kwargs["status"] == "resolved"
    alert_delete.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_snapshot_coalesces_concurrent_producers(monkeypatch):
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_LOCK", asyncio.Lock())
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def produce():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"sample": calls}

    first = asyncio.create_task(observability_v2._cached_snapshot(("test",), produce))
    await started.wait()
    second = asyncio.create_task(observability_v2._cached_snapshot(("test",), produce))
    release.set()

    first_result, second_result = await asyncio.gather(first, second)
    cached_result = await observability_v2._cached_snapshot(("test",), produce)

    assert calls == 1
    assert first_result == second_result == cached_result == {"sample": 1}


@pytest.mark.asyncio
async def test_cached_snapshot_expires_stale_entries_and_bounds_cache(monkeypatch):
    expired = ("expired",)
    survivor = ("survivor",)
    new_key = ("new",)
    monkeypatch.setattr(
        observability_v2,
        "_SNAPSHOT_CACHE",
        {expired: (9.0, "stale"), survivor: (20.0, "old")},
    )
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_LOCK", asyncio.Lock())
    monkeypatch.setattr(observability_v2, "_CACHE_MAX_ENTRIES", 1)
    monkeypatch.setattr(observability_v2, "monotonic", lambda: 10.0)

    result = await observability_v2._cached_snapshot(
        new_key, AsyncMock(return_value="fresh"), ttl=5
    )

    assert result == "fresh"
    assert expired not in observability_v2._SNAPSHOT_CACHE
    assert survivor not in observability_v2._SNAPSHOT_CACHE
    assert observability_v2._SNAPSHOT_CACHE[new_key] == (15.0, "fresh")


@pytest.mark.asyncio
async def test_record_run_creates_normalized_summary_when_upsert_has_no_match(
    monkeypatch,
):
    run_id = uuid4()
    submitted = datetime(2026, 10, 8, 12, tzinfo=UTC)
    started = submitted + timedelta(seconds=2)
    finished = submitted + timedelta(seconds=5)
    query = MagicMock()
    query.update = AsyncMock(return_value=0)
    create = AsyncMock()
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2.ObservabilityRun, "create", create)

    await observability_v2.record_run(
        run_id=run_id,
        source="agent",
        resource_id="agent-id",
        resource_name="Support agent",
        team_id="team-id",
        team_name="Support",
        status="failed",
        submitted_at=submitted,
        started_at=started,
        finished_at=finished,
        total_duration_ms=3000,
        execution_duration_ms=2500,
        total_tokens=-8,
        error_code="PROVIDER_TIMEOUT",
    )

    values = create.await_args.kwargs
    assert values["id"] == run_id
    assert values["source"] == "agent"
    assert values["queue_duration_ms"] == 2000
    assert values["total_duration_ms"] == 5000
    assert values["execution_duration_ms"] == 2500
    assert values["total_tokens"] == 0
    assert values["error_category"] == "timeout"
    assert values["trace_available"] is True
    assert values["trace_complete"] is False


@pytest.mark.asyncio
async def test_record_run_drops_database_failure_without_affecting_caller(caplog):
    with (
        caplog.at_level("WARNING", logger="app.services.observability_v2"),
        patch.object(
            observability_v2.ObservabilityRun,
            "filter",
            side_effect=RuntimeError("database unavailable"),
        ),
    ):
        await observability_v2.record_run(
            run_id=uuid4(),
            source="agent",
            resource_id=None,
            resource_name=None,
            team_id=None,
            team_name=None,
            status="failed",
            submitted_at=None,
            started_at=None,
            finished_at=None,
            total_duration_ms=None,
        )

    assert "Observability summary dropped" in caplog.text


@pytest.mark.asyncio
async def test_update_run_progress_guards_status_and_skips_empty_updates(monkeypatch):
    query = MagicMock()
    query.filter.return_value = query
    query.update = AsyncMock(return_value=1)
    run_filter = MagicMock(return_value=query)
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", run_filter)
    run_id = uuid4()
    started = datetime(2026, 10, 8, 12, tzinfo=UTC)

    await observability_v2.update_run_progress(run_id, source="agent")
    run_filter.assert_not_called()
    await observability_v2.update_run_progress(
        run_id,
        source="agent",
        status="running",
        expected_status="queued",
        started_at=started,
    )

    run_filter.assert_called_once_with(id=run_id, source="agent")
    query.filter.assert_called_once_with(status="queued")
    query.update.assert_awaited_once_with(started_at=started, status="running")


@pytest.mark.asyncio
async def test_update_run_progress_drops_slow_write(monkeypatch):
    query = MagicMock()
    query.filter.return_value = query
    query.update = AsyncMock(side_effect=asyncio.TimeoutError)
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )

    await observability_v2.update_run_progress(
        uuid4(), source="workflow", status="completed"
    )

    query.filter.assert_called_once_with(
        status__in=observability_v2.ACTIVE_RUN_STATUSES
    )
    query.update.assert_awaited_once_with(status="completed")


@pytest.mark.asyncio
async def test_record_dependency_metrics_ignores_empty_and_missing_rows(monkeypatch):
    run_filter = MagicMock()
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", run_filter)

    await observability_v2.record_dependency_metrics(uuid4(), [])
    run_filter.assert_not_called()

    values = _AwaitableQuery([])
    query = MagicMock()
    query.limit.return_value = query
    query.values.return_value = values
    query.update = AsyncMock()
    run_filter.return_value = query
    await observability_v2.record_dependency_metrics(
        uuid4(), [None, {"span_id": "orphan"}]
    )

    query.update.assert_not_awaited()
    query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_record_dependency_metrics_recovers_malformed_legacy_value(monkeypatch):
    query = MagicMock()
    query.limit.return_value = query
    values = _AwaitableQuery(
        [
            {
                "dependency_metrics": "legacy-invalid",
                "dependency_metrics_truncated": True,
            }
        ]
    )
    query.values.return_value = values
    query.update = AsyncMock(return_value=1)
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )

    await observability_v2.record_dependency_metrics(
        uuid4(), [None, {"span_id": "kept", "kind": "tool"}]
    )

    query.update.assert_awaited_once_with(
        dependency_metrics=[{"span_id": "kept", "kind": "tool"}],
        dependency_metrics_truncated=True,
    )
    query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_run_page_applies_all_filters_and_keyset_cursor(monkeypatch):
    start = datetime(2026, 10, 8, 11, tzinfo=UTC)
    end = datetime(2026, 10, 8, 12, tzinfo=UTC)
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    run_bounded = AsyncMock(return_value=[])
    cursor = _encode_cursor(start, "run-0")
    monkeypatch.setattr(
        observability_v2, "window", lambda _period, _start=None, _end=None: (start, end)
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2, "run_bounded", run_bounded)

    page = await observability_v2.list_runs(
        period="1h",
        team_id="team-1",
        source="agent",
        status="failed",
        error_category="provider",
        run_id="run-1",
        cursor=cursor,
        limit=25,
    )

    filter_calls = query.filter.call_args_list
    assert [item.kwargs for item in filter_calls[:5]] == [
        {"team_id": "team-1"},
        {"source": "agent"},
        {"status": "failed"},
        {"error_category": "provider"},
        {"id": "run-1"},
    ]
    assert len(filter_calls) == 6
    assert query.limit.call_args.args == (26,)
    assert page["items"] == []
    assert page["next_cursor"] is None
    assert page["meta"]["state"] == "no_data"
    run_bounded.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_run_detail_skips_invalid_dependency_spans(monkeypatch):
    run_id = uuid4()
    row = _workflow_observability_row(run_id)
    row.dependency_metrics = [
        None,
        {"span_id": "unknown", "kind": "other", "name": "ignored"},
        {"span_id": "unnamed", "kind": "tool"},
        {"span_id": "tool-1", "kind": "tool", "name": "http"},
    ]
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "get_or_none", AsyncMock(return_value=row)
    )

    detail = await observability_v2.run_detail("agent", run_id)

    assert [span["span_id"] for span in detail["spans"]] == [str(run_id), "tool-1"]
    assert detail["spans"][1]["parent_span_id"] == str(run_id)


@pytest.mark.asyncio
async def test_run_detail_returns_none_for_missing_summary(monkeypatch):
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "get_or_none", AsyncMock(return_value=None)
    )

    assert await observability_v2.run_detail("agent", uuid4()) is None


@pytest.mark.asyncio
async def test_dependencies_snapshot_filters_team_and_ignores_malformed_rows(
    monkeypatch,
):
    query = MagicMock()
    query.exclude.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.values.return_value = query
    monkeypatch.setattr(
        observability_v2,
        "window",
        lambda _period, _start=None, _end=None: (
            datetime(2026, 10, 8, tzinfo=UTC),
            datetime(2026, 10, 9, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(
        observability_v2,
        "run_bounded",
        AsyncMock(
            side_effect=[
                [],
                [
                    {"dependency_metrics": {"kind": "tool", "name": "wrong-shape"}},
                    {
                        "dependency_metrics": [
                            None,
                            {"kind": "unknown", "name": "ignored"},
                            {"kind": "tool", "name": None},
                        ]
                    },
                ],
            ]
        ),
    )

    result = await observability_v2._dependencies_snapshot("1h", "team-7")

    assert [item.kwargs for item in query.filter.call_args_list] == [
        {"team_id": "team-7"},
        {"team_id": "team-7"},
    ]
    assert result["models"] == result["tools"] == result["retrieval"] == []
    assert result["meta"]["state"] == "unavailable"


@pytest.mark.asyncio
async def test_queue_snapshot_reports_dynamic_queues_and_isolates_redis_failures(
    monkeypatch,
):
    from app.core import celery as celery_core
    from app.core import redis as redis_core

    inspection = SimpleNamespace(
        active=lambda: {"agent-worker": [1, 2]},
        reserved=lambda: {"api-worker": [1]},
        scheduled=lambda: {"scheduled-worker": [1]},
        active_queues=lambda: {
            "agent-worker": [
                {"name": "agent"},
                {"name": "sandbox.worker.42"},
                {"name": "unlisted"},
            ],
            "api-worker": [{"name": "default"}],
        },
    )
    monkeypatch.setattr(
        celery_core,
        "celery_app",
        SimpleNamespace(control=SimpleNamespace(inspect=lambda timeout: inspection)),
    )

    async def queue_length(name):
        if name == "default":
            raise RuntimeError("Redis unavailable for one queue")
        return 4 if name == "agent" else 0

    redis = SimpleNamespace(llen=queue_length)
    monkeypatch.setattr(redis_core, "get_redis", AsyncMock(return_value=redis))

    result = await observability_v2._queues_snapshot()

    workers = {worker["worker_id"]: worker for worker in result["workers"]}
    queues = {queue["name"]: queue for queue in result["queues"]}
    assert result["meta"]["state"] == "fresh"
    assert workers["agent-worker"]["active_tasks"] == 2
    assert workers["agent-worker"]["status"] == "healthy"
    assert workers["scheduled-worker"]["status"] == "unknown"
    assert queues["agent"]["pending"] == 4
    assert queues["agent"]["state"] == "healthy"
    assert queues["default"]["pending"] is None
    assert queues["default"]["state"] == "unavailable"
    assert "sandbox.worker.42" in queues
    assert "unlisted" not in queues


@pytest.mark.asyncio
async def test_queue_snapshot_returns_degraded_payload_when_inspection_fails(
    monkeypatch,
):
    from app.core import celery as celery_core
    from app.core import redis as redis_core

    def fail_inspection(_timeout):
        raise RuntimeError("worker inspection unavailable")

    monkeypatch.setattr(
        celery_core,
        "celery_app",
        SimpleNamespace(control=SimpleNamespace(inspect=fail_inspection)),
    )
    get_redis = AsyncMock()
    monkeypatch.setattr(redis_core, "get_redis", get_redis)

    result = await observability_v2._queues_snapshot()

    assert result["meta"]["state"] == "unavailable"
    assert result["workers"] == []
    assert result["queues"]
    assert all(queue["pending"] is None for queue in result["queues"])
    get_redis.assert_not_awaited()


@pytest.mark.asyncio
async def test_celery_dependency_probe_reports_responding_worker(monkeypatch):
    from app.core import celery as celery_core

    inspector = SimpleNamespace(stats=lambda: {"worker@node": {}})
    fake_app = SimpleNamespace(
        control=SimpleNamespace(inspect=lambda **kwargs: inspector)
    )
    monkeypatch.setattr(celery_core, "celery_app", fake_app)

    result = await observability_v2._celery_dependency_probe()

    assert result["status"] == "healthy"
    assert isinstance(result["latency_ms"], int)


@pytest.mark.asyncio
async def test_celery_dependency_probe_marks_missing_workers_unhealthy(monkeypatch):
    from app.core import celery as celery_core

    inspector = SimpleNamespace(stats=lambda: None)
    fake_app = SimpleNamespace(
        control=SimpleNamespace(inspect=lambda **kwargs: inspector)
    )
    monkeypatch.setattr(celery_core, "celery_app", fake_app)

    result = await observability_v2._celery_dependency_probe()

    assert result["status"] == "unhealthy"
    assert result["detail"] == "No Celery workers responded to inspection"


@pytest.mark.asyncio
async def test_qdrant_dependency_probe_reports_connection_and_unconfigured_backend(
    monkeypatch,
):
    from app.core.config import settings
    from app.services import memory

    client = SimpleNamespace(
        get_collections=AsyncMock(return_value={"collections": []})
    )
    monkeypatch.setattr(settings, "VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))

    healthy = await observability_v2._qdrant_dependency_probe()

    assert healthy["status"] == "healthy"
    assert isinstance(healthy["latency_ms"], int)
    client.get_collections.assert_awaited_once()

    monkeypatch.setattr(settings, "VECTOR_BACKEND", "other")
    unconfigured = await observability_v2._qdrant_dependency_probe()
    assert unconfigured["status"] == "unknown"
    assert unconfigured["detail"] == "Qdrant is not the configured vector backend"


@pytest.mark.asyncio
async def test_qdrant_dependency_probe_reports_failed_connection(monkeypatch):
    from app.core.config import settings
    from app.services import memory

    client = SimpleNamespace(
        get_collections=AsyncMock(side_effect=RuntimeError("offline"))
    )
    monkeypatch.setattr(settings, "VECTOR_BACKEND", "qdrant")
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))

    result = await observability_v2._qdrant_dependency_probe()

    assert result["status"] == "unhealthy"
    assert result["detail"] == "Qdrant health probe failed"


@pytest.mark.asyncio
async def test_infrastructure_snapshot_sanitizes_queries_and_preserves_dependency_status(
    monkeypatch,
):
    monkeypatch.setattr(
        observability_v2,
        "_celery_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 4, "detail": None}),
    )
    monkeypatch.setattr(
        observability_v2,
        "_qdrant_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 5, "detail": None}),
    )
    from app.services import admin_observability as legacy_health

    monkeypatch.setattr(
        legacy_health,
        "_database_health",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 3}),
    )
    monkeypatch.setattr(
        legacy_health,
        "_redis_health",
        AsyncMock(return_value={"status": "degraded", "latency_ms": 8}),
    )
    monkeypatch.setattr(
        legacy_health,
        "get_slow_queries",
        AsyncMock(
            return_value={
                "available": True,
                "items": [
                    {
                        "query": "SELECT * FROM users WHERE id = 123 AND email = 'private@example.test'",
                        "calls": 4,
                        "avg_ms": 15.5,
                        "max_ms": 30,
                        "total_ms": 62,
                    }
                ],
            }
        ),
    )

    result = await observability_v2._infrastructure_snapshot()

    dependencies = {item["name"]: item for item in result["dependencies"]}
    query = result["slow_queries"]["items"][0]
    assert result["meta"]["state"] == "fresh"
    assert dependencies["postgresql"]["status"] == "healthy"
    assert dependencies["redis"]["status"] == "degraded"
    assert dependencies["celery"]["status"] == "healthy"
    assert dependencies["qdrant"]["status"] == "healthy"
    assert isinstance(dependencies["postgresql"]["latency_ms"], int)
    assert isinstance(dependencies["redis"]["latency_ms"], int)
    assert query["query"] == "SELECT * FROM users WHERE id = ? AND email = '?'"
    assert "private@example.test" not in query["query"]
    assert query["calls"] == 4


@pytest.mark.asyncio
async def test_infrastructure_health_failure_does_not_hide_slow_query_availability(
    monkeypatch,
):
    monkeypatch.setattr(
        observability_v2,
        "_celery_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 4, "detail": None}),
    )
    monkeypatch.setattr(
        observability_v2,
        "_qdrant_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 5, "detail": None}),
    )
    from app.services import admin_observability as legacy_health

    monkeypatch.setattr(
        legacy_health,
        "_database_health",
        AsyncMock(side_effect=RuntimeError("database health unavailable")),
    )
    monkeypatch.setattr(
        legacy_health, "_redis_health", AsyncMock(return_value={"status": "healthy"})
    )
    slow_queries = AsyncMock(return_value={"available": True, "items": []})
    monkeypatch.setattr(legacy_health, "get_slow_queries", slow_queries)

    result = await observability_v2._infrastructure_snapshot()

    assert result["meta"]["state"] == "unavailable"
    assert result["instances"] == []
    dependencies = {item["name"]: item for item in result["dependencies"]}
    assert dependencies["postgresql"]["status"] == "unknown"
    assert dependencies["redis"]["status"] == "unknown"
    assert dependencies["celery"]["status"] == "healthy"
    assert dependencies["qdrant"]["status"] == "healthy"
    assert result["slow_queries"]["available"] is True
    slow_queries.assert_awaited_once_with(0, 1, 20)


@pytest.mark.asyncio
async def test_alert_rules_seed_disabled_defaults_and_serialize_rows(monkeypatch):
    now = datetime(2026, 10, 8, tzinfo=UTC)
    rule = SimpleNamespace(
        id="agent-failure-rate",
        name="Agent failure rate",
        threshold=0.2,
        enabled=False,
        evaluation_window_seconds=300,
        recovery_window_seconds=600,
        updated_at=now,
    )
    query = _AwaitableQuery([rule])
    create = AsyncMock()
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertRule, "get_or_create", create
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertRule, "all", MagicMock(return_value=query)
    )

    rules = await observability_v2.alert_rules()

    assert create.await_count == 2
    assert [item.kwargs for item in create.await_args_list] == [
        {
            "id": "agent-failure-rate",
            "defaults": {
                "name": "Agent failure rate",
                "threshold": 0.2,
                "enabled": False,
                "evaluation_window_seconds": 300,
                "recovery_window_seconds": 600,
            },
        },
        {
            "id": "workflow-failure-rate",
            "defaults": {
                "name": "Workflow failure rate",
                "threshold": 0.2,
                "enabled": False,
                "evaluation_window_seconds": 300,
                "recovery_window_seconds": 600,
            },
        },
    ]
    assert query.order_fields == ("id",)
    assert rules[0]["updated_at"] == now.isoformat()
    assert rules[0]["enabled"] is False


@pytest.mark.asyncio
async def test_update_alert_rule_only_persists_allowlisted_fields(monkeypatch):
    now = datetime(2026, 10, 8, tzinfo=UTC)
    row = SimpleNamespace(
        id="agent-failure-rate",
        name="Agent failure rate",
        threshold=0.2,
        enabled=False,
        evaluation_window_seconds=300,
        recovery_window_seconds=600,
        updated_at=now,
        save=AsyncMock(),
    )
    get_or_none = AsyncMock(side_effect=[None, row])
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertRule, "get_or_none", get_or_none
    )

    assert await observability_v2.update_rule("missing", {"threshold": 0.4}) is None
    updated = await observability_v2.update_rule(
        row.id, {"threshold": 0.4, "unknown": "ignored"}
    )

    row.save.assert_awaited_once_with(update_fields=["threshold", "updated_at"])
    assert updated["threshold"] == 0.4
    assert updated["name"] == "Agent failure rate"


@pytest.mark.asyncio
async def test_alert_page_applies_status_filter_and_returns_keyset_cursor(monkeypatch):
    opened = datetime(2026, 10, 8, 12, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            id=uuid4(),
            rule_id="agent-failure-rate",
            kind="failure_rate",
            severity="warning",
            title=f"Failure {index}",
            detail="Threshold exceeded",
            affected_count=3,
            status="active",
            opened_at=opened,
            resolved_at=None,
            acknowledged_at=None,
            silenced_until=None,
        )
        for index in range(2)
    ]
    query = _AwaitableQuery(rows)
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "all", MagicMock(return_value=query)
    )

    page = await observability_v2.list_alerts("active", None, 1)

    assert query.filter_calls == [((), {"status": "active"})]
    assert query.order_fields == ("-opened_at", "-id")
    assert query.limit_value == 2
    assert len(page["items"]) == 1
    assert _decode_cursor(page["next_cursor"]) == (opened, str(rows[0].id))
    assert page["meta"]["state"] == "partial"


@pytest.mark.asyncio
async def test_alert_mutations_only_return_rows_changed_from_active(monkeypatch):

    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    alert_id = uuid4()
    row = SimpleNamespace(
        id=alert_id,
        rule_id="agent-failure-rate",
        kind="failure_rate",
        severity="warning",
        title="Failure rate",
        detail="Threshold exceeded",
        affected_count=3,
        status="active",
        opened_at=now,
        resolved_at=None,
        acknowledged_at=now,
        silenced_until=now + timedelta(minutes=15),
    )
    query = MagicMock()
    query.update = AsyncMock(side_effect=[1, 1, 0])
    event_filter = MagicMock(return_value=query)
    get_or_none = AsyncMock(return_value=row)
    monkeypatch.setattr(observability_v2, "utcnow", lambda: now)
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "filter", event_filter
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "get_or_none", get_or_none
    )

    acknowledged = await observability_v2.acknowledge_alert(alert_id, "admin-id")
    silenced = await observability_v2.silence_alert(alert_id, 900)
    unchanged = await observability_v2.acknowledge_alert(alert_id, "admin-id")

    assert acknowledged["acknowledged_at"] == now.isoformat()
    assert silenced["silenced_until"] == (now + timedelta(minutes=15)).isoformat()
    assert unchanged is None
    assert query.update.await_args_list[0].kwargs == {
        "acknowledged_at": now,
        "acknowledged_by_id": "admin-id",
    }
    assert query.update.await_args_list[1].kwargs == {
        "silenced_until": now + timedelta(seconds=900)
    }
    assert query.update.await_args_list[2].kwargs == {
        "acknowledged_by_id": "admin-id",
        "acknowledged_at": now,
    }
    assert event_filter.call_args_list == [
        call(id=alert_id, status="active"),
        call(id=alert_id, status="active"),
        call(id=alert_id, status="active"),
    ]


@pytest.mark.asyncio
async def test_snapshot_expiry_and_failed_refresh_remove_stale_entries(monkeypatch):
    key = ("summary", "1h", "team-1")
    stale = {"state": "stale"}
    monkeypatch.setattr(
        observability_v2,
        "_SNAPSHOT_CACHE",
        {key: (observability_v2.monotonic() - 1, stale)},
    )
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_LOCK", asyncio.Lock())
    producer = AsyncMock(side_effect=RuntimeError("snapshot unavailable"))

    with pytest.raises(RuntimeError, match="snapshot unavailable"):
        await observability_v2._cached_snapshot(key, producer)

    assert key not in observability_v2._SNAPSHOT_CACHE
    assert key not in observability_v2._SNAPSHOT_INFLIGHT
    producer.assert_awaited_once()


def test_run_summary_reports_worker_bootstrap_delay():
    row = _workflow_observability_row(uuid4())
    row.message_started_at = row.started_at + timedelta(milliseconds=250)

    assert observability_v2._summary(row)["worker_bootstrap_ms"] == 250


@pytest.mark.asyncio
async def test_progress_without_expected_status_only_updates_active_runs(monkeypatch):
    run_id = uuid4()
    query = MagicMock()
    query.filter.return_value = query
    query.update = AsyncMock(return_value=1)
    run_filter = MagicMock(return_value=query)
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", run_filter)

    await observability_v2.update_run_progress(run_id, source="agent", status="running")

    run_filter.assert_called_once_with(id=run_id, source="agent")
    query.filter.assert_called_once_with(
        status__in=observability_v2.ACTIVE_RUN_STATUSES
    )
    query.update.assert_awaited_once_with(status="running")


@pytest.mark.asyncio
async def test_dependency_telemetry_database_failure_is_logged_and_dropped(monkeypatch):
    query = MagicMock()
    query.limit.return_value = query
    query.values.side_effect = RuntimeError("database unavailable")
    query.update = AsyncMock()
    logger = MagicMock()
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2, "logger", logger)

    await observability_v2.record_dependency_metrics(
        uuid4(), [{"kind": "tool", "name": "http"}]
    )

    query.update.assert_not_awaited()
    logger.debug.assert_called_once()
    assert (
        logger.debug.call_args.args[0] == "Dependency telemetry dropped for AgentRun %s"
    )


@pytest.mark.asyncio
async def test_summary_snapshot_applies_team_filter_before_aggregation(monkeypatch):
    start = datetime(2026, 10, 8, tzinfo=UTC)
    end = start + timedelta(hours=1)
    query = _AwaitableQuery([])
    run_bounded = AsyncMock(return_value=[])
    monkeypatch.setattr(
        observability_v2, "window", lambda _period, _start=None, _end=None: (start, end)
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2, "run_bounded", run_bounded)

    result = await observability_v2._summary_snapshot("1h", "team-1")

    assert query.filter_calls == [((), {"team_id": "team-1"})]
    assert query.limit_value == observability_v2.DB_QUERY_LIMIT + 1
    assert result["meta"]["state"] == "no_data"
    run_bounded.assert_awaited_once_with(query)


@pytest.mark.asyncio
async def test_public_snapshot_functions_cache_per_scope(monkeypatch):
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_LOCK", asyncio.Lock())
    summary_snapshot = AsyncMock(side_effect=lambda period, team_id: {"team": team_id})
    dependencies_snapshot = AsyncMock(
        side_effect=lambda period, team_id: {"team": team_id}
    )
    queues_snapshot = AsyncMock(return_value={"source": "queues"})
    infrastructure_snapshot = AsyncMock(return_value={"source": "infrastructure"})
    monkeypatch.setattr(observability_v2, "_summary_snapshot", summary_snapshot)
    monkeypatch.setattr(
        observability_v2, "_dependencies_snapshot", dependencies_snapshot
    )
    monkeypatch.setattr(observability_v2, "_queues_snapshot", queues_snapshot)
    monkeypatch.setattr(
        observability_v2, "_infrastructure_snapshot", infrastructure_snapshot
    )

    team_a = await observability_v2.summary("1h", "team-a")
    assert await observability_v2.summary("1h", "team-a") == team_a
    team_b = await observability_v2.summary("1h", "team-b")
    assert team_a == {"team": "team-a"}
    assert team_b == {"team": "team-b"}
    assert summary_snapshot.await_count == 2

    await observability_v2.dependencies("1h", "team-a")
    await observability_v2.dependencies("1h", "team-a")
    assert dependencies_snapshot.await_count == 1

    queue_payload = await observability_v2.queues()
    assert await observability_v2.queues() == queue_payload == {"source": "queues"}
    queues_snapshot.assert_awaited_once()

    infra_payload = await observability_v2.infrastructure()
    assert (
        await observability_v2.infrastructure()
        == infra_payload
        == {"source": "infrastructure"}
    )
    infrastructure_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_queue_snapshot_caps_discovered_sandbox_queues(monkeypatch):
    from app.core import celery as celery_core
    from app.core import redis as redis_core

    entries = [{"name": f"sandbox.worker.{index}"} for index in range(100)]
    inspection = SimpleNamespace(
        active=lambda: {},
        reserved=lambda: {},
        scheduled=lambda: {},
        active_queues=lambda: {
            "agent-worker": entries,
            "second-worker": [{"name": "sandbox.worker.after-limit"}],
        },
    )
    monkeypatch.setattr(
        celery_core,
        "celery_app",
        SimpleNamespace(control=SimpleNamespace(inspect=lambda timeout: inspection)),
    )
    redis = SimpleNamespace(llen=AsyncMock(return_value=0))
    monkeypatch.setattr(redis_core, "get_redis", AsyncMock(return_value=redis))

    result = await observability_v2._queues_snapshot()

    names = {queue["name"] for queue in result["queues"]}
    discovered = {name for name in names if name.startswith("sandbox.worker.")}
    assert len(names) == 64
    assert len(discovered) == 59
    assert "default" in names
    assert "sandbox.worker.58" in names
    assert "sandbox.worker.59" not in names
    assert "sandbox.worker.after-limit" not in names


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_component", ["slow_queries", "instance_registry"])
async def test_optional_infrastructure_failure_preserves_dependency_health(
    monkeypatch, failed_component
):
    monkeypatch.setattr(
        observability_v2,
        "_celery_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 4, "detail": None}),
    )
    monkeypatch.setattr(
        observability_v2,
        "_qdrant_dependency_probe",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 5, "detail": None}),
    )
    from app.services import admin_observability as legacy_health
    from app.services import observability_instances

    monkeypatch.setattr(
        legacy_health,
        "_database_health",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 2}),
    )
    monkeypatch.setattr(
        legacy_health,
        "_redis_health",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 1}),
    )
    monkeypatch.setattr(
        legacy_health,
        "get_slow_queries",
        AsyncMock(side_effect=RuntimeError("statistics unavailable"))
        if failed_component == "slow_queries"
        else AsyncMock(return_value={"available": True, "items": []}),
    )
    monkeypatch.setattr(
        observability_instances,
        "list_api_instances",
        AsyncMock(
            return_value={
                "available": failed_component != "instance_registry",
                "instances": [],
            }
        ),
    )

    result = await observability_v2._infrastructure_snapshot()

    assert result["meta"]["state"] == (
        "partial" if failed_component == "instance_registry" else "fresh"
    )
    assert result["dependencies"][0]["status"] == "healthy"
    assert result["instances"] == []
    assert result["slow_queries"] == {
        "available": failed_component != "slow_queries",
        "reset_at": None,
        "items": [],
    }


@pytest.mark.asyncio
async def test_alert_evaluation_skips_event_write_if_rule_disabled_under_lock(
    monkeypatch,
):
    _install_alert_evaluation(
        monkeypatch, ["failed"] * 10, active=None, locked_rule_enabled=False
    )
    event_filter = observability_v2.ObservabilityAlertEvent.filter

    await observability_v2.evaluate_alert_rules()

    event_filter.assert_not_called()
    observability_v2.ObservabilityAlertEvent.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_alert_page_accepts_keyset_cursor_for_unfiltered_results(monkeypatch):
    query = _AwaitableQuery([])
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "all", MagicMock(return_value=query)
    )
    cursor = _encode_cursor(datetime(2026, 10, 8, tzinfo=UTC), "alert-id")

    page = await observability_v2.list_alerts("all", cursor, 20)

    assert len(query.filter_calls) == 1
    assert len(query.filter_calls[0][0]) == 1
    assert query.filter_calls[0][1] == {}
    assert page["items"] == []
    assert page["next_cursor"] is None
    assert page["meta"]["state"] == "no_data"


@pytest.mark.asyncio
async def test_alert_page_rejects_invalid_keyset_cursor(monkeypatch):
    query = _AwaitableQuery([])
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "all", MagicMock(return_value=query)
    )

    with pytest.raises(ValueError, match="Invalid cursor"):
        await observability_v2.list_alerts("all", "invalid-cursor", 20)

    assert query.filter_calls == []
    assert query.limit_value is None


@pytest.mark.asyncio
async def test_retention_stops_when_no_expired_rows_remain(monkeypatch):
    run_query = MagicMock()
    run_query.order_by.return_value = run_query
    run_query.limit.return_value = run_query
    run_query.values_list = AsyncMock(return_value=[])
    alert_query = MagicMock()
    alert_query.order_by.return_value = alert_query
    alert_query.limit.return_value = alert_query
    alert_query.values_list = AsyncMock(return_value=[])
    run_filter = MagicMock(return_value=run_query)
    alert_filter = MagicMock(return_value=alert_query)
    monkeypatch.setattr(
        observability_v2, "utcnow", lambda: datetime(2026, 10, 8, tzinfo=UTC)
    )
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", run_filter)
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent, "filter", alert_filter
    )

    deleted = await observability_v2.retain()

    assert deleted == 0
    run_query.values_list.assert_awaited_once_with("id", flat=True)
    alert_query.values_list.assert_awaited_once_with("id", flat=True)
    run_filter.assert_called_once()
    alert_filter.assert_called_once()


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        ({"total": 120, "prompt": 80, "completion": 60}, 120),
        ({"total_tokens": 120}, 120),
        ({"total": 0, "prompt": 80, "completion": 60}, 140),
        ({"prompt": -10, "completion": 60}, 60),
        ({"total": "invalid"}, 0),
        (["invalid"], 0),
        ({}, 0),
    ],
)
def test_agent_terminal_summary_normalizes_final_message_usage(usage, expected):
    submitted = datetime(2026, 10, 8, 12, tzinfo=UTC)
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        status=observability_v2.AgentRunStatus.COMPLETED,
        submitted_at=submitted,
        started_at=submitted + timedelta(seconds=2),
        message_started_at=submitted + timedelta(seconds=3),
        finished_at=submitted + timedelta(seconds=5),
        first_token_ms=20,
        error_code=None,
    )
    summary = observability_v2.agent_terminal_summary(
        run,
        {},
        {"model_used": "provider/" + "m" * 250, "token_usage": usage},
    )
    assert summary["total_tokens"] == expected
    assert summary["model_name"] == ("provider/" + "m" * 250)[:200]
    assert summary["execution_duration_ms"] == 2000
    assert summary["total_duration_ms"] == 3000


def test_agent_terminal_summary_does_not_invent_model_or_usage_without_message():
    finished = datetime(2026, 10, 8, 12, tzinfo=UTC)
    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        status=observability_v2.AgentRunStatus.INTERRUPTED,
        submitted_at=finished - timedelta(seconds=10),
        started_at=None,
        message_started_at=None,
        finished_at=finished,
        first_token_ms=None,
        error_code="worker_loss",
    )
    summary = observability_v2.agent_terminal_summary(run, {}, {})
    assert summary["model_name"] is None
    assert summary["total_tokens"] == 0
    assert summary["execution_duration_ms"] is None
    assert summary["total_duration_ms"] is None


@pytest.mark.asyncio
async def test_dependency_models_resolve_uuid_metadata_without_merging_same_names(
    monkeypatch,
):
    gateway_id, direct_id, missing_id = uuid4(), uuid4(), uuid4()

    def sample(reference, status, duration, tokens):
        return {
            "model_name": reference,
            "status": status,
            "execution_duration_ms": duration,
            "first_token_ms": 10,
            "total_tokens": tokens,
        }

    query = MagicMock()
    query.exclude.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.values.return_value = query
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", MagicMock(return_value=query)
    )
    monkeypatch.setattr(observability_v2.Model, "filter", MagicMock(return_value=query))
    monkeypatch.setattr(
        observability_v2,
        "run_bounded",
        AsyncMock(
            side_effect=[
                [
                    sample(str(gateway_id), "completed", 100, 40),
                    sample(str(gateway_id), "failed", 300, 60),
                    sample(str(direct_id), "completed", 50, 70),
                    sample(str(missing_id), "completed", 80, 10),
                    sample("legacy-model", "completed", 20, 5),
                ],
                [],
                [
                    {
                        "id": gateway_id,
                        "name": "Shared model",
                        "provider": "openai",
                        "provider_display_name": "Gateway",
                    },
                    {
                        "id": direct_id,
                        "name": "Shared model",
                        "provider": "openai",
                        "provider_display_name": None,
                    },
                ],
            ]
        ),
    )

    result = await observability_v2._dependencies_snapshot("7d", None)
    models = {row["id"]: row for row in result["models"]}
    assert set(models) == {
        str(gateway_id),
        str(direct_id),
        str(missing_id),
        "legacy-model",
    }
    gateway, direct = models[str(gateway_id)], models[str(direct_id)]
    assert gateway["name"] == direct["name"] == "Shared model"
    assert gateway["provider_display_name"] == "Gateway"
    assert direct["provider_display_name"] == "OpenAI"
    assert gateway["requests"] == 2 and gateway["tokens"] == 100
    assert gateway["success_rate"] == 0.5 and gateway["p50_ms"] == 200
    assert direct["requests"] == 1 and direct["tokens"] == 70
    assert direct["success_rate"] == 1 and direct["p95_ms"] == 50
    missing = models[str(missing_id)]
    assert missing["name"] == "" and missing["provider_display_name"] is None
    assert missing["tokens"] == 10
    legacy = models["legacy-model"]
    assert legacy["name"] == "legacy-model" and legacy["provider"] is None
    assert legacy["tokens"] == 5


@pytest.mark.asyncio
async def test_queue_snapshot_collects_overlapping_replies_without_mixing_worker_counts(
    monkeypatch,
):
    from app.core import celery as celery_core
    from app.core import redis as redis_core

    rendezvous = Barrier(4, timeout=1.5)
    responses = {
        "active": {"worker": [1, 2, 3]},
        "reserved": {"worker": [1, 2]},
        "scheduled": {"worker": [1]},
        "active_queues": {
            "worker": [{"name": "agent"}, {"name": "sandbox.worker.parallel"}]
        },
    }

    class Inspector:
        def __init__(self):
            self.current_command = None

        def __getattr__(self, command):
            def collect():
                self.current_command = command
                rendezvous.wait()
                return responses[self.current_command]

            return collect

    monkeypatch.setattr(
        celery_core,
        "celery_app",
        SimpleNamespace(control=SimpleNamespace(inspect=lambda timeout: Inspector())),
    )
    monkeypatch.setattr(
        redis_core,
        "get_redis",
        AsyncMock(return_value=SimpleNamespace(llen=AsyncMock(return_value=0))),
    )

    result = await observability_v2._queues_snapshot()

    assert result["meta"]["state"] == "fresh"
    worker = result["workers"][0]
    assert worker["active_tasks"] == 3
    assert worker["reserved_tasks"] == 2
    assert worker["scheduled_tasks"] == 1
    consumers = {row["name"]: row["consumers"] for row in result["queues"]}
    assert consumers["agent"] == consumers["sandbox.worker.parallel"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["summary", "dependencies", "list_runs"])
async def test_custom_windows_filter_boundaries_and_cache_by_utc(
    monkeypatch, operation
):
    start = datetime(2026, 10, 8, 12, tzinfo=UTC)
    end = start + timedelta(hours=1)
    timestamps = [
        start - timedelta(microseconds=1),
        start,
        end,
        end + timedelta(microseconds=1),
    ]
    rows = [
        SimpleNamespace(
            id=uuid4(),
            source="agent",
            resource_id=None,
            resource_name=None,
            team_id=None,
            team_name=None,
            status="completed",
            submitted_at=stamp,
            started_at=None,
            message_started_at=None,
            finished_at=None,
            queue_duration_ms=None,
            execution_duration_ms=10,
            total_duration_ms=10,
            first_token_ms=2,
            total_tokens=5,
            error_category=None,
            error_code=None,
            trace_available=False,
            trace_complete=False,
            model_name="provider/model",
            dependency_metrics=[
                {
                    "kind": "tool",
                    "name": "http",
                    "status": "completed",
                    "duration_ms": 1,
                }
            ],
        )
        for stamp in timestamps
    ]

    class Query(_AwaitableQuery):
        def exclude(self, **kwargs):
            return self

        def values(self, *fields):
            self.rows = [
                {field: getattr(row, field) for field in fields} for row in self.rows
            ]
            return self

    calls = []

    def filtered(**kwargs):
        calls.append(kwargs)
        selected = [
            row
            for row in rows
            if kwargs["submitted_at__gte"]
            <= row.submitted_at
            <= kwargs["submitted_at__lte"]
        ]
        if "source" in kwargs:
            selected = [row for row in selected if row.source == kwargs["source"]]
        return Query(sorted(selected, key=lambda row: row.submitted_at, reverse=True))

    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", filtered)
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})

    async def invoke(left, right):
        kwargs = {
            "period": "custom",
            "team_id": None,
            "start_time": left,
            "end_time": right,
        }
        if operation == "list_runs":
            kwargs.update(
                source="all",
                status=None,
                error_category=None,
                run_id=None,
                cursor=None,
                limit=25,
            )
        return await getattr(observability_v2, operation)(**kwargs)

    result = await invoke(start, end)
    assert result["meta"]["period"] == "custom"
    assert result["meta"]["window_start"] == start.isoformat()
    assert result["meta"]["window_end"] == end.isoformat()
    assert result["meta"]["sample_count"] == 2
    if operation == "summary":
        assert result["agents"]["submitted"] == 2
        assert result["agents"]["tokens"] == 10
        assert len(result["trend"]) == 2
    elif operation == "dependencies":
        assert result["models"][0]["requests"] == 2
        assert result["tools"][0]["requests"] == 2
    else:
        assert {item["submitted_at"] for item in result["items"]} == {
            start.isoformat(),
            end.isoformat(),
        }
    from datetime import timezone

    offset = timezone(timedelta(hours=2))
    count = len(calls)
    equivalent = await invoke(start.astimezone(offset), end.astimezone(offset))
    assert equivalent["meta"]["sample_count"] == 2
    if operation != "list_runs":
        assert len(calls) == count
        assert len(observability_v2._SNAPSHOT_CACHE) == 1
    other = await invoke(end + timedelta(microseconds=1), end + timedelta(hours=1))
    assert other["meta"]["sample_count"] == 1
    if operation != "list_runs":
        assert len(observability_v2._SNAPSHOT_CACHE) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "span,expected",
    [(timedelta(hours=1), 2), (timedelta(days=1), 1), (timedelta(days=2), 1)],
)
async def test_custom_trend_bucket_size_uses_actual_span(monkeypatch, span, expected):
    start = datetime(2026, 10, 8, 12, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            submitted_at=start + timedelta(minutes=minute),
            source="agent",
            status="completed",
            total_duration_ms=10,
            first_token_ms=1,
            total_tokens=2,
        )
        for minute in (3, 4)
    ]
    monkeypatch.setattr(
        observability_v2.ObservabilityRun,
        "filter",
        lambda **kwargs: _AwaitableQuery(rows),
    )
    result = await observability_v2._summary_snapshot(
        "custom", None, start, start + span
    )
    assert len(result["trend"]) == expected
    assert sum(bucket["submitted"] for bucket in result["trend"]) == 2


def test_window_rejects_unknown_preset_period():
    with pytest.raises(ValueError, match="Invalid period"):
        observability_v2.window("2h")


@pytest.mark.asyncio
async def test_cancelled_snapshot_waiter_leaves_shared_producer_available(monkeypatch):
    key = ("cancelled-waiter",)
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def producer():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"ready": True}

    waiter = asyncio.create_task(observability_v2._cached_snapshot(key, producer))
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    shared = observability_v2._SNAPSHOT_INFLIGHT[key]
    assert not shared.done()
    release.set()
    result = await observability_v2._cached_snapshot(key, producer)

    assert result == {"ready": True}
    assert calls == 1


@pytest.mark.asyncio
async def test_failed_snapshot_does_not_remove_replacement_inflight_task(monkeypatch):
    key = ("replaced-producer",)
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_CACHE", {})
    monkeypatch.setattr(observability_v2, "_SNAPSHOT_INFLIGHT", {})
    replacement = None

    async def pending_replacement():
        await asyncio.Event().wait()

    async def fail_after_replacement():
        nonlocal replacement
        replacement = asyncio.create_task(pending_replacement())
        observability_v2._SNAPSHOT_INFLIGHT[key] = replacement
        raise RuntimeError("snapshot failed")

    with pytest.raises(RuntimeError, match="snapshot failed"):
        await observability_v2._cached_snapshot(key, fail_after_replacement)

    assert observability_v2._SNAPSHOT_INFLIGHT[key] is replacement
    replacement.cancel()
    with pytest.raises(asyncio.CancelledError):
        await replacement


class _ReconciliationQuery:
    def __init__(self, rows):
        self.rows = rows

    def using_db(self, *_args):
        return self

    def only(self, *_args):
        return self

    def values(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


@pytest.mark.asyncio
async def test_terminal_reconciliation_skips_empty_candidate_batch():
    connection = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))

    repaired = await observability_v2.reconcile_agent_terminal_summaries(connection)

    assert repaired == 0
    connection.execute_query.assert_awaited_once()


@pytest.mark.parametrize("saved", [True, False])
@pytest.mark.asyncio
async def test_terminal_reconciliation_counts_or_rejects_unsaved_summaries(
    monkeypatch, saved
):
    run_id, agent_id = uuid4(), uuid4()
    submitted_at = datetime.now(UTC) - timedelta(minutes=5)
    run = SimpleNamespace(
        id=run_id,
        agent_id=agent_id,
        canonical_message_id=None,
        status=SimpleNamespace(value="completed"),
        submitted_at=submitted_at,
        started_at=submitted_at,
        message_started_at=None,
        finished_at=submitted_at + timedelta(seconds=2),
        first_token_ms=None,
        error_code=None,
    )
    monkeypatch.setattr(
        observability_v2.AgentRun,
        "filter",
        lambda **_kwargs: _ReconciliationQuery([run]),
    )
    monkeypatch.setattr(
        observability_v2.Agent,
        "filter",
        lambda **_kwargs: _ReconciliationQuery(
            [{"id": agent_id, "name": "Agent", "team_id": None, "team__name": None}]
        ),
    )
    record = AsyncMock(return_value=saved)
    monkeypatch.setattr(observability_v2, "record_run", record)
    connection = SimpleNamespace(
        execute_query=AsyncMock(return_value=(1, [{"id": run_id}]))
    )

    if saved:
        assert (
            await observability_v2.reconcile_agent_terminal_summaries(connection) == 1
        )
        assert record.await_args.kwargs["resource_name"] == "Agent"
    else:
        with pytest.raises(RuntimeError, match="reconciliation failed"):
            await observability_v2.reconcile_agent_terminal_summaries(connection)


@pytest.mark.asyncio
async def test_progress_without_status_does_not_add_an_active_status_filter(
    monkeypatch,
):
    query = SimpleNamespace(update=AsyncMock(return_value=1), filter=Mock())
    filter_run = Mock(return_value=query)
    monkeypatch.setattr(observability_v2.ObservabilityRun, "filter", filter_run)
    started_at = datetime.now(UTC)
    run_id = uuid4()

    await observability_v2.update_run_progress(
        run_id, source="agent", started_at=started_at
    )

    filter_run.assert_called_once_with(id=run_id, source="agent")
    query.filter.assert_not_called()
    query.update.assert_awaited_once_with(started_at=started_at)


def _install_queue_snapshot_dependencies(monkeypatch, active_queues):
    from app.core import celery as celery_core
    from app.core import redis as redis_core

    class Inspector:
        def active(self):
            return {}

        def reserved(self):
            return {}

        def scheduled(self):
            return {}

        def active_queues(self):
            return active_queues

    monkeypatch.setattr(
        celery_core,
        "celery_app",
        SimpleNamespace(control=SimpleNamespace(inspect=lambda **_kwargs: Inspector())),
    )
    redis = SimpleNamespace(llen=AsyncMock(return_value=0))
    monkeypatch.setattr(redis_core, "get_redis", AsyncMock(return_value=redis))


@pytest.mark.asyncio
async def test_queue_snapshot_handles_absent_active_queues(monkeypatch):
    _install_queue_snapshot_dependencies(monkeypatch, {})

    result = await observability_v2._queues_snapshot()

    assert result["meta"]["state"] == "partial"
    assert result["workers"] == []
    assert all(row["pending"] == 0 for row in result["queues"])


@pytest.mark.asyncio
async def test_retention_continues_after_full_batch_then_stops_on_empty(monkeypatch):
    class Query:
        def __init__(self, batches, deletions):
            self.batches = iter(batches)
            self.deletions = iter(deletions)

        def filter(self, **_kwargs):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        async def values_list(self, *_args, **_kwargs):
            return next(self.batches)

        async def delete(self):
            return next(self.deletions)

    run_query = Query([[]], [])
    alert_query = Query([[str(index) for index in range(500)], []], [500])
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", lambda **_kwargs: run_query
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent,
        "filter",
        lambda **_kwargs: alert_query,
    )

    deleted = await observability_v2.retain()

    assert deleted == 500


@pytest.mark.asyncio
async def test_retention_stops_after_batch_limit_when_all_batches_are_full(
    monkeypatch,
):
    batch_size = observability_v2.RETENTION_BATCH_SIZE

    class Query:
        def __init__(self):
            self.batch_reads = 0
            self.deleted_batches = 0

        def filter(self, **_kwargs):
            return self

        def order_by(self, *_args):
            return self

        def limit(self, *_args):
            return self

        async def values_list(self, *_args, **_kwargs):
            self.batch_reads += 1
            return list(range(batch_size)) if self.batch_reads <= 2 else []

        async def delete(self):
            self.deleted_batches += 1
            return batch_size

    run_query, alert_query = Query(), Query()
    monkeypatch.setattr(observability_v2, "RETENTION_BATCHES_PER_CYCLE", 2)
    monkeypatch.setattr(
        observability_v2.ObservabilityRun, "filter", lambda **_kwargs: run_query
    )
    monkeypatch.setattr(
        observability_v2.ObservabilityAlertEvent,
        "filter",
        lambda **_kwargs: alert_query,
    )

    assert await observability_v2.retain() == 4 * batch_size
    assert (run_query.batch_reads, run_query.deleted_batches) == (2, 2)
    assert (alert_query.batch_reads, alert_query.deleted_batches) == (2, 2)
