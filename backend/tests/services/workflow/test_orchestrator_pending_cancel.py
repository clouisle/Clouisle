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
