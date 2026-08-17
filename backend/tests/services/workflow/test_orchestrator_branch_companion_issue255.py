from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus, RunStatus
from app.services.workflow.orchestrator import WorkflowOrchestrator, get_node_type_label


@pytest.mark.asyncio
async def test_issue255_orchestrator_node_label_known_and_unknown_branches():
    with (
        patch(
            "app.services.workflow.orchestrator.get_default_language",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.workflow.orchestrator.t", return_value="Answer"
        ) as translate,
    ):
        assert await get_node_type_label("answer") == "Answer"
        assert await get_node_type_label("not-a-node") is None

    translate.assert_called_once_with("node_type_answer", lang="en")


@pytest.mark.asyncio
async def test_issue255_orchestrator_complete_run_team_notification_branch():
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    team_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        is_debug=False,
        triggered_by_id=None,
        total_token_usage={"prompt": 2, "completion": 3},
        save=AsyncMock(),
    )
    workflow = SimpleNamespace(id=workflow_id, team_id=team_id, name="Flow")
    executions = [
        SimpleNamespace(status=NodeStatus.SUCCESS),
        SimpleNamespace(status=NodeStatus.FAILED),
        SimpleNamespace(status=NodeStatus.SKIPPED),
    ]
    node_query = MagicMock()
    node_query.all = AsyncMock(return_value=executions)
    workflow_query = MagicMock()
    workflow_query.first = AsyncMock(return_value=workflow)
    workflow_query.update = AsyncMock()
    team_query = MagicMock()
    team_query.update = AsyncMock()

    with (
        patch(
            "app.services.workflow.orchestrator.NodeExecution.filter",
            return_value=node_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Workflow.filter",
            return_value=workflow_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Team.filter", return_value=team_query
        ),
        patch(
            "app.services.workflow.orchestrator.get_default_language",
            AsyncMock(return_value="en"),
        ),
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService.send_to_team",
            AsyncMock(),
        ) as notify,
    ):
        await orchestrator._complete_run(run, {"answer": "ok"}, 25)

    assert (
        run.total_nodes,
        run.executed_nodes,
        run.failed_nodes,
        run.skipped_nodes,
    ) == (
        3,
        1,
        1,
        1,
    )
    assert run.status == RunStatus.SUCCESS
    workflow_query.update.assert_awaited_once()
    team_query.update.assert_awaited_once()
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_issue255_orchestrator_fail_run_user_notification_failure_is_swallowed():
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    workflow_id = uuid4()
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=workflow_id,
        triggered_by_id=uuid4(),
        triggered_by=None,
        total_token_usage=None,
        save=AsyncMock(),
        fetch_related=AsyncMock(),
    )
    workflow = SimpleNamespace(id=workflow_id, team_id=None, name="Flow")
    node_query = MagicMock()
    node_query.all = AsyncMock(return_value=[])
    workflow_query = MagicMock()
    workflow_query.first = AsyncMock(return_value=workflow)
    workflow_query.update = AsyncMock()

    with (
        patch(
            "app.services.workflow.orchestrator.NodeExecution.filter",
            return_value=node_query,
        ),
        patch(
            "app.services.workflow.orchestrator.Workflow.filter",
            return_value=workflow_query,
        ),
        patch(
            "app.services.workflow.orchestrator.AutoNotificationService.send_to_user",
            AsyncMock(side_effect=RuntimeError("network unavailable")),
        ) as notify,
    ):
        await orchestrator._fail_run(run, "failed", 30)

    assert run.status == RunStatus.FAILED
    assert run.error_message == "failed"
    run.fetch_related.assert_awaited_once_with("triggered_by")
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_issue255_orchestrator_cancel_missing_context_and_nullable_status_dates():
    orchestrator = WorkflowOrchestrator(enable_cache=False, enable_metrics=False)
    run = SimpleNamespace(
        id=uuid4(),
        workflow_id=uuid4(),
        status=RunStatus.PENDING,
        inputs={},
        outputs=None,
        error_message=None,
        total_duration_ms=None,
        created_at=None,
        finished_at=None,
        save=AsyncMock(),
    )
    query = MagicMock()
    query.first = AsyncMock(return_value=run)
    stream = MagicMock()
    stream.publish_workflow_error = AsyncMock()

    with (
        patch(
            "app.services.workflow.orchestrator.WorkflowRun.filter", return_value=query
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowPauseRequest.filter"
        ) as pause_filter,
        patch(
            "app.services.workflow.orchestrator.get_redis",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            AsyncMock(side_effect=RuntimeError("context missing")),
        ),
        patch("app.services.workflow.orchestrator.StreamManager", return_value=stream),
    ):
        pause_filter.return_value.update = AsyncMock(return_value=1)
        pause_filter.return_value.all = AsyncMock(return_value=[])
        assert await orchestrator.cancel(str(run.id)) is True
        status = await orchestrator.get_run_status(str(run.id))

    assert run.status == RunStatus.CANCELLED
    assert status is not None
    assert status["created_at"] is None
    assert status["finished_at"] is not None
    stream.publish_workflow_error.assert_awaited_once()
