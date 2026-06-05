from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import admin_observability


def test_continuous_percentile_handles_empty_and_single_value():
    assert admin_observability.continuous_percentile([], 0.5) is None
    assert admin_observability.continuous_percentile([42], 0.95) == 42


def test_continuous_percentile_interpolates_even_count():
    values = [10, 20, 30, 40]

    assert admin_observability.continuous_percentile(values, 0.5) == 25
    assert admin_observability.continuous_percentile(values, 0.9) == pytest.approx(37)
    assert admin_observability.continuous_percentile(values, 0.95) == pytest.approx(
        38.5
    )
    assert admin_observability.continuous_percentile(values, 0.99) == pytest.approx(
        39.7
    )


def test_extract_token_total_accepts_total_and_prompt_completion_shapes():
    assert admin_observability.extract_token_total({"total": 12}) == 12
    assert admin_observability.extract_token_total({"total_tokens": 13}) == 13
    assert admin_observability.extract_token_total({"prompt": 7, "completion": 5}) == 12
    assert (
        admin_observability.extract_token_total(
            {"prompt_tokens": 3, "completion_tokens": 4}
        )
        == 7
    )
    assert admin_observability.extract_token_total(None) == 0


@pytest.mark.asyncio
async def test_cached_payload_returns_cached_value():
    redis = AsyncMock()
    redis.get.return_value = '{"cached": true}'
    producer = AsyncMock(return_value={"cached": False})

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.cached_payload("test", {}, producer)

    assert result == {"cached": True}
    producer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_payload_computes_when_redis_fails():
    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis down")
    redis.setex.side_effect = RuntimeError("redis down")
    producer = AsyncMock(return_value={"fresh": True})

    with patch("app.services.admin_observability.get_redis", return_value=redis):
        result = await admin_observability.cached_payload("test", {}, producer)

    assert result == {"fresh": True}
    producer.assert_awaited_once()


@pytest.mark.asyncio
async def test_overview_reports_ttft_separately_from_total_duration():
    agent_rows = [
        {
            "duration_ms": 30000,
            "first_token_ms": 900,
            "round_status": "completed",
            "tokens": 10,
            "created_at": "2026-06-05T10:00:00+00:00",
        },
        {
            "duration_ms": 60000,
            "first_token_ms": 1300,
            "round_status": "completed",
            "tokens": 20,
            "created_at": "2026-06-05T10:01:00+00:00",
        },
        {
            "duration_ms": 90000,
            "first_token_ms": None,
            "round_status": "completed",
            "tokens": 30,
            "created_at": "2026-06-05T10:02:00+00:00",
        },
    ]
    workflow_rows = [
        {
            "duration_ms": 120000,
            "status": "success",
            "tokens": 40,
            "created_at": "2026-06-05T10:03:00+00:00",
        }
    ]

    with (
        patch(
            "app.services.admin_observability.normalize_time_range",
            return_value=(None, admin_observability.to_utc(admin_observability.now())),
        ),
        patch(
            "app.services.admin_observability._agent_message_rows",
            new=AsyncMock(return_value=agent_rows),
        ),
        patch(
            "app.services.admin_observability._workflow_run_rows",
            new=AsyncMock(return_value=workflow_rows),
        ),
    ):
        result = await admin_observability.get_overview("30d")

    assert result["latency"]["p95_ms"] == 115500
    assert result["ttft"]["p95_ms"] == 1280


@pytest.mark.asyncio
async def test_slow_queries_returns_unavailable_when_pg_stat_statements_missing():
    conn = MagicMock()
    conn.execute_query = AsyncMock(side_effect=RuntimeError("relation does not exist"))

    with patch(
        "app.services.admin_observability.Tortoise.get_connection", return_value=conn
    ):
        result = await admin_observability.get_slow_queries(1000, 1, 20)

    assert result["available"] is False
    assert result["items"] == []


@pytest.mark.asyncio
async def test_workers_return_unknown_when_inspect_fails():
    with patch(
        "app.services.admin_observability.celery_app.control.inspect",
        side_effect=RuntimeError("no workers"),
    ):
        result = await admin_observability.get_workers()

    assert result["status"] == "unknown"
    assert result["worker_count"] == 0
