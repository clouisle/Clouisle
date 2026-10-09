import json
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.admin.endpoints import dashboard


FIXED_NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def utc_server_days(monkeypatch):
    monkeypatch.setattr(dashboard, "to_local", lambda value: value.astimezone(UTC))


class Query:
    def __init__(self, result=None, *, count=0, calls=None):
        self.result = result
        self.count_result = count
        self.calls = calls if calls is not None else []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def prefetch_related(self, *args):
        return self._chain("prefetch_related", *args)

    def filter(self, **kwargs):
        return self._chain("filter", **kwargs)

    def annotate(self, **kwargs):
        return self._chain("annotate", **kwargs)

    def group_by(self, *args):
        return self._chain("group_by", *args)

    def order_by(self, *args):
        return self._chain("order_by", *args)

    def limit(self, value):
        return self._chain("limit", value)

    async def count(self):
        self.calls.append(("count", (), {}))
        return self.count_result

    async def values(self, *args):
        self.calls.append(("values", args, {}))
        return self.result

    async def values_list(self, *args, **kwargs):
        self.calls.append(("values_list", args, kwargs))
        return self.result

    async def all(self):
        self.calls.append(("all", (), {}))
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def model(monkeypatch, name, *, all_results=(), filter_results=()):
    calls = []
    all_iter = iter(all_results)
    filter_iter = iter(filter_results)
    fake = SimpleNamespace(
        all=lambda: Query(**next(all_iter), calls=calls),
        filter=lambda **kwargs: Query(**next(filter_iter), calls=calls)._chain(
            "model_filter", **kwargs
        ),
    )
    monkeypatch.setattr(dashboard, name, fake)
    return calls


@pytest.mark.anyio
async def test_dashboard_stats_summarizes_activity_and_empty_tokens(monkeypatch):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    for name, count in (
        ("User", 11),
        ("Team", 4),
        ("Agent", 5),
        ("Workflow", 6),
        ("KnowledgeBase", 7),
        ("Message", 13),
    ):
        filter_results = ({"count": 3},) if name == "User" else ()
        model(
            monkeypatch,
            name,
            all_results=({"count": count},),
            filter_results=filter_results,
        )

    conversation_calls = model(
        monkeypatch,
        "Conversation",
        all_results=({"count": 12},),
        filter_results=(
            {"result": [uuid4(), uuid4(), None]},
            {"result": [uuid4(), uuid4(), uuid4()]},
            {"result": [uuid4(), uuid4(), uuid4(), uuid4()]},
            {"count": 8},
        ),
    )
    team_calls = model(
        monkeypatch,
        "Team",
        all_results=({"count": 4},),
        filter_results=({"result": []},),
    )

    response = await dashboard.get_dashboard_stats(current_user=SimpleNamespace())

    assert response["code"] == 0
    assert response["data"] == {
        "overview": {
            "total_users": 11,
            "total_teams": 4,
            "total_agents": 5,
            "total_workflows": 6,
            "total_knowledge_bases": 7,
            "total_conversations": 12,
            "total_messages": 13,
            "total_tokens": 0,
        },
        "active_users": {"dau": 3, "wau": 3, "mau": 4},
        "growth": {"new_users_30d": 3, "new_conversations_30d": 8},
    }
    today_start = FIXED_NOW.replace(hour=0)
    boundaries = [
        kwargs["created_at__gte"]
        for name, _, kwargs in conversation_calls
        if name == "model_filter"
    ]
    assert boundaries == [
        today_start,
        FIXED_NOW - timedelta(days=7),
        FIXED_NOW - timedelta(days=30),
        FIXED_NOW - timedelta(days=30),
    ]
    assert ("model_filter", (), {"is_deleted": False}) in team_calls


