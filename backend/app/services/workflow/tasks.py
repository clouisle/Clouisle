"""
Celery tasks for distributed workflow execution.

Provides asynchronous task execution for workflows and nodes.
"""

from celery import shared_task, group
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="workflow.execute",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def execute_workflow_task(
    self,
    workflow_id: str,
    inputs: dict,
    user_id: str,
    team_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """
    Execute a workflow asynchronously.

    This is the main entry point for async workflow execution.

    Args:
        workflow_id: Workflow UUID string
        inputs: Input variables
        user_id: User UUID string
        team_id: Team UUID string (optional)
        run_id: Existing run ID to resume (optional)

    Returns:
        Execution result dictionary
    """
    import asyncio
    from app.services.workflow import WorkflowOrchestrator

    async def run():
        orchestrator = WorkflowOrchestrator()
        result_run_id = await orchestrator.run(
            workflow_id=UUID(workflow_id),
            inputs=inputs,
            user_id=UUID(user_id),
            team_id=UUID(team_id) if team_id else None,
            stream=True,
        )
        return {"run_id": result_run_id, "status": "completed"}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(run())
    except Exception as e:
        logger.exception(f"Workflow execution failed: {e}")
        return {"run_id": run_id, "status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="workflow.execute_node",
    max_retries=2,
    default_retry_delay=30,
)
def execute_node_task(
    self,
    run_id: str,
    node_id: str,
    node_type: str,
    node_data: dict,
) -> dict:
    """
    Execute a single node asynchronously.

    Used for parallel node execution within a workflow.

    Args:
        run_id: Workflow run UUID string
        node_id: Node ID
        node_type: Node type
        node_data: Node configuration data

    Returns:
        Node execution result
    """
    import asyncio
    from app.services.workflow import ExecutionContext, NodeExecutorRegistry
    from app.models.workflow import WorkflowRun

    async def run():
        # Load context
        context = await ExecutionContext.load(run_id)

        # Check if cancelled
        status = await context.get_status()
        if status == "cancelled":
            return {"node_id": node_id, "status": "cancelled"}

        # Get executor
        executor = NodeExecutorRegistry.get(node_type)

        # Load run
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            return {"node_id": node_id, "status": "error", "error": "Run not found"}

        # Execute
        result = await executor.execute(
            node={"id": node_id, "data": node_data},
            context=context,
            run=run,
        )

        # Store outputs
        if result.success:
            await context.set_node_outputs(node_id, result.outputs)

        return {
            "node_id": node_id,
            "status": "success" if result.success else "error",
            "outputs": result.outputs,
            "error": result.error,
            "next_handles": result.next_handles,
        }

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(run())
    except Exception as e:
        logger.exception(f"Node execution failed: {e}")
        # Retry on failure
        raise self.retry(exc=e)


@shared_task(name="workflow.execute_stage")
def execute_stage_task(
    run_id: str,
    stage_index: int,
    node_ids: list[str],
    nodes_data: dict[str, dict],
) -> dict:
    """
    Execute a stage of parallel nodes.

    Args:
        run_id: Workflow run ID
        stage_index: Stage index
        node_ids: List of node IDs in this stage
        nodes_data: Map of node_id to node data

    Returns:
        Stage execution result
    """
    # Create parallel task group
    tasks = []
    for node_id in node_ids:
        node_data = nodes_data.get(node_id, {})
        node_type = node_data.get("data", {}).get("type", "unknown")
        tasks.append(execute_node_task.s(run_id, node_id, node_type, node_data))

    # Execute in parallel
    job = group(tasks)
    result = job.apply_async()

    # Wait for results
    results = result.get(timeout=300)

    return {
        "stage_index": stage_index,
        "results": results,
    }


@shared_task(name="workflow.cancel")
def cancel_workflow_task(run_id: str) -> dict:
    """
    Cancel a running workflow.

    Args:
        run_id: Workflow run ID

    Returns:
        Cancellation result
    """
    import asyncio
    from app.services.workflow import WorkflowOrchestrator

    async def cancel():
        orchestrator = WorkflowOrchestrator()
        cancelled = await orchestrator.cancel(run_id)
        return {"run_id": run_id, "cancelled": cancelled}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(cancel())


@shared_task(name="workflow.cleanup")
def cleanup_workflow_task(run_id: str, ttl: int = 3600) -> dict:
    """
    Clean up workflow execution state from Redis.

    Args:
        run_id: Workflow run ID
        ttl: Time to live before cleanup (seconds)

    Returns:
        Cleanup result
    """
    import asyncio
    from app.services.workflow import ExecutionContext

    async def cleanup():
        context = await ExecutionContext.load(run_id)
        await context.set_ttl(ttl)
        return {"run_id": run_id, "cleaned": True}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(cleanup())


# ============================================================================
# Scheduled Tasks
# ============================================================================


@shared_task(name="workflow.check_scheduled")
def check_scheduled_workflows() -> dict:
    """
    Check and trigger scheduled workflows.

    This task should be run periodically (e.g., every minute).

    Returns:
        Number of workflows triggered
    """
    import asyncio
    from datetime import datetime
    from croniter import croniter
    from app.models.workflow import Workflow, WorkflowStatus, TriggerType

    async def check():
        now = datetime.utcnow()
        triggered = 0

        # Find workflows with cron triggers
        workflows = await Workflow.filter(
            status=WorkflowStatus.PUBLISHED,
            trigger_type=TriggerType.CRON,
        ).all()

        for workflow in workflows:
            cron_expr = workflow.trigger_config.get("cron")
            if not cron_expr:
                continue

            try:
                cron = croniter(cron_expr, now)
                prev_time = cron.get_prev(datetime)

                # Check if this minute matches cron
                if (now - prev_time).total_seconds() < 60:
                    # Trigger workflow
                    execute_workflow_task.delay(
                        workflow_id=str(workflow.id),
                        inputs={},
                        user_id=str(workflow.created_by_id),
                        team_id=str(workflow.team_id),
                    )
                    triggered += 1
                    logger.info(f"Triggered scheduled workflow: {workflow.name}")

            except Exception as e:
                logger.error(f"Error checking workflow {workflow.id}: {e}")

        return {"triggered": triggered}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(check())


@shared_task(name="workflow.cleanup_old_runs")
def cleanup_old_runs(days: int = 30) -> dict:
    """
    Clean up old workflow runs.

    Args:
        days: Delete runs older than this many days

    Returns:
        Number of runs deleted
    """
    import asyncio
    from datetime import datetime, timedelta
    from app.models.workflow import WorkflowRun

    async def cleanup():
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = await WorkflowRun.filter(created_at__lt=cutoff).delete()
        return {"deleted": deleted}

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(cleanup())
