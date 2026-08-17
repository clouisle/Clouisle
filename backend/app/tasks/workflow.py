"""
Celery tasks for workflow execution.
"""

import logging
from uuid import UUID

from celery import shared_task

from app.models.workflow import WorkflowRun, RunStatus
from app.core.i18n import t, get_default_language
from app.services.workflow.errors import translate_public_workflow_error

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def run_workflow_task(
    self,
    run_id: str,
    workflow_id: str,
    inputs: dict,
    user_id: str | None,
    team_id: str | None = None,
    is_debug: bool = False,
    base_url: str | None = None,
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
                public_base_url=base_url,
            )

            # Get final run status
            run = await WorkflowRun.filter(id=run_uuid).first()
            if run:
                return {
                    "status": "waiting"
                    if run.status == RunStatus.WAITING
                    else "success",
                    "run_id": result_run_id,
                    "outputs": run.outputs,
                }
            else:
                default_lang = await get_default_language()
                return {
                    "status": "error",
                    "message": t(
                        "workflow_run_not_found_after_execution", lang=default_lang
                    ),
                }

        except Exception as e:
            logger.exception(f"Workflow execution error: {e}")
            public_error = translate_public_workflow_error(e)

            # Update run status to failed
            run = await WorkflowRun.filter(id=run_uuid).first()
            if run:
                run.status = RunStatus.FAILED
                run.error_message = public_error
                await run.save()

            return {"status": "error", "message": public_error}

    # Run the async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_run())


@shared_task(bind=True, max_retries=0)
def resume_workflow_task(self, run_id: str) -> dict:
    """
    Celery task to resume a workflow paused at a pause node.

    Re-runs the workflow with the resume flag so already-completed nodes are
    skipped and the pause node re-executes to emit the submitted values.

    Args:
        run_id: UUID string of the workflow run

    Returns:
        Result dict with status and outputs
    """
    import asyncio

    async def _resume():
        from app.services.workflow import WorkflowOrchestrator

        run_uuid = UUID(run_id)

        try:
            run = await WorkflowRun.filter(id=run_uuid).first()
            if not run:
                default_lang = await get_default_language()
                return {
                    "status": "error",
                    "message": t(
                        "workflow_run_not_found_after_execution", lang=default_lang
                    ),
                }
            if not run.workflow_id:
                default_lang = await get_default_language()
                return {
                    "status": "error",
                    "message": t("workflow_not_found", lang=default_lang),
                }
            claimed = await WorkflowRun.filter(
                id=run_uuid,
                status=RunStatus.WAITING,
            ).update(status=RunStatus.RUNNING)
            if claimed != 1:
                default_lang = await get_default_language()
                return {
                    "status": "error",
                    "message": t("workflow_run_not_waiting", lang=default_lang),
                }
            run.status = RunStatus.RUNNING
            orchestrator = WorkflowOrchestrator()
            result_run_id = await orchestrator.run_with_run_id(
                run_id=run_uuid,
                workflow_id=run.workflow_id,
                inputs=run.inputs,
                user_id=run.triggered_by_id,
                team_id=None,
                stream=True,
                is_debug=run.is_debug,
                resume=True,
            )

            run = await WorkflowRun.filter(id=run_uuid).first()
            if run:
                # A multi-pause workflow parks again after this resume pass.
                if run.status == RunStatus.WAITING:
                    return {"status": "waiting", "run_id": result_run_id}
                return {
                    "status": "success",
                    "run_id": result_run_id,
                    "outputs": run.outputs,
                }
            default_lang = await get_default_language()
            return {
                "status": "error",
                "message": t(
                    "workflow_run_not_found_after_execution", lang=default_lang
                ),
            }

        except Exception as e:
            logger.exception(f"Workflow resume error: {e}")
            public_error = translate_public_workflow_error(e)

            run = await WorkflowRun.filter(id=run_uuid).first()
            if run and run.status == RunStatus.RUNNING:
                run.status = RunStatus.FAILED
                run.error_message = public_error
                await run.save()

            return {"status": "error", "message": public_error}

    # Run the async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_resume())


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
            return {"status": "error", "message": translate_public_workflow_error(e)}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_cancel())