@pytest.mark.anyio
async def test_dashboard_trends_observes_day_boundaries_and_serializes(monkeypatch):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    first_day = FIXED_NOW.date() - timedelta(days=6)
    start = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
    next_day = start + timedelta(days=1)
    user_id = uuid4()

    user_calls = model(
        monkeypatch,
        "User",
        filter_results=({"result": [{"created_at": start}, {"created_at": next_day}]},),
    )
    model(
        monkeypatch,
        "Conversation",
        filter_results=(
            {
                "result": [
                    {"created_at": start, "user_id": user_id},
                    {"created_at": start + timedelta(hours=1), "user_id": user_id},
                    {"created_at": next_day, "user_id": None},
                ]
            },
        ),
    )
    model(
        monkeypatch,
        "Message",
        filter_results=(
            {
                "result": [
                    {
                        "created_at": start,
                        "token_usage": {"prompt": 2, "completion": 3},
                    },
                    {"created_at": next_day, "token_usage": None},
                ]
            },
        ),
    )

    response = await dashboard.get_dashboard_trends("7d", SimpleNamespace())

    assert response["data"]["period"] == "7d"
    assert len(response["data"]["data"]) == 7
    assert response["data"]["data"][:2] == [
        {
            "date": first_day.strftime("%m/%d"),
            "new_users": 1,
            "active_users": 1,
            "new_conversations": 2,
            "messages": 1,
            "tokens": 5,
        },
        {
            "date": (first_day + timedelta(days=1)).strftime("%m/%d"),
            "new_users": 1,
            "active_users": 0,
            "new_conversations": 1,
            "messages": 1,
            "tokens": 0,
        },
    ]
    assert (
        "model_filter",
        (),
        {"created_at__gte": start, "created_at__lte": FIXED_NOW},
    ) in user_calls


@pytest.mark.anyio
async def test_top_agents_defaults_invalid_metric_and_keeps_all_system_scope(
    monkeypatch,
):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    team = SimpleNamespace(name="Core")
    agents = [
        SimpleNamespace(
            id=uuid4(), name="A", icon="bot", conversation_count=9, team=team
        ),
        SimpleNamespace(
            id=uuid4(), name="B", icon=None, conversation_count=0, team=None
        ),
    ]
    calls = model(monkeypatch, "Agent", all_results=({"result": agents},))
    monkeypatch.setattr(dashboard, "t", lambda key: f"translated:{key}")

    response = await dashboard.get_top_agents(
        limit=2,
        metric="invalid",
        time_range="all",
        current_user=SimpleNamespace(team_id=uuid4()),
    )

    assert response["data"] == [
        {
            "agent_id": str(agents[0].id),
            "name": "A",
            "icon": "bot",
            "value": 9,
            "team_name": "Core",
        },
        {
            "agent_id": str(agents[1].id),
            "name": "B",
            "icon": None,
            "value": 0,
            "team_name": "translated:unknown",
        },
    ]
    assert calls == [
        ("prefetch_related", ("team",), {}),
        ("order_by", ("-conversation_count",), {}),
        ("limit", (2,), {}),
    ]


