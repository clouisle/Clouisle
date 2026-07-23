from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import admin_observability as service


@pytest.fixture
def period(monkeypatch):
    end = datetime(2026, 7, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(service, "normalize_time_range", lambda _: (None, end))
    return end


def test_normalizers_serializers_and_pagination(monkeypatch):
    end = datetime(2026, 7, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(service, "now", lambda: end)

    assert service.normalize_time_range("all") == (None, end)
    assert service.normalize_time_range("invalid")[0] == end - service.timedelta(
        days=30
    )
    assert service.normalize_granularity("7d") == "hour"
    assert service.normalize_granularity("30d", "hour") == "hour"
    assert service.safe_rate(1, 0) == 0
    assert service.percentile_payload([])["p50_ms"] is None
    assert service._serialize_value(uuid4()).__class__ is str
    assert service._serialize_value(1.236) == 1.24
    assert service._serialize_datetime(None) is None
    assert service._serialize_datetime(3) == "3"
    assert service._coerce_datetime("2026-07-22T12:00:00+00:00") == end
    assert service._round_nullable(1.6) == 2
    assert service._time_where("created", None, end) == ("created < $1", [end])
    assert service._paginate([1, 2], 0, 200, {"extra": True}) == {
        "items": [1, 2],
        "total": 2,
        "page": 1,
        "page_size": 100,
        "extra": True,
    }


def test_performance_bucket_sort_and_merge_helpers():
    performance = service._decorate_performance_row(
        {
            "request_count": 2,
            "success_count": 1,
            "timeout_count": 1,
            "total_tokens": 5,
            "p50_ms": 1.6,
        },
        "request_count",
    )
    assert performance["success_rate"] == 50
    assert performance["timeout_rate"] == 50
    assert performance["avg_tokens"] == 2.5
    assert performance["p50_ms"] == 2

    bucket = service._decorate_bucket_row(
        {"bucket": datetime(2026, 7, 22, tzinfo=UTC), "run_count": 0},
        "run_count",
    )
    assert bucket["success_rate"] == 0
    assert bucket["bucket"] == "2026-07-22T00:00:00+00:00"
    assert service._agent_sort_key("tokens") == "total_tokens"
    assert service._agent_sort_key("bad") == "request_count"
    assert service._workflow_sort_key("failed_nodes") == "failed_nodes"
    assert service._workflow_sort_key("bad") == "run_count"
    assert service._merge_count_buckets(
        [{"bucket": "b", "count": 2}], [{"bucket": "a", "count": 3}]
    ) == [
        {"bucket": "a", "agent_requests": 0, "workflow_runs": 3, "total_requests": 3},
        {"bucket": "b", "agent_requests": 2, "workflow_runs": 0, "total_requests": 2},
    ]


@pytest.mark.asyncio
async def test_agents_and_agent_detail_sort_filter_and_trend(monkeypatch, period):
    agent_id = uuid4()
    rows = [
        {"agent_id": str(agent_id), "request_count": 1},
        {"agent_id": str(uuid4()), "request_count": 3},
    ]
    monkeypatch.setattr(
        service, "_agent_performance_rows", AsyncMock(return_value=rows)
    )
    trend = AsyncMock(return_value=[{"bucket": "today"}])
    monkeypatch.setattr(service, "_agent_trend_rows", trend)

    listing = await service.get_agents("all", 1, 1, "requests", "desc")
    detail = await service.get_agent_detail(agent_id, "all")

    assert listing["items"][0]["request_count"] == 3
    assert listing["total"] == 2
    assert detail == {
        "time_range": "all",
        "agent": rows[0],
        "trend": [{"bucket": "today"}],
    }
    trend.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflows_and_workflow_detail_sort_filter_nodes(monkeypatch, period):
    workflow_id = uuid4()
    rows = [
        {"workflow_id": str(workflow_id), "run_count": 1},
        {"workflow_id": str(uuid4()), "run_count": 3},
    ]
    monkeypatch.setattr(
        service, "_workflow_performance_rows", AsyncMock(return_value=rows)
    )
    monkeypatch.setattr(
        service, "_workflow_trend_rows", AsyncMock(return_value=[{"bucket": "today"}])
    )
    monkeypatch.setattr(
        service, "_workflow_node_rows", AsyncMock(return_value=[{"node_type": "llm"}])
    )

    listing = await service.get_workflows("all", 1, 20, "runs", "asc")
    detail = await service.get_workflow_detail(workflow_id, "all")

    assert [item["run_count"] for item in listing["items"]] == [1, 3]
    assert detail["workflow"] == rows[0]
    assert detail["nodes"] == [{"node_type": "llm"}]


@pytest.mark.asyncio
async def test_timeout_log_analytics_combines_filters_and_distribution(
    monkeypatch, period
):
    monkeypatch.setattr(
        service,
        "_workflow_timeout_rows",
        AsyncMock(
            return_value=[
                {
                    "workflow_id": "w1",
                    "workflow_name": None,
                    "created_at": period,
                    "duration_ms": 10,
                    "status": "timeout",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        service,
        "_agent_timeout_like_rows",
        AsyncMock(
            return_value=[
                {
                    "agent_id": "a1",
                    "agent_name": "Agent",
                    "model_used": "model",
                    "created_at": period,
                    "duration_ms": 20,
                    "round_status": "error",
                }
            ]
        ),
    )

    result = await service.get_timeouts("all", "all", 1, 20)

    assert result["distribution"] == {"workflow": 1, "agent": 1}
    assert result["items"][0]["source"] in {"workflow", "agent"}
    assert result["agent_timeout_type_available"] is False


@pytest.mark.asyncio
async def test_throughput_merges_metrics_and_current_counters(monkeypatch, period):
    buckets = AsyncMock(
        side_effect=[
            [{"bucket": "2026-07-22", "count": 2}],
            [{"bucket": "2026-07-22", "count": 3}],
        ]
    )
    monkeypatch.setattr(service, "_bucket_count_rows", buckets)
    monkeypatch.setattr(service, "_scalar_count", AsyncMock(return_value=4))
    monkeypatch.setattr(service, "_current_qps", AsyncMock(return_value=0.5))

    result = await service.get_throughput("7d", None)

    assert result["granularity"] == "hour"
    assert result["current"] == {"qps": 0.5, "tps": 0.5, "running_workflows": 4}
    assert result["buckets"][0]["total_requests"] == 5


@pytest.mark.asyncio
async def test_token_analytics_groups_models_and_sources(monkeypatch, period):
    monkeypatch.setattr(
        service,
        "_agent_message_rows",
        AsyncMock(
            return_value=[
                {"model_used": "small", "tokens": 2},
                {"model_used": None, "tokens": None},
                {"model_used": "small", "tokens": 3},
            ]
        ),
    )
    monkeypatch.setattr(
        service, "_workflow_run_rows", AsyncMock(return_value=[{"tokens": 7}])
    )

    result = await service.get_tokens("30d")

    assert result["total_tokens"] == 12
    assert result["by_source"] == [
        {"source": "agent", "tokens": 5},
        {"source": "workflow", "tokens": 7},
    ]
    assert result["by_model"] == [
        {"model": "small", "tokens": 5},
        {"model": "unknown", "tokens": 0},
    ]


@pytest.mark.asyncio
async def test_query_row_helpers_normalize_database_results(monkeypatch, period):
    execute = AsyncMock(
        side_effect=[
            (1, [{"created_at": period, "duration_ms": 1.234}]),
            (1, [{"created_at": period, "status": "success"}]),
            (1, [{"request_count": 2, "success_count": 1, "total_tokens": 3}]),
            (1, [{"run_count": 2, "success_count": 1, "total_tokens": 3}]),
        ]
    )
    monkeypatch.setattr(service, "_execute", execute)

    messages = await service._agent_message_rows(None, period)
    workflows = await service._workflow_run_rows(None, period)
    agents = await service._agent_performance_rows(None, period)
    performance = await service._workflow_performance_rows(None, period)

    assert messages[0]["created_at"] == period.isoformat()
    assert messages[0]["duration_ms"] == 1.23
    assert workflows[0]["status"] == "success"
    assert agents[0]["success_rate"] == 50
    assert performance[0]["avg_tokens"] == 1.5
    assert "assistant_final" in execute.await_args_list[0].args[0]


@pytest.mark.asyncio
async def test_detail_and_timeout_query_helpers(monkeypatch, period):
    execute = AsyncMock(
        side_effect=[
            (1, [{"bucket": period, "request_count": 2, "success_count": 1}]),
            (1, [{"bucket": period, "run_count": 2, "success_count": 1}]),
            (1, [{"node_type": "llm", "avg_duration_ms": 1.234}]),
            (1, [{"created_at": period, "workflow_name": "Flow"}]),
            (1, [{"created_at": period, "agent_name": "Agent"}]),
        ]
    )
    monkeypatch.setattr(service, "_execute", execute)
    entity_id = uuid4()

    assert (await service._agent_trend_rows(entity_id, None, period, "day"))[0][
        "success_rate"
    ] == 50
    assert (await service._workflow_trend_rows(entity_id, None, period, "day"))[0][
        "success_rate"
    ] == 50
    assert (await service._workflow_node_rows(entity_id, None, period))[0][
        "avg_duration_ms"
    ] == 1.23
    assert (await service._workflow_timeout_rows(None, period))[0][
        "created_at"
    ] == period.isoformat()
    assert (await service._agent_timeout_like_rows(None, period))[0][
        "agent_name"
    ] == "Agent"


@pytest.mark.asyncio
async def test_database_count_bucket_and_qps_boundaries(monkeypatch, period):
    connection = SimpleNamespace(
        execute_query=AsyncMock(return_value=(1, [{"count": 5, "bucket": period}]))
    )
    monkeypatch.setattr(service.Tortoise, "get_connection", lambda _: connection)

    assert await service._execute("SELECT", []) == (
        1,
        [{"count": 5, "bucket": period}],
    )
    assert await service._scalar_count("table", "true", []) == 5

    monkeypatch.setattr(service, "_execute", AsyncMock(return_value=(0, [])))
    assert await service._scalar_count("table", "true", []) == 0

    monkeypatch.setattr(
        service,
        "_execute",
        AsyncMock(return_value=(1, [{"bucket": period, "count": 2}])),
    )
    rows = await service._bucket_count_rows(
        "messages", "created_at", None, period, "hour", "canonical = true"
    )
    assert rows == [{"bucket": period.isoformat(), "count": 2}]

    count = AsyncMock(side_effect=[30, 30])
    monkeypatch.setattr(service, "_scalar_count", count)
    assert await service._current_qps(period) == 1
