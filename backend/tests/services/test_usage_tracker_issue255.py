from datetime import UTC, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.usage_tracker import QuotaExceededError, UsageTracker

usage_module = import_module("app.services.usage_tracker")


def team_model(**overrides):
    values = {
        "team_id": "team-1",
        "model": SimpleNamespace(name="Primary"),
        "is_enabled": True,
        "daily_tokens_used": 4,
        "monthly_tokens_used": 8,
        "daily_requests_used": 1,
        "monthly_requests_used": 2,
        "daily_token_limit": None,
        "monthly_token_limit": None,
        "daily_request_limit": None,
        "monthly_request_limit": None,
        "daily_reset_at": datetime(2026, 7, 22, tzinfo=UTC),
        "monthly_reset_at": datetime(2026, 7, 1, tzinfo=UTC),
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limits", "quota_type"),
    [
        ({"daily_token_limit": 5}, "daily_token"),
        ({"monthly_token_limit": 9}, "monthly_token"),
        ({"daily_request_limit": 1}, "daily_request"),
        ({"monthly_request_limit": 2}, "monthly_request"),
    ],
)
async def test_check_quota_with_model_reports_each_limit(
    monkeypatch, limits, quota_type
):
    tracker = UsageTracker()
    model = team_model(**limits)
    monkeypatch.setattr(
        tracker, "_reset_daily_if_needed", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        tracker, "_reset_monthly_if_needed", AsyncMock(return_value=False)
    )

    with pytest.raises(QuotaExceededError) as caught:
        await tracker.check_quota_with_model(model, tokens_needed=2)

    assert caught.value.quota_type == quota_type
    model.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_usage_stats_resets_expired_counts_and_calculates_percentages(
    monkeypatch,
):
    current = datetime(2026, 7, 22, 12, tzinfo=UTC)
    model = team_model(
        daily_token_limit=20,
        monthly_token_limit=40,
        daily_reset_at=current - timedelta(days=1),
        monthly_reset_at=current,
    )
    tracker = UsageTracker()
    monkeypatch.setattr(usage_module, "now", lambda: current)
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    stats = await tracker.get_usage_stats("team-1", "model-1")

    assert stats["daily_tokens_used"] == 0
    assert stats["daily_token_percent"] == 0.0
    assert stats["monthly_token_percent"] == 20.0
    model.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_usage_updates_all_counters(monkeypatch):
    tracker = UsageTracker()
    model = team_model()
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))
    monkeypatch.setattr(
        tracker, "_reset_daily_if_needed", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        tracker, "_reset_monthly_if_needed", AsyncMock(return_value=False)
    )

    result = await tracker.record_usage("team-1", "model-1", 3, request_count=2)

    assert result is model
    assert (
        model.daily_tokens_used,
        model.monthly_tokens_used,
        model.daily_requests_used,
        model.monthly_requests_used,
    ) == (7, 11, 3, 4)
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_and_record_usage_locks_and_saves_in_transaction(monkeypatch):
    tracker = UsageTracker()
    model = team_model()
    connection = object()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = connection
    query = MagicMock()
    query.using_db.return_value = query
    query.select_for_update.return_value = query
    query.first = AsyncMock(return_value=model)
    monkeypatch.setattr(usage_module, "in_transaction", lambda: transaction)
    monkeypatch.setattr(usage_module.TeamModel, "filter", MagicMock(return_value=query))

    result = await tracker.check_and_record_usage(
        "team-1", "model-1", 3, request_count=2
    )

    assert result is model
    query.using_db.assert_called_once_with(connection)
    query.select_for_update.assert_called_once_with()
    model.save.assert_awaited_once_with(using_db=connection)
    assert (model.daily_tokens_used, model.monthly_requests_used) == (7, 4)