@pytest.mark.anyio
async def test_team_usage_and_model_distribution_cover_empty_and_all_scope(monkeypatch):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    team = SimpleNamespace(
        id=uuid4(),
        name="Core",
        total_tokens=100,
        total_conversations=8,
        total_messages=20,
    )
    team_calls = model(monkeypatch, "Team", filter_results=({"result": [team]},))
    response = await dashboard.get_team_token_usage(1, "all", SimpleNamespace())
    assert response["data"] == [
        {
            "team_id": str(team.id),
            "name": "Core",
            "total_tokens": 100,
            "conversations": 8,
            "messages": 20,
        }
    ]
    assert team_calls == [
        ("model_filter", (), {"is_deleted": False}),
        ("order_by", ("-total_tokens",), {}),
        ("limit", (1,), {}),
    ]

    message_calls = model(
        monkeypatch,
        "Message",
        filter_results=(
            {
                "result": [
                    {"model_used": "large", "count": 3},
                    {"model_used": "small", "count": 1},
                ]
            },
        ),
    )
    tracked_models = [
        SimpleNamespace(
            model=SimpleNamespace(model_id="large"),
            monthly_requests_used=2,
        ),
        SimpleNamespace(
            model=SimpleNamespace(model_id="embedding"),
            monthly_requests_used=4,
        ),
    ]
    merged_counter_calls = model(
        monkeypatch,
        "TeamModel",
        filter_results=({"result": tracked_models},),
    )
    distribution = await dashboard.get_models_distribution("all", SimpleNamespace())
    assert distribution["data"] == [
        {"model": "large", "count": 3, "percentage": 75.0},
        {"model": "small", "count": 1, "percentage": 25.0},
    ]
    assert merged_counter_calls == []
    assert message_calls[0] == ("model_filter", (), {"model_used__isnull": False})

    model(monkeypatch, "Message", filter_results=({"result": []},))
    fallback_models = [
        SimpleNamespace(
            model=SimpleNamespace(model_id="embedding-model"),
            monthly_requests_used=4,
        ),
        SimpleNamespace(
            model=SimpleNamespace(model_id="embedding-model"),
            monthly_requests_used=1,
        ),
        SimpleNamespace(
            model=SimpleNamespace(model_id="chat-model"),
            monthly_requests_used=5,
        ),
    ]
    team_model_calls = model(
        monkeypatch,
        "TeamModel",
        filter_results=({"result": fallback_models},),
    )
    fallback_distribution = await dashboard.get_models_distribution(
        "30d", SimpleNamespace()
    )
    assert fallback_distribution["data"] == [
        {"model": "embedding-model", "count": 5, "percentage": 50.0},
        {"model": "chat-model", "count": 5, "percentage": 50.0},
    ]
    assert team_model_calls == [
        (
            "model_filter",
            (),
            {
                "monthly_requests_used__gt": 0,
                "monthly_reset_at__gte": FIXED_NOW.replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0
                ),
            },
        ),
        ("prefetch_related", ("model",), {}),
    ]


@pytest.mark.anyio
async def test_workflow_summary_aggregates_and_handles_missing_workflow(monkeypatch):
    workflow_id = uuid4()
    missing_id = uuid4()
    calls = []
    runs = Query(calls=calls)
    counts = iter([4, 3])
    runs.count = AsyncMock(side_effect=lambda: next(counts))
    values = iter(
        [
            [{"avg_dur": 12.9}],
            [{"trigger_type": "api", "count": 3}, {"trigger_type": None, "count": 1}],
            [{"status": "success", "count": 3}, {"status": "failed", "count": 1}],
            [
                {"workflow_id": workflow_id, "run_count": 4},
                {"workflow_id": missing_id, "run_count": 0},
            ],
            [{"workflow_id": workflow_id, "success_count": 3}],
        ]
    )
    runs.values = AsyncMock(side_effect=lambda *_args: next(values))
    monkeypatch.setattr(
        dashboard.WorkflowRun,
        "filter",
        lambda **kwargs: runs._chain("model_filter", **kwargs),
    )
    workflow = SimpleNamespace(id=workflow_id, name="Deploy")
    monkeypatch.setattr(
        dashboard.Workflow,
        "filter",
        lambda **kwargs: Query(result=[workflow], calls=calls)._chain(
            "model_filter", **kwargs
        ),
    )
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)

    response = await dashboard.get_workflow_summary("90d", SimpleNamespace())

    assert response["data"] == {
        "total_runs": 4,
        "success_rate": 75.0,
        "avg_duration_ms": 12,
        "trigger_type_distribution": [
            {"type": "api", "count": 3},
            {"type": None, "count": 1},
        ],
        "status_distribution": [
            {"status": "success", "count": 3},
            {"status": "failed", "count": 1},
        ],
        "top_workflows": [
            {
                "workflow_id": str(workflow_id),
                "name": "Deploy",
                "run_count": 4,
                "success_rate": 75.0,
            }
        ],
    }
    assert calls[0] == (
        "model_filter",
        (),
        {
            "created_at__gte": FIXED_NOW - timedelta(days=90),
            "created_at__lte": FIXED_NOW,
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "period", "days"),
    [
        (dashboard.get_dashboard_trends, "invalid", 30),
        (dashboard.get_models_distribution, "7d", 7),
        (dashboard.get_models_distribution, "90d", 90),
        (dashboard.get_models_distribution, "invalid", 30),
        (dashboard.get_workflow_summary, "7d", 7),
        (dashboard.get_workflow_summary, "invalid", 30),
    ],
)
async def test_dashboard_period_filters_use_expected_boundaries(
    monkeypatch, endpoint, period, days
):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    calls = []
    counter_calls = []

    if endpoint is dashboard.get_dashboard_trends:
        for name in ("User", "Conversation", "Message"):
            model(monkeypatch, name, filter_results=({"result": []},))
    elif endpoint is dashboard.get_models_distribution:
        calls = model(monkeypatch, "Message", filter_results=({"result": []},))
        counter_calls = model(
            monkeypatch, "TeamModel", filter_results=({"result": []},)
        )
    else:
        runs = Query(result=[], count=0, calls=calls)
        monkeypatch.setattr(
            dashboard.WorkflowRun,
            "filter",
            lambda **kwargs: runs._chain("model_filter", **kwargs),
        )

    response = await endpoint(period, SimpleNamespace())

    if endpoint is dashboard.get_dashboard_trends:
        assert len(response["data"]["data"]) == 30
    else:
        assert calls[0] == (
            "model_filter",
            (),
            {
                "created_at__gte": FIXED_NOW - timedelta(days=days),
                "created_at__lte": FIXED_NOW,
                **(
                    {"model_used__isnull": False}
                    if endpoint is dashboard.get_models_distribution
                    else {}
                ),
            },
        )

    if endpoint is dashboard.get_models_distribution:
        if period == "90d":
            assert counter_calls == []
        else:
            usage_field = (
                "daily_requests_used" if period == "7d" else "monthly_requests_used"
            )
            reset_field = "daily_reset_at" if period == "7d" else "monthly_reset_at"
            counter_start = (
                FIXED_NOW.replace(hour=0, minute=0, second=0, microsecond=0)
                if period == "7d"
                else FIXED_NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            )
            assert counter_calls == [
                (
                    "model_filter",
                    (),
                    {
                        f"{usage_field}__gt": 0,
                        f"{reset_field}__gte": counter_start,
                    },
                ),
                ("prefetch_related", ("model",), {}),
            ]


