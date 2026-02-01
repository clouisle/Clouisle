"""
Celery tasks for workflow execution.
"""

import logging
from uuid import UUID

from celery import shared_task

from app.models.workflow import WorkflowRun, RunStatus

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_workflow_task(
    self,
    run_id: str,
    workflow_id: str,
    inputs: dict,
    user_id: str | None,
    team_id: str | None = None,
    is_debug: bool = False,
) -> dict:
    """
    Celery task to run a workflow.

    Args:
        run_id: UUID string of the workflow run
        workflow_id: UUID string of the workflow
        inputs: Input variables
        user_id: Optional UUID string of the user (None for webhook triggers)
        team_id: Optional UUID string of the team
        is_debug: Whether this is a debug run (uses draft instead of published)

    Returns:
        Result dict with status and outputs
    """
    import asyncio

    async def _run():
        from app.services.workflow import WorkflowOrchestrator

        run_uuid = UUID(run_id)
        workflow_uuid = UUID(workflow_id)
        user_uuid = UUID(user_id) if user_id else None
        team_uuid = UUID(team_id) if team_id else None

        try:
            orchestrator = WorkflowOrchestrator()
            result_run_id = await orchestrator.run_with_run_id(
                run_id=run_uuid,
                workflow_id=workflow_uuid,
                inputs=inputs,
                user_id=user_uuid,
                team_id=team_uuid,
                stream=True,
                is_debug=is_debug,
            )

            # Get final run status
            run = await WorkflowRun.filter(id=run_uuid).first()
            if run:
                return {
                    "status": "success",
                    "run_id": result_run_id,
                    "outputs": run.outputs,
                }
            else:
                return {"status": "error", "message": "Run not found after execution"}

        except Exception as e:
            logger.exception(f"Workflow execution error: {e}")

            # Update run status to failed
            run = await WorkflowRun.filter(id=run_uuid).first()
            if run:
                run.status = RunStatus.FAILED
                run.error_message = str(e)
                await run.save()

            # Re-raise for retry if applicable
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {"status": "error", "message": str(e)}

    # Run the async function
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run())


@shared_task(bind=True)
def cancel_workflow_task(self, run_id: str) -> dict:
    """
    Celery task to cancel a running workflow.

    Args:
        run_id: UUID string of the workflow run

    Returns:
        Result dict with cancellation status
    """
    import asyncio

    async def _cancel():
        from app.services.workflow import WorkflowOrchestrator

        run_uuid = UUID(run_id)

        try:
            orchestrator = WorkflowOrchestrator()
            cancelled = await orchestrator.cancel(str(run_uuid))

            return {"status": "success", "cancelled": cancelled}

        except Exception as e:
            logger.exception(f"Workflow cancellation error: {e}")
            return {"status": "error", "message": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_cancel())
