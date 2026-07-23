import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.tasks.usage import reset_daily_usage, reset_monthly_usage


@pytest.fixture
def task_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.mark.parametrize(
    ("task", "period", "expected_boundary", "expected_update"),
    [
        (
            reset_daily_usage,
            "daily",
            datetime(2026, 7, 19, tzinfo=timezone.utc),
            {
                "daily_tokens_used": 0,
                "daily_requests_used": 0,
                "daily_reset_at": datetime(2026, 7, 19, 14, 30, tzinfo=timezone.utc),
            },
        ),
        (
            reset_monthly_usage,
            "monthly",
            datetime(2026, 7, 1, tzinfo=timezone.utc),
            {
                "monthly_tokens_used": 0,
                "monthly_requests_used": 0,
                "monthly_reset_at": datetime(2026, 7, 19, 14, 30, tzinfo=timezone.utc),
            },
        ),
    ],
)
@pytest.mark.parametrize("count", [3, 0])
def test_reset_usage_updates_matching_models_and_logs_result(
    task, period, expected_boundary, expected_update, count, task_loop
):
    current_time = datetime(2026, 7, 19, 14, 30, tzinfo=timezone.utc)
    update = AsyncMock(return_value=count)

    with (
        patch("app.tasks.usage.get_now", return_value=current_time),
        patch("app.tasks.usage.TeamModel.filter") as model_filter,
        patch("app.tasks.usage.logger.info") as log_info,
    ):
        model_filter.return_value.update = update

        assert task.run() == count

    model_filter.assert_called_once_with(
        **{f"{period}_reset_at__lt": expected_boundary}
    )
    update.assert_awaited_once_with(**expected_update)
    if count:
        log_info.assert_called_once_with(
            f"Reset {period} usage for {count} team models"
        )
    else:
        log_info.assert_called_once_with(f"No team models need {period} usage reset")


@pytest.mark.parametrize("task", [reset_daily_usage, reset_monthly_usage])
def test_reset_usage_task_propagates_update_failure(task, task_loop):
    update = AsyncMock(side_effect=RuntimeError("database unavailable"))

    with (
        patch("app.tasks.usage.TeamModel.filter") as model_filter,
        patch("app.tasks.usage.logger.info") as log_info,
    ):
        model_filter.return_value.update = update

        with pytest.raises(RuntimeError, match="database unavailable"):
            task.run()

    log_info.assert_not_called()


def test_reset_usage_tasks_have_expected_celery_names():
    assert reset_daily_usage.name == "tasks.reset_daily_usage"
    assert reset_monthly_usage.name == "tasks.reset_monthly_usage"