@pytest.mark.anyio
async def test_workflow_summary_empty_and_persistence_errors_propagate(monkeypatch):
    empty = Query(result=[], count=0)
    monkeypatch.setattr(dashboard.WorkflowRun, "all", lambda: empty)
    response = await dashboard.get_workflow_summary("all", SimpleNamespace())
    assert response["data"] == {
        "total_runs": 0,
        "success_rate": 0,
        "avg_duration_ms": 0,
        "trigger_type_distribution": [],
        "status_distribution": [],
        "top_workflows": [],
    }

    error = RuntimeError("database unavailable")
    monkeypatch.setattr(dashboard.User, "all", lambda: Query())
    monkeypatch.setattr(Query, "count", AsyncMock(side_effect=error))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await dashboard.get_dashboard_stats(SimpleNamespace())


RANGE_ENDPOINTS = [
    ("/stats/trends", "period"),
    ("/stats/agents/top", "time_range"),
    ("/stats/teams/token-usage", "time_range"),
    ("/stats/models/distribution", "time_range"),
    ("/stats/workflows/summary", "time_range"),
]


@pytest.mark.anyio
@pytest.mark.parametrize("path,range_key", RANGE_ENDPOINTS)
@pytest.mark.parametrize(
    "range_value,start,end",
    [
        ("custom", None, None),
        ("custom", "2026-07-21T00:00:00Z", None),
        ("custom", None, "2026-07-22T00:00:00Z"),
        ("custom", "2026-07-21T00:00:00", "2026-07-22T00:00:00Z"),
        ("custom", "2026-07-21T00:00:00Z", "2026-07-22T00:00:00"),
        ("custom", "invalid", "2026-07-22T00:00:00Z"),
        ("custom", "2026-07-21T00:00:00Z", "2026-07-21T08:00:00+08:00"),
        ("custom", "2026-07-22T00:00:00Z", "2026-07-21T00:00:00Z"),
        ("custom", "2026-07-21T00:00:00.0000001Z", "2026-07-22T00:00:00Z"),
        ("7d", "2026-07-21T00:00:00Z", "2026-07-22T00:00:00Z"),
        ("30d", "2026-07-21T00:00:00Z", None),
        ("90d", None, "2026-07-22T00:00:00Z"),
        ("all", "2026-07-21T00:00:00Z", "2026-07-22T00:00:00Z"),
    ],
)
async def test_dashboard_consumers_reject_invalid_ranges(
    path, range_key, range_value, start, end
):
    app = FastAPI()
    app.include_router(dashboard.router)
    for route in dashboard.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "current_user":
                app.dependency_overrides[dependency.call] = lambda: SimpleNamespace()
    params = {range_key: range_value}
    if start is not None:
        params["start_time"] = start
    if end is not None:
        params["end_time"] = end
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(path, params=params)
    assert response.status_code == 422


