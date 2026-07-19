from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.usage_tracker import QuotaExceededError, UsageTracker

NOW = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def freeze_usage_time():
    with patch("app.services.usage_tracker.now", return_value=NOW):
        yield


def team_model(**overrides):
    values = {
        "team_id": "team-1",
        "model_id": "model-1",
        "model": SimpleNamespace(name="Test Model"),
        "is_enabled": True,
        "daily_token_limit": 100,
        "monthly_token_limit": 1_000,
        "daily_request_limit": 10,
        "monthly_request_limit": 100,
        "daily_tokens_used": 20,
        "monthly_tokens_used": 200,
        "daily_requests_used": 2,
        "monthly_requests_used": 20,
        "daily_reset_at": NOW,
        "monthly_reset_at": NOW,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_check_quota_resets_expired_usage_and_allows_exact_limit():
    tracker = UsageTracker()
    model = team_model(
        daily_tokens_used=90,
        monthly_tokens_used=900,
        daily_reset_at=NOW - timedelta(days=1),
        monthly_reset_at=NOW - timedelta(days=32),
    )

    with (
        patch.object(tracker, "_get_team_model", new=AsyncMock(return_value=model)),
        patch("app.services.usage_tracker.now", return_value=NOW),
    ):
        result = await tracker.check_quota("team-1", "model-1", tokens_needed=100)

    assert result is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (0, 0)
    assert (model.daily_requests_used, model.monthly_requests_used) == (0, 0)
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "tokens_needed", "quota_type"),
    [
        ({"daily_tokens_used": 91}, 10, "daily_token"),
        ({"monthly_tokens_used": 991}, 10, "monthly_token"),
        ({"daily_requests_used": 10}, 0, "daily_request"),
        ({"monthly_requests_used": 100}, 0, "monthly_request"),
    ],
)
async def test_check_quota_reports_each_exceeded_quota(
    overrides, tokens_needed, quota_type
):
    tracker = UsageTracker()
    model = team_model(**overrides)

    with patch.object(tracker, "_get_team_model", new=AsyncMock(return_value=model)):
        with pytest.raises(QuotaExceededError) as exc_info:
            await tracker.check_quota("team-1", "model-1", tokens_needed=tokens_needed)

    assert exc_info.value.quota_type == quota_type
    model.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "message"),
    [
        (None, "No authorization found"),
        (team_model(is_enabled=False), "Model authorization is disabled"),
    ],
)
async def test_check_quota_rejects_missing_or_disabled_authorization(model, message):
    tracker = UsageTracker()

    with patch.object(tracker, "_get_team_model", new=AsyncMock(return_value=model)):
        with pytest.raises(ValueError, match=message):
            await tracker.check_quota("team-1", "model-1")


@pytest.mark.asyncio
async def test_record_usage_aggregates_and_persists():
    tracker = UsageTracker()
    model = team_model()

    with patch.object(tracker, "_get_team_model", new=AsyncMock(return_value=model)):
        result = await tracker.record_usage(
            "team-1", "model-1", tokens_used=15, request_count=3
        )

    assert result is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (35, 215)
    assert (model.daily_requests_used, model.monthly_requests_used) == (5, 23)
    model.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_record_usage_rejects_missing_authorization():
    tracker = UsageTracker()

    with patch.object(tracker, "_get_team_model", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="cannot record usage"):
            await tracker.record_usage("team-1", "model-1", tokens_used=1)


def transaction_query(model):
    connection = MagicMock()
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=connection)
    transaction.__aexit__ = AsyncMock(return_value=None)

    query = MagicMock()
    query.using_db.return_value.select_for_update.return_value.first = AsyncMock(
        return_value=model
    )
    return connection, transaction, query


@pytest.mark.asyncio
async def test_check_and_record_usage_locks_aggregates_and_persists_at_boundary():
    tracker = UsageTracker()
    model = team_model(
        daily_tokens_used=90,
        monthly_tokens_used=990,
        daily_requests_used=9,
        monthly_requests_used=99,
    )
    connection, transaction, query = transaction_query(model)

    with (
        patch("app.services.usage_tracker.in_transaction", return_value=transaction),
        patch("app.services.usage_tracker.TeamModel.filter", return_value=query),
        patch("app.services.usage_tracker.now", return_value=NOW),
    ):
        result = await tracker.check_and_record_usage(
            "team-1", "model-1", tokens_used=10, request_count=1
        )

    assert result is model
    assert (model.daily_tokens_used, model.monthly_tokens_used) == (100, 1_000)
    assert (model.daily_requests_used, model.monthly_requests_used) == (10, 100)
    query.using_db.assert_called_once_with(connection)
    model.save.assert_awaited_once_with(using_db=connection)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "error", "quota_type"),
    [
        (None, ValueError, None),
        (team_model(is_enabled=False), ValueError, None),
        (team_model(daily_tokens_used=100), QuotaExceededError, "daily_token"),
        (team_model(daily_requests_used=10), QuotaExceededError, "daily_request"),
    ],
)
async def test_check_and_record_usage_rejects_invalid_or_exceeded_usage(
    model, error, quota_type
):
    tracker = UsageTracker()
    _, transaction, query = transaction_query(model)

    with (
        patch("app.services.usage_tracker.in_transaction", return_value=transaction),
        patch("app.services.usage_tracker.TeamModel.filter", return_value=query),
        pytest.raises(error) as exc_info,
    ):
        await tracker.check_and_record_usage(
            "team-1", "model-1", tokens_used=1, request_count=1
        )

    if quota_type:
        assert exc_info.value.quota_type == quota_type
    if model:
        model.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_quota_with_model_rejects_disabled_and_exceeded_models():
    tracker = UsageTracker()

    with pytest.raises(ValueError, match="disabled"):
        await tracker.check_quota_with_model(team_model(is_enabled=False))

    with pytest.raises(QuotaExceededError) as exc_info:
        await tracker.check_quota_with_model(
            team_model(monthly_tokens_used=1_000), tokens_needed=1
        )

    assert exc_info.value.quota_type == "monthly_token"


@pytest.mark.asyncio
async def test_get_usage_stats_returns_percentages_and_unlimited_boundaries():
    tracker = UsageTracker()
    model = team_model(
        daily_tokens_used=25,
        daily_token_limit=40,
        monthly_token_limit=0,
        model=None,
    )

    with patch.object(
        tracker, "_get_team_model", new=AsyncMock(side_effect=[model, None])
    ):
        stats = await tracker.get_usage_stats("team-1", "model-1")
        missing = await tracker.get_usage_stats("team-1", "missing")

    assert stats == {
        "model_id": "model-1",
        "model_name": None,
        "daily_tokens_used": 25,
        "daily_token_limit": 40,
        "daily_token_percent": 62.5,
        "monthly_tokens_used": 200,
        "monthly_token_limit": 0,
        "monthly_token_percent": None,
        "daily_requests_used": 2,
        "daily_request_limit": 10,
        "monthly_requests_used": 20,
        "monthly_request_limit": 100,
        "is_enabled": True,
    }
    assert missing is None
    model.save.assert_not_awaited()
