"""Workflow orchestration cancellation state-transition tests."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import RunStatus
from app.services.workflow.orchestrator import WorkflowOrchestrator


class TestWorkflowOrchestratorPendingCancellation:
    """Tests for cancellation of pending workflow runs."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [RunStatus.PENDING, RunStatus.WAITING])
    async def test_cancel_active_run_marks_context_and_publishes_error(self, status):
        run_id = str(uuid4())
        redis_client = MagicMock()
        run = MagicMock(status=status)
        run.save = AsyncMock()
        context = MagicMock()
        context.set_status = AsyncMock()
        stream_manager = MagicMock()
        stream_manager.publish_workflow_error = AsyncMock()

        with patch("app.services.workflow.orchestrator.WorkflowRun") as workflow_run:
            with patch(
                "app.services.workflow.orchestrator.WorkflowPauseRequest"
            ) as pause_request_cls:
                with patch(
                    "app.services.workflow.orchestrator.get_redis",
                    new=AsyncMock(return_value=redis_client),
                ):
                    with patch(
                        "app.services.workflow.orchestrator.ExecutionContext.load",
                        new=AsyncMock(return_value=context),
                    ):
                        with patch(
                            "app.services.workflow.orchestrator.StreamManager",
                            return_value=stream_manager,
                        ):
                            pause_request_cls.filter.return_value.update = AsyncMock(
                                return_value=1
                            )
                            pause_request_cls.filter.return_value.all = AsyncMock(
                                return_value=[]
                            )
                            workflow_run.filter.return_value.first = AsyncMock(
                                return_value=run
                            )

                            cancelled = await WorkflowOrchestrator().cancel(run_id)

        assert cancelled is True
        assert run.status == RunStatus.CANCELLED
        run.save.assert_awaited_once()
        context.set_status.assert_awaited_once_with("cancelled")
        stream_manager.publish_workflow_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_active_run_without_workflow_skips_pause_cleanup():
    run_id = str(uuid4())
    run = MagicMock(status=RunStatus.PENDING, workflow_id=None)
    run.save = AsyncMock()
    context = MagicMock()
    context.set_status = AsyncMock()
    stream_manager = MagicMock()
    stream_manager.publish_workflow_error = AsyncMock()

    with patch("app.services.workflow.orchestrator.WorkflowRun") as workflow_run:
        with patch(
            "app.services.workflow.orchestrator.WorkflowPauseRequest"
        ) as pause_request_cls:
            with patch(
                "app.services.workflow.orchestrator.get_redis",
                new=AsyncMock(return_value=MagicMock()),
            ):
                with patch(
                    "app.services.workflow.orchestrator.ExecutionContext.load",
                    new=AsyncMock(return_value=context),
                ):
                    with patch(
                        "app.services.workflow.orchestrator.StreamManager",
                        return_value=stream_manager,
                    ):
                        workflow_run.filter.return_value.first = AsyncMock(
                            return_value=run
                        )
                        cancelled = await WorkflowOrchestrator().cancel(run_id)

    assert cancelled is True
    pause_request_cls.filter.assert_not_called()
    context.set_status.assert_awaited_once_with("cancelled")


@pytest.mark.asyncio
async def test_cancel_active_run_removes_pending_pause_notifications():
    run_id = str(uuid4())
    request = MagicMock(id=uuid4())
    run = MagicMock(status=RunStatus.WAITING, workflow_id=uuid4())
    run.save = AsyncMock()
    pause_query = MagicMock()
    pause_query.update = AsyncMock(return_value=1)
    pause_query.all = AsyncMock(return_value=[request])
    context = MagicMock(set_status=AsyncMock())
    stream_manager = MagicMock(publish_workflow_error=AsyncMock())
    remove = AsyncMock()

    with (
        patch("app.services.workflow.orchestrator.WorkflowRun") as workflow_run,
        patch("app.services.workflow.orchestrator.WorkflowPauseRequest") as pause_cls,
        patch(
            "app.services.workflow.orchestrator.get_redis",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.ExecutionContext.load",
            new=AsyncMock(return_value=context),
        ),
        patch(
            "app.services.workflow.orchestrator.StreamManager",
            return_value=stream_manager,
        ),
        patch(
            "app.services.workflow.orchestrator.remove_pause_pending_notifications",
            new=remove,
        ),
    ):
        workflow_run.filter.return_value.first = AsyncMock(return_value=run)
        pause_cls.filter.return_value = pause_query
        cancelled = await WorkflowOrchestrator().cancel(run_id)

    assert cancelled is True
    pause_query.update.assert_awaited_once()
    remove.assert_awaited_once_with(request.id)