class EventQuery:
    """Row-backed query double: filters and aggregations operate on event data."""

    def __init__(self, rows, group=(), annotations=()):
        self.rows = rows
        self.group = group
        self.annotations = annotations

    def filter(self, **filters):
        def matches(row):
            for key, expected in filters.items():
                field, _, operator = key.partition("__")
                actual = row.get(field)
                if operator == "gte" and actual < expected:
                    return False
                if operator == "lte" and actual > expected:
                    return False
                if operator == "isnull" and (actual is None) != expected:
                    return False
                if operator == "in" and actual not in expected:
                    return False
                if not operator and actual != expected:
                    return False
            return True

        return EventQuery(
            [row for row in self.rows if matches(row)], self.group, self.annotations
        )

    def annotate(self, **annotations):
        return EventQuery(self.rows, self.group, tuple(annotations))

    def group_by(self, *fields):
        return EventQuery(self.rows, fields, self.annotations)

    def order_by(self, *_args):
        return self

    def limit(self, count):
        return EventQuery(self.rows[:count], self.group, self.annotations)

    async def count(self):
        return len(self.rows)

    async def values(self, *fields):
        if not self.annotations:
            return [{key: row[key] for key in fields} for row in self.rows]
        groups = {}
        for row in self.rows:
            groups.setdefault(tuple(row[key] for key in self.group), []).append(row)
        if not self.group:
            groups[()] = self.rows
        result = []
        for key, rows in groups.items():
            item = dict(zip(self.group, key, strict=True))
            for annotation in self.annotations:
                if annotation == "avg_dur":
                    item[annotation] = (
                        sum(row["total_duration_ms"] for row in rows) / len(rows)
                        if rows
                        else None
                    )
                else:
                    item[annotation] = len(rows)
            result.append({field: item[field] for field in fields})
        return result


