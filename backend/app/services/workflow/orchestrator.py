"""
Workflow orchestrator.

Main entry point for workflow execution. Coordinates execution plan,
node executors, and stream events.
"""

from datetime import datetime, timezone
from .types import WorkflowValue
from uuid import UUID
import logging
import time


from app.models.workflow import (
    Workflow,
    WorkflowRun,
    RunStatus,
    WorkflowPauseRequest,
    PauseRequestStatus,
    NodeExecution,
    NodeStatus,
    WorkflowVersion,
)
from app.models.user import Team
from app.models.notification import AutoNotificationType
from app.core.redis import get_redis
from app.core.i18n import t, get_default_language
from app.services.auto_notification import AutoNotificationService

from .context import ExecutionContext
from .pause_approvers import remove_pause_pending_notifications
from .errors import (
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
    NodeExecutionError,
    NodeWaitingError,
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
    "pause": "node_type_pause",
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
        inputs: dict[str, WorkflowValue],
        user_id: UUID,
        team_id: UUID | None = None,
        stream: bool = True,
        public_base_url: str | None = None,
    ) -> str:
        """
        Run a workflow.

        Args:
            workflow_id: Workflow UUID
            inputs: Input variables
            user_id: User UUID triggering the run
            team_id: Optional team UUID
            stream: Whether to enable streaming
            public_base_url: Public base URL of the triggering request, used as a
                fallback for absolutizing upload URLs when PUBLIC_API_URL is unset

        Returns:
            Run ID (UUID string)

        Raises:
            WorkflowNotFoundError: If workflow doesn't exist
            WorkflowNotPublishedError: If workflow has no published version
        """
        start_time = time.time()

        # Load workflow (with cache)
        workflow = await self._load_workflow(workflow_id)

        # Get workflow definition from the latest published snapshot.
        workflow_def = await self._get_workflow_definition(workflow, is_debug=False)

        # Create run record
        run = await self._create_run(
            workflow=workflow,
            inputs=inputs,
            user_id=user_id,
            team_id=team_id,
        )
        run.context_snapshot = {
            "workflow_definition": workflow_def,
            **({"public_base_url": public_base_url} if public_base_url else {}),
        }
        await run.save(update_fields=["context_snapshot"])

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
            public_base_url=public_base_url,
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
                logger.error(
                    f"Workflow {workflow_id} validation failed with {len(errors)} error(s): {errors}"
                )
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

        except NodeWaitingError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            run.status = RunStatus.WAITING
            run.total_duration_ms = duration_ms
            await run.save()
            if stream_manager:
                await stream_manager.publish_workflow_waiting(e.node_id)
            await context.set_ttl()
            logger.info(
                "Workflow run %s paused awaiting input at node %s",
                run.id,
                e.node_id,
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
        inputs: dict[str, WorkflowValue],
        user_id: UUID,
        team_id: UUID | None = None,
        stream: bool = True,
        is_debug: bool = False,
        public_base_url: str | None = None,
        resume: bool = False,
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
            is_debug: Whether this is a debug run (uses the live draft)

        Returns:
            Run ID (UUID string)
        """
        start_time = time.time()

        # Load workflow
        workflow = await self._load_workflow(workflow_id)

        # Load existing run record
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            raise WorkflowNotFoundError(
                t("workflow_run_not_found"), msg_key="workflow_run_not_found"
            )

        # A resumed run must execute the exact definition that originally
        # paused, not whichever draft/published version happens to be current
        # when a human submits values. Persist that definition in the existing
        # context snapshot on the first pass and reuse it on resume.
        context_snapshot = dict(getattr(run, "context_snapshot", {}) or {})
        if resume:
            saved_definition = context_snapshot.get("workflow_definition")
            if not isinstance(saved_definition, dict):
                raise WorkflowValidationError(
                    details={"reason": "workflow_pause_snapshot_missing"}
                )
            workflow_def = saved_definition
            saved_base_url = context_snapshot.get("public_base_url")
            if not public_base_url and isinstance(saved_base_url, str):
                public_base_url = saved_base_url
        else:
            # The persisted run mode is authoritative, so callers cannot make
            # a normal run execute the live draft inconsistently.
            workflow_def = await self._get_workflow_definition(
                workflow, is_debug=run.is_debug
            )
            context_snapshot["workflow_definition"] = workflow_def
            if public_base_url:
                context_snapshot["public_base_url"] = public_base_url
            run.context_snapshot = context_snapshot

        # Update run status to running
        run.status = RunStatus.RUNNING
        if not resume:
            # Keep the original start time across resume passes so the run
            # history shows the true start, not the resume moment.
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
            public_base_url=public_base_url,
        )
        await context.set_inputs(inputs)

        # Create stream manager
        stream_manager = StreamManager(str(run.id)) if stream else None
        if stream_manager and resume:
            # Continue pass-1 sequences so the replay filter does not drop the
            # resumed pass for clients reconnecting with from_sequence.
            await stream_manager.seed_sequence()

        node_count = 0

        try:
            # Build execution plan
            plan = await self._get_execution_plan(workflow_id, workflow_def)

            # Validate plan
            errors = plan.validate()
            if errors:
                logger.error(
                    f"Workflow {workflow_id} validation failed with {len(errors)} error(s): {errors}"
                )
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
                resume=resume,
            )

            # Update run record
            duration_ms = int((time.time() - start_time) * 1000)
            if resume:
                # Carry the pre-pause execution time forward instead of
                # reporting only this resume pass.
                duration_ms += run.total_duration_ms or 0
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

        except NodeWaitingError as e:
            # Pause node: the run is deliberately parked (RunStatus.WAITING,
            # node already persisted as WAITING, pause request created by the
            # executor). Keep the Redis context alive while paused so the
            # resume task can continue without rebuilding state, then exit
            # cleanly instead of failing the run.
            duration_ms = int((time.time() - start_time) * 1000)
            if resume:
                duration_ms += run.total_duration_ms or 0
            run.status = RunStatus.WAITING
            run.total_duration_ms = duration_ms
            await run.save()
            if stream_manager:
                await stream_manager.publish_workflow_waiting(e.node_id)
            await context.set_ttl()
            logger.info(
                "Workflow run %s paused awaiting input at node %s",
                run.id,
                e.node_id,
            )
            return str(run.id)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            if resume:
                duration_ms += run.total_duration_ms or 0
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
            raise WorkflowNotFoundError(
                t("workflow_not_found"), msg_key="workflow_not_found"
            )
        return workflow

    async def _get_workflow_definition(
        self, workflow: Workflow, *, is_debug: bool = True
    ) -> dict:
        """Get the live draft for debug runs or the latest published snapshot."""
        if is_debug:
            if not workflow.definition:
                raise WorkflowNotPublishedError(workflow.name)

            # Try cache first for the live draft used by the editor debug drawer.
            if self._cache:
                cached = await self._cache.get_workflow(
                    str(workflow.id),
                    version=str(workflow.updated_at.timestamp())
                    if workflow.updated_at
                    else None,
                )
                if cached:
                    return cached

                await self._cache.set_workflow(
                    str(workflow.id),
                    workflow.definition,
                    version=str(workflow.updated_at.timestamp())
                    if workflow.updated_at
                    else None,
                )

            return workflow.definition

        # Published runs must execute an immutable version snapshot, never the
        # mutable workflow definition.  This also prevents a published workflow
        # with an edited draft from silently running the draft.
        if not workflow.definition:
            raise WorkflowNotPublishedError(workflow.name)

        published_version = (
            await WorkflowVersion.filter(workflow_id=workflow.id)
            .order_by("-version")
            .first()
        )
        if not published_version or not published_version.definition:
            raise WorkflowNotPublishedError(workflow.name)

        version_key = f"published:{published_version.version}"
        if self._cache:
            cached = await self._cache.get_workflow(
                str(workflow.id), version=version_key
            )
            if cached:
                return cached

            await self._cache.set_workflow(
                str(workflow.id),
                published_version.definition,
                version=version_key,
            )

        return published_version.definition

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

        # Debug runs feed the per-node TypeSpec inference so the editor can
        # surface field-level autocomplete after a single trial. Production
        # runs intentionally skip this so live traffic shape doesn't drift
        # the editor schema.
        if run.is_debug and run.workflow_id:
            from .schema_inference import merge_run_into_workflow

            await merge_run_into_workflow(run.workflow_id, node_executions)

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
            if workflow.team_id and total_tokens > 0:
                await Team.filter(id=workflow.team_id).update(
                    total_tokens=F("total_tokens") + total_tokens
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
            if workflow.team_id and total_tokens > 0:
                await Team.filter(id=workflow.team_id).update(
                    total_tokens=F("total_tokens") + total_tokens
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

    async def _persist_skipped_node(
        self,
        run: "WorkflowRun",
        node_id: str,
        node_type: str | None,
        node_label: str,
    ) -> None:
        """Persist a branch-pruned node so a later resume pass skips it too.

        The resume path rebuilds its skipped set from SKIPPED NodeExecution
        records, so every in-memory skip must be durable or the pruned branch
        re-executes after the human resumes the run.
        """
        existing = await NodeExecution.filter(run_id=run.id, node_id=node_id).first()
        if existing:
            return
        execution_order = len(await NodeExecution.filter(run_id=run.id).all())
        await NodeExecution.create(
            run_id=run.id,
            node_id=node_id,
            node_type=node_type or "",
            node_name=node_label,
            execution_order=execution_order,
            status=NodeStatus.SKIPPED,
            started_at=datetime.now(timezone.utc),
        )

    async def _execute(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        run: WorkflowRun,
        stream_manager: StreamManager | None,
        start_time: float,
        profiler: ExecutionProfiler | None = None,
        resume: bool = False,
    ) -> tuple[dict[str, WorkflowValue], int]:
        """
        Execute the workflow according to the plan.

        Args:
            plan: Execution plan
            context: Execution context
            run: Workflow run record
            stream_manager: Stream manager for events
            start_time: Execution start time
            profiler: Optional execution profiler
            resume: When True, skip nodes already completed in a prior pass
                (resume after a pause node submission)

        Returns:
            Tuple of (final outputs dictionary, node count)
        """
        executed_nodes: set[str] = set()
        skipped_nodes: set[str] = set()
        node_count = 0
        final_outputs: dict[str, WorkflowValue] = {}

        # Resume after a pause: rebuild the executed/skipped sets from the
        # persisted node executions so only unpaused work re-runs. The paused
        # node itself is NOT in the success set, so it re-executes and emits
        # the submitted values.
        if resume:
            prior = await NodeExecution.filter(run_id=run.id).all()
            executed_nodes = {
                n.node_id for n in prior if n.status == NodeStatus.SUCCESS
            }
            skipped_nodes = {n.node_id for n in prior if n.status == NodeStatus.SKIPPED}
            for execution in prior:
                if (
                    execution.status == NodeStatus.SUCCESS
                    and execution.node_type == "answer"
                ):
                    final_outputs.update(execution.outputs or {})
            logger.info(
                "Resuming run %s with %d executed, %d skipped nodes",
                run.id,
                len(executed_nodes),
                len(skipped_nodes),
            )

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

                # Container children are executed exclusively by their iteration/loop
                # parent. React Flow edges still place them in the global plan; running
                # them here would bypass the per-round variable scope.
                node = plan.get_node(node_id)
                node_data = getattr(node, "node_data", None) if node else None
                if isinstance(node_data, dict) and node_data.get("parentId"):
                    continue

                # Check if node should be skipped due to branch
                if node:
                    # Check if any upstream node was skipped
                    if node.upstream & skipped_nodes:
                        # This node's branch was not taken
                        skipped_nodes.add(node_id)
                        node_label = (
                            node.node_data.get("data", {}).get("label")
                            or await get_node_type_label(node.node_type)
                            or node_id
                        )
                        await self._persist_skipped_node(
                            run, node_id, node.node_type, node_label
                        )
                        if stream_manager:
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
                # Preserve the normal call shape for existing execution paths;
                # only resume runs need to inspect a prior WAITING record.
                if resume:
                    result = await self._execute_node(
                        node_id=node_id,
                        plan=plan,
                        context=context,
                        run=run,
                        stream_manager=stream_manager,
                        resume=True,
                    )
                else:
                    result = await self._execute_node(
                        node_id=node_id,
                        plan=plan,
                        context=context,
                        run=run,
                        stream_manager=stream_manager,
                    )

                # Pause node: stop execution, persist WAITING state upstream
                if getattr(result, "waiting", False):
                    raise NodeWaitingError(node_id=node_id)

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

                        # Re-execute iteration node to get next item.
                        if resume:
                            result = await self._execute_node(
                                node_id=node_id,
                                plan=plan,
                                context=context,
                                run=run,
                                stream_manager=stream_manager,
                                resume=True,
                            )
                        else:
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
                                downstream_node = plan.get_node(downstream_id)
                                if downstream_node:
                                    downstream_label = (
                                        downstream_node.node_data.get("data", {}).get(
                                            "label"
                                        )
                                        or await get_node_type_label(
                                            downstream_node.node_type
                                        )
                                        or downstream_id
                                    )
                                else:
                                    downstream_label = downstream_id
                                await self._persist_skipped_node(
                                    run,
                                    downstream_id,
                                    downstream_node.node_type
                                    if downstream_node
                                    else None,
                                    downstream_label,
                                )
                                for pruned_id in all_downstream:
                                    pruned_node = plan.get_node(pruned_id)
                                    await self._persist_skipped_node(
                                        run,
                                        pruned_id,
                                        pruned_node.node_type if pruned_node else None,
                                        pruned_id,
                                    )
                                if stream_manager:
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

        # Expose the current round's iteration/loop outputs (item, index, ...)
        # as bare-name variables so body nodes can reference e.g. {{doc}} without
        # the node prefix; the node-scoped {{iteration-xxx.doc}} form keeps working
        # through normal node-output resolution.
        round_outputs = await context.get_node_outputs(iteration_node_id) or {}
        context.push_iteration_scope(
            {k: v for k, v in round_outputs.items() if not str(k).startswith("_")}
        )

        logger.info(f"Executing iteration body: {ordered_body_nodes}")

        try:
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

                # Defensive: pause nodes are rejected inside iteration/loop
                # bodies by validation; if one still pauses, surface it as an
                # execution error instead of corrupting the loop state.
                if getattr(result, "waiting", False):
                    raise NodeExecutionError(
                        node_id=node_id,
                        node_type="pause",
                        message=t("workflow_pause_inside_container"),
                    )

                logger.info(f"Iteration body node {node_id} result: {result.outputs}")
        finally:
            context.pop_iteration_scope()

    async def _execute_node(
        self,
        node_id: str,
        plan: ExecutionPlan,
        context: ExecutionContext,
        run: WorkflowRun,
        stream_manager: StreamManager | None,
        resume: bool = False,
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

        # Create NodeExecution record. Only resume runs query for a prior
        # WAITING record; normal executions preserve the existing single-create
        # path and do not add a database read.
        node_execution = None
        if resume:
            node_execution = (
                await NodeExecution.filter(
                    run_id=run.id, node_id=node_id, status=NodeStatus.WAITING
                )
                .order_by("-started_at")
                .first()
            )
        if node_execution is None:
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
        else:
            node_execution.status = NodeStatus.RUNNING
            node_execution.error_message = None
            node_execution.outputs = None
            await node_execution.save()

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

            if result.waiting:
                # Paused for external input (pause node): persist WAITING and
                # stop this execution; a later submit dispatches a resume task.
                node_execution.status = NodeStatus.WAITING
                await node_execution.save()
                if stream_manager:
                    await stream_manager.publish_node_complete(
                        node_id=node_id,
                        outputs={"waiting": True},
                        duration_ms=int((time.time() - start_time) * 1000),
                        node_type=node_type,
                        is_streaming=is_streaming_answer,
                    )
                return result

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
        Cancel a pending, running, or externally paused workflow.

        Args:
            run_id: Run ID to cancel

        Returns:
            True if cancelled, False if not found or already completed
        """
        run = await WorkflowRun.filter(id=run_id).first()
        if not run:
            return False

        if run.status not in (RunStatus.RUNNING, RunStatus.PENDING, RunStatus.WAITING):
            return False

        run.status = RunStatus.CANCELLED
        run.finished_at = datetime.now(timezone.utc)
        await run.save()

        # Close out any pending pause requests so the approval trail is not
        # left mid-flight (submit already 409s on non-WAITING runs).
        if run.status == RunStatus.CANCELLED and run.workflow_id:
            cancelled_requests = WorkflowPauseRequest.filter(
                run_id=run.id,
                status=PauseRequestStatus.PENDING,
            )
            await cancelled_requests.update(status=PauseRequestStatus.CANCELLED)
            for request in await cancelled_requests.all():
                await remove_pause_pending_notifications(request.id)

        # Set cancelled status in context (may not exist yet for PENDING runs)
        redis_client = await get_redis()
        try:
            context = await ExecutionContext.load(run_id, redis_client)
            await context.set_status("cancelled")
        except Exception as e:
            logger.warning(f"Could not load context for cancellation: {e}")

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
