"""
Workflow orchestrator.

Main entry point for workflow execution. Coordinates execution plan,
node executors, and stream events.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import logging
import time


from app.models.workflow import (
    Workflow,
    WorkflowRun,
    RunStatus,
    NodeExecution,
    NodeStatus,
)
from app.models.notification import AutoNotificationType
from app.core.redis import get_redis
from app.core.i18n import t, get_default_language
from app.services.auto_notification import AutoNotificationService

from .context import ExecutionContext
from .errors import (
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
    NodeExecutionError,
    ExecutionTimeoutError,
    ExecutionCancelledError,
    translate_public_workflow_error,
)
from .executor import NodeExecutorRegistry, ExecutionResult
from .plan import ExecutionPlan
from .stream import StreamManager
from .retry import RetryableExecutor, get_retry_policy
from .cache import get_workflow_cache
from .metrics import get_metrics_collector
from .profiler import ExecutionProfiler

logger = logging.getLogger(__name__)

# Default node labels by type (for nodes without label in data)
NODE_TYPE_KEYS = {
    "user_input": "node_type_user_input",
    "trigger": "node_type_trigger",
    "llm": "node_type_llm",
    "answer": "node_type_answer",
    "condition": "node_type_condition",
    "question_classifier": "node_type_question_classifier",
    "code": "node_type_code",
    "http_request": "node_type_http_request",
    "tool": "node_type_tool",
    "sub_workflow": "node_type_sub_workflow",
    "variable_assignment": "node_type_variable_assignment",
    "variable_aggregator": "node_type_variable_aggregator",
    "parameter_extractor": "node_type_parameter_extractor",
    "iteration": "node_type_iteration",
    "agent": "node_type_agent",
    "end": "node_type_end",
}


async def get_node_type_label(node_type: str) -> str | None:
    """Get translated node type label."""
    key = NODE_TYPE_KEYS.get(node_type)
    if not key:
        return None
    default_lang = await get_default_language()
    return t(key, lang=default_lang)


class WorkflowOrchestrator:
    """
    Orchestrates workflow execution.

    Handles:
    - Workflow loading and validation
    - Execution plan generation
    - Node execution coordination
    - Stream event publishing
    - Error handling and cleanup

    Example:
        orchestrator = WorkflowOrchestrator()
        run_id = await orchestrator.run(
            workflow_id=uuid,
            inputs={"query": "Hello"},
            user_id=user_uuid,
        )
    """

    def __init__(
        self,
        timeout: int = 300,  # 5 minutes default
        max_nodes: int = 100,
        enable_retry: bool = True,
        enable_cache: bool = True,
        enable_metrics: bool = True,
        enable_profiling: bool = False,
    ):
        """
        Initialize orchestrator.

        Args:
            timeout: Maximum execution time in seconds
            max_nodes: Maximum number of nodes to execute
            enable_retry: Whether to enable retry for failed nodes
            enable_cache: Whether to enable caching
            enable_metrics: Whether to enable metrics collection
            enable_profiling: Whether to enable detailed profiling
        """
        self.timeout = timeout
        self.max_nodes = max_nodes
        self.enable_retry = enable_retry
        self.enable_cache = enable_cache
        self.enable_metrics = enable_metrics
        self.enable_profiling = enable_profiling

        # Get global instances
        self._cache = get_workflow_cache() if enable_cache else None
        self._metrics = get_metrics_collector() if enable_metrics else None

    async def run(
        self,
        workflow_id: UUID,
        inputs: dict[str, Any],
        user_id: UUID,
        team_id: UUID | None = None,
        stream: bool = True,
    ) -> str:
        """
        Run a workflow.

        Args:
            workflow_id: Workflow UUID
            inputs: Input variables
            user_id: User UUID triggering the run
            team_id: Optional team UUID
            stream: Whether to enable streaming

        Returns:
            Run ID (UUID string)

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotPublishedError: If workflow has no published version
        """
        start_time = time.time()

        # Load workflow (with cache)
        workflow = await self._load_workflow(workflow_id)

        # Get workflow definition (with cache)
        workflow_def = await self._get_workflow_definition(workflow)

        # Create run record
        run = await self._create_run(
            workflow=workflow,
            inputs=inputs,
            user_id=user_id,
            team_id=team_id,
        )

        # Record metrics - workflow start
        if self._metrics:
            await self._metrics.record_workflow_start(str(run.id), str(workflow_id))

        # Create profiler if enabled
        profiler = None
        if self.enable_profiling:
            profiler = ExecutionProfiler(
                run_id=str(run.id),
                workflow_id=str(workflow_id),
                workflow_name=workflow.name,
            )
            profiler.start()

        # Create execution context
        redis_client = await get_redis()
        context = await ExecutionContext.create(
            run_id=str(run.id),
            redis_client=redis_client,
            workflow_id=str(workflow_id),
            user_id=user_id,
        )
        await context.set_inputs(inputs)

        # Create stream manager
        stream_manager = StreamManager(str(run.id)) if stream else None

        node_count = 0

        try:
            # Build execution plan (with cache)
            plan = await self._get_execution_plan(workflow_id, workflow_def)

            # Validate plan
            errors = plan.validate()
            if errors:
                raise WorkflowValidationError(details={"errors": errors})

            # Publish workflow start event
            if stream_manager:
                await stream_manager.publish_workflow_start(
                    workflow_id=str(workflow_id),
                    workflow_name=workflow.name,
                    inputs=inputs,
                )

            # Execute workflow
            outputs, node_count = await self._execute(
                plan=plan,
                context=context,
                run=run,
                stream_manager=stream_manager,
                start_time=start_time,
                profiler=profiler,
            )

            # Update run record
            duration_ms = int((time.time() - start_time) * 1000)
            await self._complete_run(run, outputs, duration_ms)

            # Record metrics - workflow complete
            if self._metrics:
                await self._metrics.record_workflow_complete(
                    run_id=str(run.id),
                    workflow_id=str(workflow_id),
                    duration_ms=duration_ms,
                    status="success",
                    node_count=node_count,
                )

            # Finish profiling
            if profiler:
                profiler.finish()
                # Store profile in context for later retrieval
                await context.set_variable("_profile", profiler.to_dict())

            # Publish workflow complete event
            if stream_manager:
                await stream_manager.publish_workflow_complete(
                    outputs=outputs,
                    duration_ms=duration_ms,
                )

            return str(run.id)

        except Exception as e:
            # Handle errors
            duration_ms = int((time.time() - start_time) * 1000)
            public_error = translate_public_workflow_error(e)

            await self._fail_run(run, public_error, duration_ms)

            # Record metrics - workflow failed
            if self._metrics:
                await self._metrics.record_workflow_complete(
                    run_id=str(run.id),
                    workflow_id=str(workflow_id),
                    duration_ms=duration_ms,
                    status="failed",
                    node_count=node_count,
                    error=public_error,
                )

            # Finish profiling even on error
            if profiler:
                profiler.finish()

            if stream_manager:
                node_id = getattr(e, "node_id", None)
                await stream_manager.publish_workflow_error(
                    error=public_error,
                    node_id=node_id,
                )

            raise

    async def run_with_run_id(
        self,
        run_id: UUID,
        workflow_id: UUID,
        inputs: dict[str, Any],
        user_id: UUID,
        team_id: UUID | None = None,
        stream: bool = True,
        is_debug: bool = False,
    ) -> str:
        """
        Run a workflow with an existing run record.

        This is used for background execution where the run record
        is created before starting the actual execution.

        Args:
            run_id: Existing run UUID
            workflow_id: Workflow UUID
            inputs: Input variables
            user_id: User UUID triggering the run
            team_id: Optional team UUID
            stream: Whether to enable streaming
            is_debug: Whether this is a debug run (not used currently)

        Returns:
            Run ID (UUID string)
        """
        start_time = time.time()

        # Load workflow
        workflow = await self._load_workflow(workflow_id)

        # Get workflow definition
        workflow_def = await self._get_workflow_definition(workflow)

        # Load existing run record
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            raise WorkflowNotFoundError(
                t("workflow_run_not_found"), msg_key="workflow_run_not_found"
            )

        # Update run status to running
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        await run.save()

        # Record metrics - workflow start
        if self._metrics:
            await self._metrics.record_workflow_start(str(run.id), str(workflow_id))

        # Create profiler if enabled
        profiler = None
        if self.enable_profiling:
            profiler = ExecutionProfiler(
                run_id=str(run.id),
                workflow_id=str(workflow_id),
                workflow_name=workflow.name,
            )
            profiler.start()

        # Create execution context
        redis_client = await get_redis()
        context = await ExecutionContext.create(
            run_id=str(run.id),
            redis_client=redis_client,
            workflow_id=str(workflow_id),
            user_id=user_id,
        )
        await context.set_inputs(inputs)

        # Create stream manager
        stream_manager = StreamManager(str(run.id)) if stream else None

        node_count = 0

        try:
            # Build execution plan
            plan = await self._get_execution_plan(workflow_id, workflow_def)

            # Validate plan
            errors = plan.validate()
            if errors:
                raise WorkflowValidationError(details={"errors": errors})

            # Publish workflow start event
            if stream_manager:
                await stream_manager.publish_workflow_start(
                    workflow_id=str(workflow_id),
                    workflow_name=workflow.name,
                    inputs=inputs,
                )

            # Execute workflow
            outputs, node_count = await self._execute(
                plan=plan,
                context=context,
                run=run,
                stream_manager=stream_manager,
                start_time=start_time,
                profiler=profiler,
            )

            # Update run record
            duration_ms = int((time.time() - start_time) * 1000)
            await self._complete_run(run, outputs, duration_ms)

            # Record metrics
            if self._metrics:
                await self._metrics.record_workflow_complete(
                    run_id=str(run.id),
                    workflow_id=str(workflow_id),
                    duration_ms=duration_ms,
                    status="success",
                    node_count=node_count,
                )

            # Finish profiling
            if profiler:
                profiler.finish()
                await context.set_variable("_profile", profiler.to_dict())

            # Publish workflow complete event
            if stream_manager:
                await stream_manager.publish_workflow_complete(
                    outputs=outputs,
                    duration_ms=duration_ms,
                )

            return str(run.id)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            public_error = translate_public_workflow_error(e)

            await self._fail_run(run, public_error, duration_ms)

            if self._metrics:
                await self._metrics.record_workflow_complete(
                    run_id=str(run.id),
                    workflow_id=str(workflow_id),
                    duration_ms=duration_ms,
                    status="failed",
                    node_count=node_count,
                    error=public_error,
                )

            if profiler:
                profiler.finish()

            if stream_manager:
                node_id = getattr(e, "node_id", None)
                await stream_manager.publish_workflow_error(
                    error=public_error,
                    node_id=node_id,
                )

            raise

    async def _load_workflow(self, workflow_id: UUID) -> Workflow:
        """Load workflow from database."""
        workflow = await Workflow.filter(id=workflow_id).first()
        if not workflow:
            raise WorkflowNotFoundError(t("workflow_not_found"), msg_key="workflow_not_found")
        return workflow

    async def _get_workflow_definition(self, workflow: Workflow) -> dict:
        """Get workflow definition (with caching)."""
        if not workflow.definition:
            raise WorkflowNotPublishedError(workflow.name)

        # Try cache first
        if self._cache:
            cached = await self._cache.get_workflow(
                str(workflow.id),
                version=str(workflow.updated_at.timestamp())
                if workflow.updated_at
                else None,
            )
            if cached:
                return cached

            # Cache the definition
            await self._cache.set_workflow(
                str(workflow.id),
                workflow.definition,
                version=str(workflow.updated_at.timestamp())
                if workflow.updated_at
                else None,
            )

        return workflow.definition

    async def _get_execution_plan(
        self,
        workflow_id: UUID,
        workflow_def: dict,
    ) -> ExecutionPlan:
        """Get execution plan (with caching)."""
        # Build plan from workflow definition
        # Note: We always rebuild the plan from workflow_def since the cached
        # version (to_dict) only contains summary info, not full node data.
        # The caching benefit comes from caching workflow_def itself.
        plan = ExecutionPlan.from_workflow(workflow_def)

        return plan

    async def _create_run(
        self,
        workflow: Workflow,
        inputs: dict,
        user_id: UUID,
        team_id: UUID | None,
    ) -> WorkflowRun:
        """Create a new workflow run record."""
        run = await WorkflowRun.create(
            workflow_id=workflow.id,
            triggered_by_id=user_id,
            trigger_type=workflow.trigger_type,
            inputs=inputs,
            status=RunStatus.RUNNING,
        )
        logger.info(f"Created workflow run {run.id}")
        return run

    async def _complete_run(
        self,
        run: WorkflowRun,
        outputs: dict,
        duration_ms: int,
    ) -> None:
        """Mark run as completed."""
        # Update node execution statistics
        node_executions = await NodeExecution.filter(run_id=run.id).all()
        run.total_nodes = len(node_executions)
        run.executed_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.SUCCESS]
        )
        run.failed_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.FAILED]
        )
        run.skipped_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.SKIPPED]
        )

        run.status = RunStatus.SUCCESS
        run.outputs = outputs
        run.error_message = None
        run.error_node_id = None
        run.error_traceback = None
        run.total_duration_ms = duration_ms
        run.finished_at = datetime.now(timezone.utc)
        await run.save()
        logger.info(f"Completed workflow run {run.id}")

        # Update workflow statistics
        workflow = await Workflow.filter(id=run.workflow_id).first()
        if workflow:
            # Calculate total tokens from run
            total_tokens = 0
            if run.total_token_usage:
                total_tokens = (run.total_token_usage.get("prompt", 0) or 0) + (
                    run.total_token_usage.get("completion", 0) or 0
                )

            # Update workflow stats atomically
            from tortoise.expressions import F

            await Workflow.filter(id=workflow.id).update(
                run_count=F("run_count") + 1,
                success_count=F("success_count") + 1,
                total_tokens=F("total_tokens") + total_tokens,
            )

            # Update team stats atomically
            await Workflow.filter(id=workflow.id).update(
                team__total_tokens=F("team__total_tokens") + total_tokens
            )

            # Send workflow run success notification
            try:
                # Send to triggering user if available, otherwise to team
                if run.triggered_by_id:
                    await run.fetch_related("triggered_by")
                    user_locale = (
                        getattr(run.triggered_by, "locale", "en")
                        if run.triggered_by
                        else "en"
                    )
                    await AutoNotificationService.send_to_user(
                        notification_type=AutoNotificationType.WORKFLOW_RUN_SUCCESS,
                        user_id=run.triggered_by_id,
                        title=t("notify_workflow_run_success_title", lang=user_locale),
                        content=t(
                            "notify_workflow_run_success_content",
                            lang=user_locale,
                            workflow_name=workflow.name,
                            duration=duration_ms,
                            node_count=run.executed_nodes,
                        ),
                        data={
                            "workflow_id": str(workflow.id),
                            "workflow_name": workflow.name,
                            "run_id": str(run.id),
                            "duration_ms": duration_ms,
                            "node_count": run.executed_nodes,
                        },
                        link_url=f"/app/apps/workflow/{workflow.id}",
                    )
                else:
                    default_lang = await get_default_language()
                    await AutoNotificationService.send_to_team(
                        notification_type=AutoNotificationType.WORKFLOW_RUN_SUCCESS,
                        team_id=workflow.team_id,
                        title=t("notify_workflow_run_success_title", lang=default_lang),
                        content=t(
                            "notify_workflow_run_success_content",
                            lang=default_lang,
                            workflow_name=workflow.name,
                            duration=duration_ms,
                            node_count=run.executed_nodes,
                        ),
                        data={
                            "workflow_id": str(workflow.id),
                            "workflow_name": workflow.name,
                            "run_id": str(run.id),
                            "duration_ms": duration_ms,
                            "node_count": run.executed_nodes,
                        },
                        link_url=f"/app/apps/workflow/{workflow.id}",
                    )
            except Exception as e:
                logger.warning(f"Failed to send workflow run success notification: {e}")

    async def _fail_run(
        self,
        run: WorkflowRun,
        error: str,
        duration_ms: int,
    ) -> None:
        """Mark run as failed."""
        # Update node execution statistics
        node_executions = await NodeExecution.filter(run_id=run.id).all()
        run.total_nodes = len(node_executions)
        run.executed_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.SUCCESS]
        )
        run.failed_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.FAILED]
        )
        run.skipped_nodes = len(
            [n for n in node_executions if n.status == NodeStatus.SKIPPED]
        )

        run.status = RunStatus.FAILED
        run.error_message = error
        run.total_duration_ms = duration_ms
        run.finished_at = datetime.now(timezone.utc)
        await run.save()
        logger.error(f"Failed workflow run {run.id}: {error}")

        # Update workflow statistics
        workflow = await Workflow.filter(id=run.workflow_id).first()
        if workflow:
            # Calculate total tokens from run (even if failed, tokens were consumed)
            total_tokens = 0
            if run.total_token_usage:
                total_tokens = (run.total_token_usage.get("prompt", 0) or 0) + (
                    run.total_token_usage.get("completion", 0) or 0
                )

            # Update workflow stats atomically
            from tortoise.expressions import F

            await Workflow.filter(id=workflow.id).update(
                run_count=F("run_count") + 1,
                fail_count=F("fail_count") + 1,
                total_tokens=F("total_tokens") + total_tokens,
            )

            # Update team stats atomically
            await Workflow.filter(id=workflow.id).update(
                team__total_tokens=F("team__total_tokens") + total_tokens
            )

            # Send workflow run failed notification
            try:
                # Send to triggering user if available, otherwise to team
                if run.triggered_by_id:
                    await run.fetch_related("triggered_by")
                    user_locale = (
                        getattr(run.triggered_by, "locale", "en")
                        if run.triggered_by
                        else "en"
                    )
                    await AutoNotificationService.send_to_user(
                        notification_type=AutoNotificationType.WORKFLOW_RUN_FAILED,
                        user_id=run.triggered_by_id,
                        title=t("notify_workflow_run_failed_title", lang=user_locale),
                        content=t(
                            "notify_workflow_run_failed_content",
                            lang=user_locale,
                            workflow_name=workflow.name,
                            error=error[:200]
                            if error
                            else t("unknown_error"),  # Truncate long errors
                        ),
                        data={
                            "workflow_id": str(workflow.id),
                            "workflow_name": workflow.name,
                            "run_id": str(run.id),
                            "error": error,
                            "duration_ms": duration_ms,
                        },
                        link_url=f"/app/apps/workflow/{workflow.id}",
                    )
                else:
                    default_lang = await get_default_language()
                    await AutoNotificationService.send_to_team(
                        notification_type=AutoNotificationType.WORKFLOW_RUN_FAILED,
                        team_id=workflow.team_id,
                        title=t("notify_workflow_run_failed_title", lang=default_lang),
                        content=t(
                            "notify_workflow_run_failed_content",
                            lang=default_lang,
                            workflow_name=workflow.name,
                            error=error[:200]
                            if error
                            else t("unknown_error"),  # Truncate long errors
                        ),
                        data={
                            "workflow_id": str(workflow.id),
                            "workflow_name": workflow.name,
                            "run_id": str(run.id),
                            "error": error,
                            "duration_ms": duration_ms,
                        },
                        link_url=f"/app/apps/workflow/{workflow.id}",
                    )
            except Exception as e:
                logger.warning(f"Failed to send workflow run failed notification: {e}")

    async def _execute(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        run: WorkflowRun,
        stream_manager: StreamManager | None,
        start_time: float,
        profiler: ExecutionProfiler | None = None,
    ) -> tuple[dict[str, Any], int]:
        """
        Execute the workflow according to the plan.

        Args:
            plan: Execution plan
            context: Execution context
            run: Workflow run record
            stream_manager: Stream manager for events
            start_time: Execution start time
            profiler: Optional execution profiler

        Returns:
            Tuple of (final outputs dictionary, node count)
        """
        executed_nodes: set[str] = set()
        skipped_nodes: set[str] = set()
        node_count = 0
        final_outputs: dict[str, Any] = {}

        # Track iteration state for loop/iteration nodes

        # Execute stages sequentially
        for stage in plan.stages:
            # Check timeout
            if time.time() - start_time > self.timeout:
                raise ExecutionTimeoutError(self.timeout)

            # Check if cancelled
            status = await context.get_status()
            if status == "cancelled":
                raise ExecutionCancelledError()

            # Filter nodes that should be executed in this stage
            nodes_to_execute = []
            for node_id in stage.node_ids:
                # Skip if already executed or skipped
                if node_id in executed_nodes or node_id in skipped_nodes:
                    continue

                # Check if node should be skipped due to branch
                node = plan.get_node(node_id)
                if node:
                    # Check if any upstream node was skipped
                    if node.upstream & skipped_nodes:
                        # This node's branch was not taken
                        skipped_nodes.add(node_id)
                        if stream_manager:
                            node_label = (
                                node.node_data.get("data", {}).get("label")
                                or await get_node_type_label(node.node_type)
                                or node_id
                            )
                            await stream_manager.publish_node_skip(
                                node_id=node_id,
                                reason="upstream_skipped",
                                node_type=node.node_type,
                                node_label=node_label,
                            )
                        continue

                nodes_to_execute.append(node_id)

            # Execute nodes in this stage
            for node_id in nodes_to_execute:
                # Skip if already executed (may have been executed as part of iteration body)
                if node_id in executed_nodes:
                    continue

                node_count += 1
                if node_count > self.max_nodes:
                    raise NodeExecutionError(
                        message=f"Exceeded maximum node count: {self.max_nodes}",
                        node_id=node_id,
                        node_type=node.node_type if node else "unknown",
                    )

                # Execute single node
                result = await self._execute_node(
                    node_id=node_id,
                    plan=plan,
                    context=context,
                    run=run,
                    stream_manager=stream_manager,
                )

                # Check for iteration/loop nodes
                node = plan.get_node(node_id)
                if node and node.node_type in ("iteration", "loop"):
                    iteration_complete = result.outputs.get(
                        "_iteration_complete"
                    ) or result.outputs.get("_loop_complete", False)

                    # Get child nodes inside the iteration container (by parentId)
                    child_nodes = self._get_child_nodes(plan, node_id)

                    # Loop until iteration is complete
                    while not iteration_complete:
                        if child_nodes:
                            # Execute iteration body (child nodes)
                            await self._execute_iteration_body(
                                iteration_node_id=node_id,
                                downstream_nodes=child_nodes,
                                plan=plan,
                                context=context,
                                run=run,
                                stream_manager=stream_manager,
                                start_time=start_time,
                                executed_nodes=executed_nodes,
                                skipped_nodes=skipped_nodes,
                            )

                        # Re-execute iteration node to get next item
                        result = await self._execute_node(
                            node_id=node_id,
                            plan=plan,
                            context=context,
                            run=run,
                            stream_manager=stream_manager,
                        )
                        iteration_complete = result.outputs.get(
                            "_iteration_complete"
                        ) or result.outputs.get("_loop_complete", False)

                        # Break before executing body if iteration is complete
                        if iteration_complete:
                            break

                    # Mark child nodes as executed to prevent re-execution in stage loop
                    for child_id in child_nodes:
                        executed_nodes.add(child_id)

                executed_nodes.add(node_id)

                # Handle branching
                if result.next_handles:
                    # Condition node - mark non-taken branches for skipping
                    if node:
                        all_handles = set(node.handle_map.keys())
                        taken_handles = set(result.next_handles)
                        skipped_handles = all_handles - taken_handles

                        logger.info(
                            f"Branching node {node_id}: all_handles={all_handles}, taken={taken_handles}, skipped={skipped_handles}"
                        )
                        logger.info(f"Handle map: {node.handle_map}")

                        for handle in skipped_handles:
                            # Mark all downstream nodes of skipped branches
                            downstream = node.handle_map.get(handle, [])
                            logger.info(
                                f"Skipping handle {handle}, downstream nodes: {downstream}"
                            )
                            for downstream_id in downstream:
                                skipped_nodes.add(downstream_id)
                                # Also add all nodes reachable from this
                                all_downstream = plan.get_all_downstream(downstream_id)
                                skipped_nodes.update(all_downstream)
                                logger.info(
                                    f"Skipping node {downstream_id} and all downstream: {all_downstream}"
                                )
                                if stream_manager:
                                    downstream_node = plan.get_node(downstream_id)
                                    if downstream_node:
                                        downstream_label = (
                                            downstream_node.node_data.get(
                                                "data", {}
                                            ).get("label")
                                            or await get_node_type_label(
                                                downstream_node.node_type
                                            )
                                            or downstream_id
                                        )
                                    else:
                                        downstream_label = downstream_id
                                    await stream_manager.publish_node_skip(
                                        node_id=downstream_id,
                                        reason="branch_not_taken",
                                        node_type=downstream_node.node_type
                                        if downstream_node
                                        else None,
                                        node_label=downstream_label,
                                    )

                # Collect final outputs from answer nodes
                if node and node.node_type == "answer":
                    final_outputs.update(result.outputs)

        return final_outputs, node_count

    async def _execute_iteration_body(
        self,
        iteration_node_id: str,
        downstream_nodes: list[str],
        plan: ExecutionPlan,
        context: ExecutionContext,
        run: WorkflowRun,
        stream_manager: StreamManager | None,
        start_time: float,
        executed_nodes: set,
        skipped_nodes: set,
    ) -> None:
        """
        Execute the body of an iteration/loop.

        Executes all child nodes inside the iteration container.
        """
        # Use the child nodes directly (already sorted by execution order)
        ordered_body_nodes = downstream_nodes

        logger.info(f"Executing iteration body: {ordered_body_nodes}")

        for node_id in ordered_body_nodes:
            # Check timeout
            if time.time() - start_time > self.timeout:
                raise ExecutionTimeoutError(self.timeout)

            # Check if cancelled
            status = await context.get_status()
            if status == "cancelled":
                raise ExecutionCancelledError()

            # Execute node
            result = await self._execute_node(
                node_id=node_id,
                plan=plan,
                context=context,
                run=run,
                stream_manager=stream_manager,
            )

            logger.info(f"Iteration body node {node_id} result: {result.outputs}")

    async def _execute_node(
        self,
        node_id: str,
        plan: ExecutionPlan,
        context: ExecutionContext,
        run: WorkflowRun,
        stream_manager: StreamManager | None,
    ) -> ExecutionResult:
        """
        Execute a single node.

        Args:
            node_id: Node ID to execute
            plan: Execution plan
            context: Execution context
            run: Workflow run record
            stream_manager: Stream manager for events

        Returns:
            Execution result
        """
        node_info = plan.get_node(node_id)
        if not node_info:
            raise NodeExecutionError(
                message=t("node_not_found_in_execution_plan"),
                node_id=node_id,
                node_type="unknown",
            )

        node_type = node_info.node_type
        node_data = node_info.node_data
        # Get label from node_data.data.label (React Flow node structure)
        # Fall back to default label by type, then node_id
        node_inner_data = node_data.get("data", {})
        node_label = (
            node_inner_data.get("label")
            or await get_node_type_label(node_type)
            or node_id
        )

        logger.debug(
            f"Execute node {node_id}: type={node_type}, label={node_label}, data_keys={list(node_inner_data.keys())}"
        )

        # Answer nodes are always streaming (real or pseudo)
        is_streaming_answer = node_type == "answer"

        # Publish node start
        if stream_manager:
            await stream_manager.publish_node_start(
                node_id=node_id,
                node_type=node_type,
                node_label=node_label,
                is_streaming=is_streaming_answer,
            )

        # Create NodeExecution record
        execution_order = len(await NodeExecution.filter(run_id=run.id).all())
        node_execution = await NodeExecution.create(
            run_id=run.id,
            node_id=node_id,
            node_type=node_type,
            node_name=node_label,
            execution_order=execution_order,
            status=NodeStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            config_snapshot=node_inner_data.get("config"),
        )

        start_time = time.time()

        try:
            # Get executor
            executor = NodeExecutorRegistry.get(node_type)

            # Wrap with retry if enabled
            if self.enable_retry:
                policy = get_retry_policy(node_type)
                retryable = RetryableExecutor(executor, policy)
                result = await retryable.execute(
                    node=node_data,
                    context=context,
                    run=run,
                )
            else:
                # Execute directly without retry
                result = await executor.execute(
                    node=node_data,
                    context=context,
                    run=run,
                )

            if not result.success:
                raise NodeExecutionError(
                    node_id=node_id,
                    node_type=node_type,
                    message=result.error or "Unknown error",
                )

            # Store outputs in context
            await context.set_node_outputs(node_id, result.outputs)

            # Publish node complete (filter out lazy results for serialization)
            duration_ms = int((time.time() - start_time) * 1000)

            # Filter outputs for database storage - remove non-serializable objects
            from .lazy_stream import LazyStreamResult

            serializable_outputs = {}
            for k, v in result.outputs.items():
                if isinstance(v, LazyStreamResult):
                    serializable_outputs[k] = "__LAZY_STREAM__"
                elif isinstance(v, ExecutionContext):
                    serializable_outputs[k] = "__EXECUTION_CONTEXT__"
                else:
                    # Try to serialize, skip if fails
                    try:
                        import json

                        json.dumps(v)
                        serializable_outputs[k] = v
                    except (TypeError, ValueError):
                        serializable_outputs[k] = (
                            f"__NON_SERIALIZABLE_{type(v).__name__}__"
                        )

            # Update NodeExecution record - success
            node_execution.status = NodeStatus.SUCCESS
            node_execution.finished_at = datetime.now(timezone.utc)
            node_execution.execution_duration_ms = duration_ms
            node_execution.outputs = serializable_outputs
            await node_execution.save()

            if stream_manager:
                from .lazy_stream import LazyStreamResult

                # Filter outputs for serialization - lazy results are placeholders
                serializable_outputs = {
                    k: (v if not isinstance(v, LazyStreamResult) else "__LAZY_STREAM__")
                    for k, v in result.outputs.items()
                }
                await stream_manager.publish_node_complete(
                    node_id=node_id,
                    outputs=serializable_outputs,
                    duration_ms=duration_ms,
                    node_type=node_type,
                    is_streaming=is_streaming_answer,
                )

            return result

        except NodeExecutionError as e:
            # Update NodeExecution record - failed
            duration_ms = int((time.time() - start_time) * 1000)
            public_error = translate_public_workflow_error(e)
            node_execution.status = NodeStatus.FAILED
            node_execution.finished_at = datetime.now(timezone.utc)
            node_execution.execution_duration_ms = duration_ms
            node_execution.error_message = public_error
            node_execution.error_type = type(e).__name__
            await node_execution.save()
            if stream_manager:
                await stream_manager.publish_node_error(
                    node_id=node_id,
                    error=public_error,
                )
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                message=public_error,
            ) from e
        except Exception as e:
            # Update NodeExecution record - failed
            duration_ms = int((time.time() - start_time) * 1000)
            public_error = translate_public_workflow_error(e)
            node_execution.status = NodeStatus.FAILED
            node_execution.finished_at = datetime.now(timezone.utc)
            node_execution.execution_duration_ms = duration_ms
            node_execution.error_message = public_error
            node_execution.error_type = type(e).__name__
            await node_execution.save()

            if stream_manager:
                await stream_manager.publish_node_error(
                    node_id=node_id,
                    error=public_error,
                )
            raise NodeExecutionError(
                node_id=node_id,
                node_type=node_type,
                message=public_error,
            ) from e

    async def cancel(self, run_id: str) -> bool:
        """
        Cancel a running workflow.

        Args:
            run_id: Run ID to cancel

        Returns:
            True if cancelled, False if not found or already completed
        """
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            return False

        if run.status != RunStatus.RUNNING:
            return False

        run.status = RunStatus.CANCELLED
        run.finished_at = datetime.now(timezone.utc)
        await run.save()

        # Set cancelled status in context
        redis_client = await get_redis()
        context = await ExecutionContext.load(run_id, redis_client)
        await context.set_status("cancelled")

        # Publish cancel event
        stream_manager = StreamManager(run_id)
        await stream_manager.publish_workflow_error(error=t("workflow_run_cancelled"))

        logger.info(f"Cancelled workflow run {run_id}")
        return True

    async def get_run_status(self, run_id: str) -> dict | None:
        """
        Get the status of a workflow run.

        Args:
            run_id: Run ID

        Returns:
            Status dictionary or None if not found
        """
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            return None

        return {
            "id": str(run.id),
            "workflow_id": str(run.workflow_id),
            "status": str(run.status),
            "inputs": run.inputs,
            "outputs": run.outputs,
            "error": run.error_message,
            "duration_ms": run.total_duration_ms,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }

    def _get_child_nodes(self, plan: ExecutionPlan, parent_id: str) -> list[str]:
        """
        Get child nodes inside a container (iteration/loop) by parentId.

        Args:
            plan: Execution plan
            parent_id: Parent container node ID

        Returns:
            List of child node IDs in execution order
        """
        child_nodes = []
        for node_id, node_info in plan.nodes.items():
            node_data = node_info.node_data
            # Check parentId in node data
            if node_data.get("parentId") == parent_id:
                child_nodes.append(node_id)

        # Sort by execution order
        execution_order = plan.get_execution_order()
        return [n for n in execution_order if n in child_nodes]