@pytest.mark.anyio
async def test_custom_consumers_clip_events_and_preserve_inclusive_microseconds(
    monkeypatch,
):
    start = FIXED_NOW.replace(hour=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    timestamps = [
        start - timedelta(microseconds=1),
        start,
        end,
        end + timedelta(microseconds=1),
    ]
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    users = [{"created_at": value} for value in timestamps]
    conversations = [
        {"created_at": value, "user_id": "same-user"} for value in timestamps
    ]
    messages = [
        {
            "created_at": value,
            "token_usage": {"prompt": token, "completion": None},
            "model_used": "historic",
        }
        for value, token in zip(timestamps, [999, 10, 20, 999], strict=True)
    ]
    runs = [
        {
            "created_at": value,
            "status": status,
            "trigger_type": "api",
            "workflow_id": None,
            "total_duration_ms": duration,
        }
        for value, status, duration in zip(
            timestamps,
            ["failed", "success", "success", "failed"],
            [999, 10, 30, 999],
            strict=True,
        )
    ]
    for name, rows in (
        ("User", users),
        ("Conversation", conversations),
        ("Message", messages),
        ("WorkflowRun", runs),
    ):
        monkeypatch.setattr(
            dashboard,
            name,
            SimpleNamespace(
                filter=lambda rows=rows, **filters: EventQuery(rows).filter(**filters)
            ),
        )
    monkeypatch.setattr(
        dashboard,
        "TeamModel",
        SimpleNamespace(
            filter=lambda **_kwargs: pytest.fail(
                "Custom history cannot use present quota counters"
            )
        ),
    )
    # Offset input represents the exact same UTC instant as the first boundary.
    bounds = {"start_time": "2026-07-21T08:00:00+08:00", "end_time": end.isoformat()}
    app = FastAPI()
    app.include_router(dashboard.router)
    for route in dashboard.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "current_user":
                app.dependency_overrides[dependency.call] = lambda: SimpleNamespace()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        trends = await client.get(
            "/stats/trends", params={"period": "custom", **bounds}
        )
        models = await client.get(
            "/stats/models/distribution", params={"time_range": "custom", **bounds}
        )
        workflows = await client.get(
            "/stats/workflows/summary", params={"time_range": "custom", **bounds}
        )
    assert trends.status_code == models.status_code == workflows.status_code == 200
    assert trends.json()["data"]["data"] == [
        {
            "date": "07/21",
            "new_users": 2,
            "active_users": 1,
            "new_conversations": 2,
            "messages": 2,
            "tokens": 30,
        }
    ]
    assert models.json()["data"] == [
        {"model": "historic", "count": 2, "percentage": 100.0}
    ]
    summary = workflows.json()["data"]
    assert (
        summary["total_runs"],
        summary["success_rate"],
        summary["avg_duration_ms"],
    ) == (2, 100, 20)


@pytest.mark.anyio
async def test_bounded_rankings_execute_aggregate_sql_over_event_rows(monkeypatch):
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.create_function(
        "jsonb_typeof",
        1,
        lambda value: (
            "number"
            if value is not None and isinstance(json.loads(value), (int, float))
            else None
        ),
    )
    database.executescript(
        "CREATE TABLE agents (id TEXT, team_id TEXT); CREATE TABLE conversations (id TEXT, agent_id TEXT, created_at TEXT); CREATE TABLE messages (conversation_id TEXT, created_at TEXT, token_usage TEXT);"
    )
    start = FIXED_NOW.replace(hour=0)
    end = start + timedelta(days=1) - timedelta(microseconds=1)
    timestamps = [
        start - timedelta(microseconds=1),
        start,
        end,
        end + timedelta(microseconds=1),
    ]
    database.executemany(
        "INSERT INTO agents VALUES (?, ?)",
        [("active", "team-active"), ("stale", "team-stale")],
    )
    database.executemany(
        "INSERT INTO conversations VALUES (?, ?, ?)",
        [
            ("old", "active", timestamps[0].isoformat()),
            ("new", "active", start.isoformat()),
            ("stale", "stale", timestamps[0].isoformat()),
        ],
    )
    database.executemany(
        "INSERT INTO messages VALUES (?, ?, ?)",
        [
            (
                "old",
                value.isoformat(),
                json.dumps({"prompt": token, "completion": None}),
            )
            for value, token in zip(timestamps, [999, 10, 20, 999], strict=True)
        ],
    )

    class Connection:
        async def execute_query_dict(self, sql, params):
            # SQLite's JSON operators match PostgreSQL here; only cast syntax differs.
            for key in ("prompt", "completion"):
                sql = sql.replace(
                    f"(m.token_usage ->> '{key}')::bigint",
                    f"CAST((m.token_usage ->> '{key}') AS INTEGER)",
                )
            return [
                dict(row)
                for row in database.execute(
                    sql,
                    {
                        str(index): value.isoformat()
                        for index, value in enumerate(params, 1)
                    },
                )
            ]

    monkeypatch.setattr(
        dashboard.Tortoise, "get_connection", lambda _name: Connection()
    )
    agents = [
        SimpleNamespace(
            id=agent_id,
            name=agent_id,
            icon=None,
            team=SimpleNamespace(name=team_id),
            conversation_count=999,
            message_count=999,
            total_tokens=999,
        )
        for agent_id, team_id in [("stale", "team-stale"), ("active", "team-active")]
    ]
    teams = [
        SimpleNamespace(
            id=team_id,
            name=team_id,
            total_tokens=999,
            total_conversations=999,
            total_messages=999,
        )
        for team_id in ("team-stale", "team-active")
    ]
    monkeypatch.setattr(
        dashboard, "Agent", SimpleNamespace(all=lambda: Query(result=agents))
    )
    monkeypatch.setattr(
        dashboard, "Team", SimpleNamespace(filter=lambda **_kwargs: Query(result=teams))
    )
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    bounds = {"start_time": start.isoformat(), "end_time": end.isoformat()}
    app = FastAPI()
    app.include_router(dashboard.router)
    for route in dashboard.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.name == "current_user":
                app.dependency_overrides[dependency.call] = lambda: SimpleNamespace()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for metric, expected in (
                ("conversation_count", 1),
                ("message_count", 2),
                ("total_tokens", 30),
            ):
                response = await client.get(
                    "/stats/agents/top",
                    params={
                        "limit": 1,
                        "metric": metric,
                        "time_range": "custom",
                        **bounds,
                    },
                )
                assert response.status_code == 200
                assert response.json()["data"][0]["agent_id"] == "active"
                assert response.json()["data"][0]["value"] == expected
            response = await client.get(
                "/stats/teams/token-usage",
                params={"limit": 1, "time_range": "custom", **bounds},
            )
            assert response.status_code == 200
            assert response.json()["data"] == [
                {
                    "team_id": "team-active",
                    "name": "team-active",
                    "total_tokens": 30,
                    "conversations": 1,
                    "messages": 2,
                }
            ]
        # The same measured-row aggregation applies to the existing bounded presets.
        response = await dashboard.get_top_agents(
            limit=1,
            metric="total_tokens",
            time_range="7d",
            current_user=SimpleNamespace(),
        )
        assert response["data"][0]["value"] == 1009
    finally:
        database.close()


@pytest.mark.anyio
@pytest.mark.parametrize("period,expected_days", [("90d", 90), ("all", 121)])
async def test_trends_long_ranges_span_actual_history(
    monkeypatch, period, expected_days
):
    monkeypatch.setattr(dashboard, "now", lambda: FIXED_NOW)
    old = FIXED_NOW - timedelta(days=120)
    for name, rows in (
        ("User", [{"created_at": old}]),
        ("Conversation", []),
        ("Message", [{"created_at": FIXED_NOW, "token_usage": {"completion": 7}}]),
    ):
        monkeypatch.setattr(
            dashboard,
            name,
            SimpleNamespace(
                filter=lambda rows=rows, **filters: EventQuery(rows).filter(**filters)
            ),
        )
    response = await dashboard.get_dashboard_trends(period, SimpleNamespace())
    points = response["data"]["data"]
    assert len(points) == expected_days
    assert sum(point["new_users"] for point in points) == (1 if period == "all" else 0)
    assert sum(point["tokens"] for point in points) == 7


@pytest.mark.anyio
async def test_all_trends_without_events_invents_no_history(monkeypatch):
    for name in ("User", "Conversation", "Message"):
        monkeypatch.setattr(
            dashboard, name, SimpleNamespace(filter=lambda **_filters: EventQuery([]))
        )
    response = await dashboard.get_dashboard_trends("all", SimpleNamespace())
    assert response["data"]["data"] == []


@pytest.mark.anyio
async def test_custom_trends_clip_partial_days_with_server_timezone_labels(monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setattr(
        dashboard, "to_local", lambda value: value.astimezone(ZoneInfo("Asia/Shanghai"))
    )
    start = datetime(2026, 7, 21, 15, 59, 59, 999999, tzinfo=UTC)
    end = start + timedelta(microseconds=1)
    rows = [
        {"created_at": value, "token_usage": None}
        for value in (
            start - timedelta(microseconds=1),
            start,
            end,
            end + timedelta(microseconds=1),
        )
    ]
    for name, events in (("User", []), ("Conversation", []), ("Message", rows)):
        monkeypatch.setattr(
            dashboard,
            name,
            SimpleNamespace(
                filter=lambda events=events, **filters: EventQuery(events).filter(
                    **filters
                )
            ),
        )
    response = await dashboard.get_dashboard_trends(
        "custom", SimpleNamespace(), start.isoformat(), end.isoformat()
    )
    assert [
        (point["date"], point["messages"]) for point in response["data"]["data"]
    ] == [("07/21", 1), ("07/22", 1)]
