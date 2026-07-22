from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.usage_tracker import QuotaExceededError, UsageTracker


usage_module = import_module("app.services.usage_tracker")
NOW = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)


def team_model(**overrides):
    defaults = {
        "team_id": "team-1",
        "is_enabled": True,
        "daily_reset_at": NOW,
        "monthly_reset_at": NOW,
        "daily_tokens_used": 10,
        "monthly_tokens_used": 20,
        "daily_requests_used": 1,
        "monthly_requests_used": 2,
        "daily_token_limit": None,
        "monthly_token_limit": None,
        "daily_request_limit": None,
        "monthly_request_limit": None,
        "model": SimpleNamespace(name="Test Model"),
        "save": AsyncMock(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_get_team_model_builds_related_query(monkeypatch):
    expected = team_model()

    class Query:
        def select_related(self, relation):
            assert relation == "model"
            return self

        async def first(self):
            return expected

    monkeypatch.setattr(
        usage_module.TeamModel,
        "filter",
        lambda **kwargs: (
            Query() if kwargs == {"team_id": "team-1", "model_id": "model-1"} else None
        ),
    )

    assert await UsageTracker()._get_team_model("team-1", "model-1") is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "message"),
    [
        (None, "No authorization found"),
        (team_model(is_enabled=False), "authorization is disabled"),
    ],
)
async def test_check_quota_rejects_missing_or_disabled_model(
    monkeypatch, model, message
):
    tracker = UsageTracker()
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    with pytest.raises(ValueError, match=message):
        await tracker.check_quota("team-1", "model-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("limits", "quota_type"),
    [
        ({"daily_token_limit": 10}, "daily_token"),
        ({"monthly_token_limit": 20}, "monthly_token"),
        ({"daily_request_limit": 1}, "daily_request"),
        ({"monthly_request_limit": 2}, "monthly_request"),
    ],
)
async def test_check_quota_reports_each_limit(monkeypatch, limits, quota_type):
    tracker = UsageTracker()
    model = team_model(**limits)
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    with pytest.raises(QuotaExceededError) as exc_info:
        await tracker.check_quota("team-1", "model-1", tokens_needed=1)

    assert exc_info.value.quota_type == quota_type


@pytest.mark.asyncio
async def test_check_quota_persists_resets(monkeypatch):
    tracker = UsageTracker()
    model = team_model(daily_reset_at=None, monthly_reset_at=None)
    monkeypatch.setattr(usage_module, "now", lambda: NOW)
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    assert await tracker.check_quota("team-1", "model-1") is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (0, 0)
    assert (model.daily_requests_used, model.monthly_requests_used) == (0, 0)
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_record_usage_rejects_missing_model(monkeypatch):
    tracker = UsageTracker()
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=None))

    with pytest.raises(ValueError, match="cannot record usage"):
        await tracker.record_usage("team-1", "model-1", 3)


@pytest.mark.asyncio
async def test_record_usage_aggregates_and_saves(monkeypatch):
    tracker = UsageTracker()
    model = team_model()
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    assert await tracker.record_usage("team-1", "model-1", 5, 3) is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (15, 25)
    assert (model.daily_requests_used, model.monthly_requests_used) == (4, 5)
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_and_record_usage_resets_aggregates_and_uses_transaction(
    monkeypatch,
):
    tracker = UsageTracker()
    model = team_model(daily_reset_at=None, monthly_reset_at=None)
    connection = object()

    class Query:
        def using_db(self, conn):
            assert conn is connection
            return self

        def select_for_update(self):
            return self

        async def first(self):
            return model

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(usage_module, "now", lambda: NOW)
    monkeypatch.setattr(usage_module, "in_transaction", transaction)
    monkeypatch.setattr(usage_module.TeamModel, "filter", lambda **kwargs: Query())

    assert await tracker.check_and_record_usage("team-1", "model-1", 5, 2) is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (5, 5)
    assert (model.daily_requests_used, model.monthly_requests_used) == (2, 2)
    model.save.assert_awaited_once_with(using_db=connection)


@pytest.mark.asyncio
async def test_check_quota_with_model_rejects_disabled_and_persists_reset(monkeypatch):
    tracker = UsageTracker()
    disabled = team_model(is_enabled=False)

    with pytest.raises(ValueError, match="authorization is disabled"):
        await tracker.check_quota_with_model(disabled)

    model = team_model(daily_reset_at=None)
    monkeypatch.setattr(usage_module, "now", lambda: NOW)
    await tracker.check_quota_with_model(model)

    assert model.daily_tokens_used == 0
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_get_usage_stats_handles_missing_and_aggregates_percentages(monkeypatch):
    tracker = UsageTracker()
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=None))
    assert await tracker.get_usage_stats("team-1", "model-1") is None

    model = team_model(
        daily_tokens_used=25,
        monthly_tokens_used=40,
        daily_token_limit=200,
        monthly_token_limit=80,
    )
    monkeypatch.setattr(tracker, "_get_team_model", AsyncMock(return_value=model))

    stats = await tracker.get_usage_stats("team-1", "model-1")

    assert stats == {
        "model_id": "model-1",
        "model_name": "Test Model",
        "daily_tokens_used": 25,
        "daily_token_limit": 200,
        "daily_token_percent": 12.5,
        "monthly_tokens_used": 40,
        "monthly_token_limit": 80,
        "monthly_token_percent": 50.0,
        "daily_requests_used": 1,
        "daily_request_limit": None,
        "monthly_requests_used": 2,
        "monthly_request_limit": None,
        "is_enabled": True,
    }
