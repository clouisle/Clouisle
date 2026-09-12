"""Contracts for the database-side statistics aggregation helpers.

The SQL is primarily verified by executing it against a real PostgreSQL 17
instance; these tests pin what is checkable without a database and what a
plausible refactor could silently break:

- the granularity allowlist (the only identifier-position fragment in the
  module, and therefore the only injection surface),
- the token-key allowlist,
- NULL/empty-set coercion, which differs between SQL (``AVG`` -> NULL) and the
  previous Python implementation (``else 0``),
- two SQL-shape invariants that each caused a production 500 and that unit
  tests with a mocked connection cannot otherwise catch, because a mock
  accepts any string as valid SQL.
"""

from datetime import datetime
from uuid import uuid4

import pytest

from app.services import stats_sql


class _Conn:
    """Records the SQL and bound parameters of each call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[str, list]] = []

    async def execute_query_dict(self, sql, params=None):
        self.calls.append((sql, params))
        return self.results.pop(0) if self.results else []


@pytest.mark.parametrize("granularity", ["hour", "day"])
def test_granularity_allowlist_accepts_supported_units(granularity):
    assert stats_sql._granularity(granularity) == granularity


@pytest.mark.parametrize(
    "granularity",
    ["week", "month", "day; DROP TABLE messages", "'day'", "HOUR", ""],
)
def test_granularity_allowlist_rejects_everything_else(granularity):
    """The unit is interpolated into SQL, so it must never accept free text."""
    with pytest.raises(ValueError):
        stats_sql._granularity(granularity)


@pytest.mark.parametrize("key", ["total", "prompt; --", "", "PROMPT"])
def test_token_key_allowlist_rejects_unknown_keys(key):
    with pytest.raises(ValueError):
        stats_sql._token_sum(key)


@pytest.mark.anyio
async def test_message_overview_binds_values_and_defaults_empty_aggregates(
    monkeypatch,
):
    agent_id = uuid4()
    start = datetime(2026, 9, 1)
    # A row of all-NULL aggregates is what PostgreSQL returns for an empty
    # window; the previous Python code fell back to 0 for each field.
    conn = _Conn([{}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_message_overview(agent_id, start)

    sql, params = conn.calls[0]
    assert params == [str(agent_id), start]
    assert str(agent_id) not in sql  # value is bound, never interpolated
    assert result == {
        "user_messages": 0,
        "assistant_messages": 0,
        "tool_messages": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "tool_call_count": 0,
        "avg_duration": 0,
    }


@pytest.mark.anyio
async def test_message_overview_omits_window_when_period_is_all(monkeypatch):
    conn = _Conn([{}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    await stats_sql.agent_message_overview(uuid4(), None)

    sql, params = conn.calls[0]
    assert len(params) == 1
    assert "created_at >=" not in sql


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("helper", "column"),
    [
        ("agent_conversation_overview", "created_at >="),
        ("agent_tool_usage", "m.created_at >="),
        ("agent_run_health", "updated_at >="),
        ("agent_latency_percentiles", "m.created_at >="),
        ("agent_intervention_counts", "i.created_at >="),
    ],
)
async def test_windowed_helpers_bind_the_lower_bound(monkeypatch, helper, column):
    start = datetime(2026, 9, 1)
    conn = _Conn([])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    await getattr(stats_sql, helper)(uuid4(), start)

    sql, params = conn.calls[0]
    assert column in sql
    assert params[1] is start


@pytest.mark.anyio
@pytest.mark.parametrize(
    "helper",
    [
        "agent_conversation_overview",
        "agent_tool_usage",
        "agent_run_health",
        "agent_latency_percentiles",
        "agent_intervention_counts",
    ],
)
async def test_windowed_helpers_scan_unbounded_for_all_period(monkeypatch, helper):
    """``period=all`` must emit no lower bound at all, not a sentinel date."""
    conn = _Conn([])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    await getattr(stats_sql, helper)(uuid4(), None)

    sql, params = conn.calls[0]
    assert "created_at >=" not in sql
    assert "updated_at >=" not in sql
    assert len(params) == 1


@pytest.mark.anyio
async def test_trend_buckets_bind_timezone_and_merge_both_series(monkeypatch):
    bucket = datetime(2026, 9, 12)
    conn = _Conn(
        [{"bucket": bucket, "conversations": 2}],
        [
            {
                "bucket": bucket,
                "messages": 3,
                "tokens": 150,
                "avg_duration": 1200.0,
                "ttft_p50": 4649.0,
                "ttft_p95": 30431.6,
            }
        ],
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_trend_buckets(
        uuid4(), datetime(2026, 9, 5), "day", "Asia/Shanghai"
    )

    # The timezone decides local day boundaries; binding it (rather than
    # formatting it in) is what keeps the bucketing both correct and safe.
    assert conn.calls[0][1][2] == "Asia/Shanghai"
    assert result[bucket] == {
        "conversations": 2,
        "messages": 3,
        "tokens": 150,
        "avg_duration": 1200.0,
        "ttft_p50": 4649.0,
        "ttft_p95": 30431.6,
    }


@pytest.mark.anyio
async def test_trend_buckets_keep_unmeasured_latency_as_null(monkeypatch):
    """A bucket whose messages carry no first-token timing must stay NULL.

    Coercing it to 0 would draw a fake drop to zero on the latency chart
    instead of the gap that the data actually represents.
    """
    bucket = datetime(2026, 9, 12)
    conn = _Conn(
        [{"bucket": bucket, "conversations": 1}],
        [
            {
                "bucket": bucket,
                "messages": 2,
                "tokens": 0,
                "avg_duration": None,
                "ttft_p50": None,
                "ttft_p95": None,
            }
        ],
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_trend_buckets(
        uuid4(), datetime(2026, 9, 5), "day", "Asia/Shanghai"
    )

    assert result[bucket]["ttft_p50"] is None
    assert result[bucket]["ttft_p95"] is None


@pytest.mark.anyio
async def test_trend_buckets_keep_conversation_only_periods(monkeypatch):
    """A bucket with conversations but no assistant replies must survive."""
    bucket = datetime(2026, 9, 12)
    conn = _Conn([{"bucket": bucket, "conversations": 1}], [])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_trend_buckets(
        uuid4(), datetime(2026, 9, 5), "hour", "UTC"
    )

    assert result[bucket]["conversations"] == 1
    assert "messages" not in result[bucket]


@pytest.mark.anyio
async def test_workflow_overview_maps_null_aggregates_to_zero(monkeypatch):
    conn = _Conn([{"total_runs": 0, "avg_duration_ms": None, "last_run_at": None}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.workflow_run_overview(uuid4())

    assert result["total_runs"] == 0
    assert result["avg_duration_ms"] == 0
    assert result["last_run_at"] is None


@pytest.mark.anyio
async def test_global_run_stats_scope_to_given_ids_and_truncate_average(
    monkeypatch,
):
    first, second = uuid4(), uuid4()
    conn = _Conn(
        [{"status": "success", "count": 3}, {"status": "failed", "count": 1}],
        [{"workflow_id": first, "count": 3}, {"workflow_id": second, "count": 1}],
        [{"avg_duration_ms": 1366.6666666666667}],
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.workflow_global_run_stats([first, second])

    # Every query is scoped to exactly the authorised ids it was handed.
    for _sql, params in conn.calls:
        assert params[0] == [str(first), str(second)]
    assert result["runs_by_status"] == {"success": 3, "failed": 1}
    assert result["total_runs"] == 4
    assert result["top_workflows"] == [(first, 3), (second, 1)]
    # Matches the previous integer-truncating `//` division, not rounding.
    assert result["avg_duration_ms"] == 1366


# --- SQL-shape regressions (each of these shipped a production 500) ---------


@pytest.mark.parametrize("fragment", [stats_sql._TOOL_CALL_COUNT, stats_sql._TOKEN_SUM])
def test_jsonb_fragments_qualify_their_columns(fragment):
    """``conversations`` also has a ``token_usage`` column.

    Both fragments are used in queries joining ``messages`` to
    ``conversations``, so an unqualified column name raises
    "column reference is ambiguous" at runtime.
    """
    for column in ("token_usage", "tool_calls"):
        assert f" {column}" not in fragment, (
            f"{column} must be qualified as m.{column} to stay unambiguous"
        )
        assert f"({column}" not in fragment


@pytest.mark.parametrize("fragment", [stats_sql._TOOL_CALL_COUNT, stats_sql._TOKEN_SUM])
def test_jsonb_fragments_carry_their_own_role_predicate(fragment):
    """These fragments cannot be narrowed by a trailing ``FILTER`` clause.

    ``FILTER`` may only follow a bare aggregate, so
    ``COALESCE(SUM(...)) FILTER (WHERE ...)`` is a syntax error. The role
    predicate therefore has to live inside the ``CASE``.
    """
    assert "m.role = 'assistant'" in fragment


@pytest.mark.anyio
async def test_message_overview_never_appends_filter_to_wrapped_aggregates(
    monkeypatch,
):
    conn = _Conn([{}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    await stats_sql.agent_message_overview(uuid4(), None)

    sql = conn.calls[0][0]
    # COUNT/AVG may legitimately use FILTER; COALESCE(SUM(...)) may not.
    for chunk in sql.split("AS ")[:-1]:
        if "COALESCE" in chunk:
            assert "FILTER" not in chunk.split("COALESCE")[-1], (
                "FILTER cannot follow COALESCE(SUM(...)) — fold the predicate "
                "into the CASE instead"
            )


# --- Execution health -------------------------------------------------------


@pytest.mark.anyio
async def test_run_health_counts_only_terminal_states_in_the_rate(monkeypatch):
    conn = _Conn(
        [
            {"status": "completed", "count": 9},
            {"status": "failed", "count": 1},
            {"status": "stopped", "count": 2},
            # Worker loss is terminal: it must dilute the rate and be reported,
            # not passed off as an in-flight run.
            {"status": "interrupted", "count": 2},
            {"status": "running", "count": 4},
            {"status": "queued", "count": 3},
        ]
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_run_health(uuid4(), None)

    assert result["completed"] == 9
    assert result["failed"] == 1
    assert result["stopped"] == 2
    assert result["interrupted"] == 2
    assert result["in_flight"] == 7
    # In-flight runs must not dilute the rate; interrupted runs must.
    assert result["total"] == 14
    assert result["success_rate"] == pytest.approx(9 / 14)


@pytest.mark.anyio
async def test_run_health_reports_interrupted_runs_as_terminal_not_in_flight(
    monkeypatch,
):
    """A crashed run must not masquerade as still running.

    ``mark_expired_runs_interrupted`` is the only writer of this status, and
    the persistence layer stamps ``finished_at`` for it.
    """
    conn = _Conn(
        [
            {"status": "interrupted", "count": 3},
            {"status": "running", "count": 1},
        ]
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_run_health(uuid4(), None)

    assert result["interrupted"] == 3
    assert result["in_flight"] == 1
    assert result["total"] == 3
    assert result["success_rate"] == 0.0


@pytest.mark.anyio
async def test_run_health_without_terminal_runs_reports_zero_rate(monkeypatch):
    conn = _Conn([{"status": "running", "count": 2}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_run_health(uuid4(), None)

    assert result["total"] == 0
    assert result["success_rate"] == 0.0


@pytest.mark.anyio
async def test_run_health_surfaces_unknown_status_without_failing(monkeypatch):
    """An unmapped status must be visible, not folded in — and not a 500.

    A status written by another release is real data; raising here would turn a
    read-only statistics request into a server error, while counting it as a
    known outcome would misattribute it. It gets its own total instead.
    """
    conn = _Conn(
        [
            {"status": "completed", "count": 4},
            {"status": "teleported", "count": 3},
            {"status": "running", "count": 1},
        ]
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_run_health(uuid4(), None)

    assert result["unrecognised"] == 3
    # It must not inflate any known bucket...
    assert result["completed"] == 4
    assert result["in_flight"] == 1
    assert result["total"] == 4
    assert result["success_rate"] == pytest.approx(1.0)


# --- First-token latency ----------------------------------------------------


@pytest.mark.anyio
async def test_latency_percentiles_map_null_aggregates_to_zero(monkeypatch):
    conn = _Conn([{"p50": None, "p95": None, "avg_first_token": None, "samples": 0}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_latency_percentiles(uuid4(), None)

    assert result == {"p50": 0.0, "p95": 0.0, "avg": 0.0, "samples": 0}


@pytest.mark.anyio
async def test_latency_percentiles_preserve_measured_tail(monkeypatch):
    conn = _Conn(
        [{"p50": 4649.0, "p95": 30431.6, "avg_first_token": 8583.58, "samples": 67}]
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_latency_percentiles(uuid4(), None)

    # p95 far above p50 is the signal an average would hide.
    assert result["p95"] == pytest.approx(30431.6)
    assert result["p50"] == pytest.approx(4649.0)
    assert result["samples"] == 67


# --- User interventions -----------------------------------------------------


@pytest.mark.anyio
async def test_intervention_counts_keep_total_coherent_with_its_parts(monkeypatch):
    conn = _Conn(
        [
            {"kind": "steer", "count": 10},
            {"kind": "stop", "count": 7},
            {"kind": "follow_up", "count": 3},
        ]
    )
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    result = await stats_sql.agent_intervention_counts(uuid4(), None)

    assert result["steer"] == 10
    assert result["stop"] == 7
    assert result["follow_up"] == 3
    # total must equal the sum of the reported parts, or the UI cannot trust it.
    assert result["total"] == 20


@pytest.mark.anyio
async def test_intervention_counts_reject_unknown_kind(monkeypatch):
    conn = _Conn([{"kind": "shouted", "count": 1}])
    monkeypatch.setattr(stats_sql, "_connection", lambda: conn)

    with pytest.raises(ValueError, match="shouted"):
        await stats_sql.agent_intervention_counts(uuid4(), None)


def test_terminal_statuses_exclude_every_in_flight_state():
    """Guards the rate denominator if the enum gains a state."""
    # Must stay in lockstep with agent_run_store's notion of "finished":
    # _build_transition_updates stamps finished_at for exactly these four.
    assert stats_sql.TERMINAL_AGENT_RUN_STATUSES == {
        "completed",
        "failed",
        "stopped",
        "interrupted",
    }
    assert stats_sql.TERMINAL_AGENT_RUN_STATUSES.isdisjoint(
        stats_sql.IN_FLIGHT_AGENT_RUN_STATUSES
    )
    assert (
        stats_sql.TERMINAL_AGENT_RUN_STATUSES | stats_sql.IN_FLIGHT_AGENT_RUN_STATUSES
    ) == stats_sql.AGENT_RUN_STATUS_VALUES
