import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.tasks import usage


@pytest.mark.parametrize(
    ("task", "current_time", "filter_kwargs", "update_kwargs"),
    [
        (
            usage.reset_daily_usage,
            datetime(2026, 7, 19, 15, 30, tzinfo=timezone.utc),
            {"daily_reset_at__lt": datetime(2026, 7, 19, tzinfo=timezone.utc)},
            {
                "daily_tokens_used": 0,
                "daily_requests_used": 0,
                "daily_reset_at": datetime(2026, 7, 19, 15, 30, tzinfo=timezone.utc),
            },
        ),
        (
            usage.reset_monthly_usage,
            datetime(2026, 7, 19, 15, 30, tzinfo=timezone.utc),
            {"monthly_reset_at__lt": datetime(2026, 7, 1, tzinfo=timezone.utc)},
            {
                "monthly_tokens_used": 0,
                "monthly_requests_used": 0,
                "monthly_reset_at": datetime(2026, 7, 19, 15, 30, tzinfo=timezone.utc),
            },
        ),
    ],
)
def test_usage_reset_tasks_update_only_stale_models(
    task, current_time, filter_kwargs, update_kwargs
):
    queryset = Mock(update=AsyncMock(return_value=2))
    loop = asyncio.new_event_loop()
    try:
        with (
            patch.object(usage, "get_now", return_value=current_time),
            patch.object(usage.TeamModel, "filter", return_value=queryset) as filter_,
            patch.object(usage.asyncio, "get_event_loop", return_value=loop),
        ):
            assert task.run() == 2
    finally:
        loop.close()

    filter_.assert_called_once_with(**filter_kwargs)
    queryset.update.assert_awaited_once_with(**update_kwargs)


@pytest.mark.parametrize(
    "task, message",
    [
        (usage.reset_daily_usage, "No team models need daily usage reset"),
        (usage.reset_monthly_usage, "No team models need monthly usage reset"),
    ],
)
def test_usage_reset_tasks_log_when_no_models_need_reset(task, message, caplog):
    queryset = Mock(update=AsyncMock(return_value=0))
    loop = asyncio.new_event_loop()
    try:
        with (
            patch.object(usage.TeamModel, "filter", return_value=queryset),
            patch.object(usage.asyncio, "get_event_loop", return_value=loop),
            caplog.at_level("INFO", logger="app.tasks.usage"),
        ):
            assert task.run() == 0
    finally:
        loop.close()

    assert message in caplog.text
