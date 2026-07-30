from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import dashboard


FIXED_NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


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
        {"created_at__gte": FIXED_NOW - timedelta(days=7)},
    ) in user_calls


@pytest.mark.anyio
async def test_top_agents_defaults_invalid_filters_and_keeps_system_scope(monkeypatch):
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
        time_range="invalid",
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
    response = await dashboard.get_team_token_usage(1, "7d", SimpleNamespace())
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
        {"model": "embedding", "count": 4, "percentage": 50.0},
        {"model": "large", "count": 3, "percentage": 37.5},
        {"model": "small", "count": 1, "percentage": 12.5},
    ]
    assert merged_counter_calls == [
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
        "all", SimpleNamespace()
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
        {"created_at__gte": FIXED_NOW - timedelta(days=90)},
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
                **(
                    {"model_used__isnull": False}
                    if endpoint is dashboard.get_models_distribution
                    else {}
                ),
            },
        )

    if endpoint is dashboard.get_models_distribution:
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
