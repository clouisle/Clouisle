from unittest.mock import AsyncMock

import pytest

from app.core.celery import celery_app
from app.tasks import tool_approval as tool_approval_tasks


@pytest.mark.asyncio
async def test_expiry_sweep_invokes_service_and_reports_count(monkeypatch):
    expire = AsyncMock(return_value=3)
    stale = AsyncMock(return_value=2)
    monkeypatch.setattr("app.services.tool_approvals.expire_due_executions", expire)
    monkeypatch.setattr(
        "app.services.tool_approvals.mark_stale_executing_outcome_unknown", stale
    )
    result = await tool_approval_tasks._expire_tool_approvals(limit=25)
    expire.assert_awaited_once_with(limit=25)
    stale.assert_awaited_once_with(limit=25)
    assert result == {"expired": 3, "outcome_unknown": 2}


def test_expiry_task_is_registered_on_the_default_queue_and_beat():
    assert (
        "tasks.expire_tool_approvals"
        in celery_app.conf.beat_schedule["expire-tool-approvals"]["task"]
    )
    assert (
        celery_app.conf.task_routes["tasks.expire_tool_approvals"]["queue"] == "default"
    )
    assert "app.tasks.tool_approval" in celery_app.conf.include
