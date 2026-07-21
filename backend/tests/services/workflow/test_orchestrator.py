"""
Tests for the WorkflowOrchestrator class.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.workflow import NodeStatus, RunStatus
from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    NodeExecutionError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
)
from app.services.workflow.executor import ExecutionResult
from app.services.workflow.orchestrator import WorkflowOrchestrator


class TestWorkflowOrchestratorInit:
    """Tests for WorkflowOrchestrator initialization."""

    def test_default_init(self):
        """Test default initialization."""
        orchestrator = WorkflowOrchestrator()

        assert orchestrator.timeout == 300
        assert orchestrator.max_nodes == 100
        assert orchestrator.enable_retry is True

    def test_custom_init(self):
        """Test custom initialization."""
        orchestrator = WorkflowOrchestrator(
            timeout=600,
            max_nodes=200,
            enable_retry=False,
        )

        assert orchestrator.timeout == 600
        assert orchestrator.max_nodes == 200
        assert orchestrator.enable_retry is False


class TestWorkflowOrchestratorRun:
    """Tests for WorkflowOrchestrator.run()."""

    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator."""
        return WorkflowOrchestrator(
            timeout=10,
            enable_retry=False,
            enable_cache=False,
            enable_metrics=False,
        )

    @pytest.fixture
    def workflow_def(self):
        """Create a simple workflow definition."""
        return {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "data": {
                        "label": "Start",
                        "variables": [{"name": "query", "type": "string"}],
                    },
                },
                {
                    "id": "end",
                    "type": "answer",
                    "data": {
                        "label": "End",
                        "answer": "{{query}}",
                    },
                },
            ],
            "edges": [
                {"source": "start", "target": "end"},
            ],
        }

    @pytest.mark.asyncio
    async def test_run_workflow_not_found(self, orchestrator):
        """Test running non-existent workflow raises error."""
        with patch("app.services.workflow.orchestrator.Workflow") as mock_workflow:
            mock_workflow.filter.return_value.first = AsyncMock(return_value=None)

            with pytest.raises(WorkflowNotFoundError):
                await orchestrator.run(
                    workflow_id=uuid4(),
                    inputs={},
                    user_id=uuid4(),
                )

    @pytest.mark.asyncio
    async def test_run_workflow_not_published(self, orchestrator):
        """Test running unpublished workflow raises error."""
        mock_wf = MagicMock()
        mock_wf.name = "Test"
        mock_wf.definition = None  # No definition

        with patch("app.services.workflow.orchestrator.Workflow") as mock_workflow:
            mock_workflow.filter.return_value.first = AsyncMock(return_value=mock_wf)

            with pytest.raises(WorkflowNotPublishedError):
                await orchestrator.run(
                    workflow_id=uuid4(),
                    inputs={},
                    user_id=uuid4(),
                )

    @pytest.mark.asyncio
    async def test_run_simple_workflow(self, orchestrator, workflow_def):
        """Test running a simple workflow."""
        workflow_id = uuid4()
        user_id = uuid4()
        run_id = uuid4()

        mock_wf = MagicMock()
        mock_wf.id = workflow_id
        mock_wf.name = "Test Workflow"
        mock_wf.definition = workflow_def
        mock_wf.trigger_type = "manual"

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.workflow_id = workflow_id
        mock_run.status = "running"
        mock_run.trigger_type = "manual"
        mock_run.inputs = {}
        mock_run.save = AsyncMock()

        with patch("app.services.workflow.orchestrator.Workflow") as mock_workflow_cls:
            with patch(
                "app.services.workflow.orchestrator.WorkflowRun"
            ) as mock_run_cls:
                with patch(
                    "app.services.workflow.orchestrator.ExecutionContext"
                ) as mock_ctx_cls:
                    with patch("app.services.workflow.orchestrator.StreamManager"):
                        mock_workflow_cls.filter.return_value.first = AsyncMock(
                            return_value=mock_wf
                        )
                        mock_run_cls.create = AsyncMock(return_value=mock_run)

                        mock_ctx = MagicMock()
                        mock_ctx.set_inputs = AsyncMock()
                        mock_ctx.get_inputs = AsyncMock(return_value={"query": "test"})
                        mock_ctx.set_variable = AsyncMock()
                        mock_ctx.get_variable = AsyncMock(return_value="test")
                        mock_ctx.set_node_outputs = AsyncMock()
                        mock_ctx.get_status = AsyncMock(return_value="running")
                        mock_ctx_cls.create = AsyncMock(return_value=mock_ctx)
                        orchestrator._execute = AsyncMock(
                            return_value=({"answer": "test"}, 2)
                        )
                        orchestrator._complete_run = AsyncMock()

                        result = await orchestrator.run(
                            workflow_id=workflow_id,
                            inputs={"query": "test"},
                            user_id=user_id,
                            stream=False,
                        )

                        assert result == str(run_id)

    @pytest.mark.asyncio
    async def test_run_with_existing_run_records_stream_metrics_and_profile(
        self, workflow_def
    ):
        workflow_id = uuid4()
        user_id = uuid4()
        run_id = uuid4()
        orchestrator = WorkflowOrchestrator(
            enable_cache=False, enable_metrics=False, enable_profiling=True
        )
        orchestrator._metrics = MagicMock(
            record_workflow_start=AsyncMock(),
            record_workflow_complete=AsyncMock(),
        )
        orchestrator._get_execution_plan = AsyncMock()
        orchestrator._execute = AsyncMock(return_value=({"answer": "done"}, 2))
        orchestrator._complete_run = AsyncMock()

        workflow = MagicMock(
            id=workflow_id,
            name="Test Workflow",
            definition=workflow_def,
        )
        run = MagicMock(id=run_id, save=AsyncMock())
        plan = MagicMock()
        plan.validate.return_value = []
        orchestrator._get_execution_plan.return_value = plan
        context = MagicMock(set_inputs=AsyncMock(), set_variable=AsyncMock())
        stream = MagicMock(
            publish_workflow_start=AsyncMock(),
            publish_workflow_complete=AsyncMock(),
        )
        profiler = MagicMock()
        profiler.to_dict.return_value = {"nodes": 2}

        with (
            patch.object(
                orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
            ),
            patch("app.services.workflow.orchestrator.WorkflowRun") as workflow_run_cls,
            patch(
                "app.services.workflow.orchestrator.ExecutionContext.create",
                new=AsyncMock(return_value=context),
            ),
            patch(
                "app.services.workflow.orchestrator.StreamManager",
                return_value=stream,
            ),
            patch(
                "app.services.workflow.orchestrator.ExecutionProfiler",
                return_value=profiler,
            ),
        ):
            workflow_run_cls.filter.return_value.first = AsyncMock(return_value=run)
            result = await orchestrator.run_with_run_id(
                run_id, workflow_id, {"query": "test"}, user_id
            )

        assert result == str(run_id)
        assert run.status == RunStatus.RUNNING
        run.save.assert_awaited_once()
        context.set_inputs.assert_awaited_once_with({"query": "test"})
        orchestrator._complete_run.assert_awaited_once()
        orchestrator._metrics.record_workflow_complete.assert_awaited_once_with(
            run_id=str(run_id),
            workflow_id=str(workflow_id),
            duration_ms=pytest.approx(0, abs=1000),
            status="success",
            node_count=2,
        )
        profiler.start.assert_called_once_with()
        profiler.finish.assert_called_once_with()
        context.set_variable.assert_awaited_once_with("_profile", {"nodes": 2})
        stream.publish_workflow_start.assert_awaited_once()
        stream.publish_workflow_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_with_existing_run_reports_validation_failure(self, workflow_def):
        workflow_id = uuid4()
        run_id = uuid4()
        orchestrator = WorkflowOrchestrator(
            enable_cache=False, enable_metrics=False, enable_profiling=True
        )
        orchestrator._metrics = MagicMock(
            record_workflow_start=AsyncMock(),
            record_workflow_complete=AsyncMock(),
        )
        orchestrator._get_execution_plan = AsyncMock()
        orchestrator._fail_run = AsyncMock()

        workflow = MagicMock(
            id=workflow_id,
            name="Invalid Workflow",
            definition=workflow_def,
        )
        run = MagicMock(id=run_id, save=AsyncMock())
        plan = MagicMock()
        plan.validate.return_value = ["missing start node"]
        orchestrator._get_execution_plan.return_value = plan
        context = MagicMock(set_inputs=AsyncMock())
        stream = MagicMock(publish_workflow_error=AsyncMock())
        profiler = MagicMock()

        with (
            patch.object(
                orchestrator, "_load_workflow", AsyncMock(return_value=workflow)
            ),
            patch("app.services.workflow.orchestrator.WorkflowRun") as workflow_run_cls,
            patch(
                "app.services.workflow.orchestrator.ExecutionContext.create",
                new=AsyncMock(return_value=context),
            ),
            patch(
                "app.services.workflow.orchestrator.StreamManager",
                return_value=stream,
            ),
            patch(
                "app.services.workflow.orchestrator.ExecutionProfiler",
                return_value=profiler,
            ),
        ):
            workflow_run_cls.filter.return_value.first = AsyncMock(return_value=run)
            with pytest.raises(WorkflowValidationError):
                await orchestrator.run_with_run_id(run_id, workflow_id, {}, uuid4())

        orchestrator._fail_run.assert_awaited_once()
        orchestrator._metrics.record_workflow_complete.assert_awaited_once()
        profiler.finish.assert_called_once_with()
        stream.publish_workflow_error.assert_awaited_once()


class TestWorkflowOrchestratorCancel:
    """Tests for WorkflowOrchestrator.cancel()."""

    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator."""
        return WorkflowOrchestrator()

    @pytest.mark.asyncio
    async def test_cancel_running_workflow(self, orchestrator):
        """Test cancelling a running workflow."""
        run_id = str(uuid4())

        mock_run = MagicMock()
        mock_run.status = "running"
        mock_run.save = AsyncMock()

        with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
            with patch(
                "app.services.workflow.orchestrator.ExecutionContext"
            ) as mock_ctx_cls:
                mock_stream = MagicMock(publish_workflow_error=AsyncMock())
                with (
                    patch(
                        "app.services.workflow.orchestrator.StreamManager",
                        return_value=mock_stream,
                    ),
                    patch(
                        "app.services.workflow.orchestrator.get_redis", new=AsyncMock()
                    ),
                ):
                    mock_run_cls.filter.return_value.first = AsyncMock(
                        return_value=mock_run
                    )

                    mock_ctx = MagicMock()
                    mock_ctx.set_status = AsyncMock()
                    mock_ctx_cls.load = AsyncMock(return_value=mock_ctx)

                    result = await orchestrator.cancel(run_id)

                    assert result is True
                    assert mock_run.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_workflow(self, orchestrator):
        """Test cancelling a non-existent workflow."""
        with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
            mock_run_cls.filter.return_value.first = AsyncMock(return_value=None)

            result = await orchestrator.cancel(str(uuid4()))

            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_completed_workflow(self, orchestrator):
        """Test cancelling an already completed workflow."""
        mock_run = MagicMock()
        mock_run.status = "success"

        with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
            mock_run_cls.filter.return_value.first = AsyncMock(return_value=mock_run)

            result = await orchestrator.cancel(str(uuid4()))

            assert result is False


class TestWorkflowOrchestratorGetStatus:
    """Tests for WorkflowOrchestrator.get_run_status()."""

    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator."""
        return WorkflowOrchestrator()

    @pytest.mark.asyncio
    async def test_get_status_exists(self, orchestrator):
        """Test getting status of existing run."""
        run_id = str(uuid4())
        workflow_id = uuid4()

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.workflow_id = workflow_id
        mock_run.status = "success"
        mock_run.inputs = {"query": "test"}
        mock_run.outputs = {"answer": "result"}
        mock_run.error_message = None
        mock_run.total_duration_ms = 1234
        mock_run.created_at = datetime.utcnow()
        mock_run.finished_at = datetime.utcnow()

        with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
            mock_run_cls.filter.return_value.first = AsyncMock(return_value=mock_run)

            status = await orchestrator.get_run_status(run_id)

            assert status is not None
            assert status["id"] == run_id
            assert status["status"] == "success"
            assert status["duration_ms"] == 1234

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, orchestrator):
        """Test getting status of non-existent run."""
        with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
            mock_run_cls.filter.return_value.first = AsyncMock(return_value=None)

            status = await orchestrator.get_run_status(str(uuid4()))

            assert status is None


class TestWorkflowOrchestratorExecution:
    """Tests for WorkflowOrchestrator execution logic."""

    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator."""
        return WorkflowOrchestrator(timeout=5, max_nodes=10)

    @pytest.mark.asyncio
    async def test_execution_timeout(self, orchestrator):
        """Test execution timeout is enforced."""
        # This would require a more complex setup with actual node execution
        # For now, verify the timeout is set correctly
        assert orchestrator.timeout == 5

    @pytest.mark.asyncio
    async def test_max_nodes_limit(self, orchestrator):
        """Test max nodes limit is enforced."""
        assert orchestrator.max_nodes == 10


class TestWorkflowOrchestratorBranching:
    """Tests for branching execution in WorkflowOrchestrator."""

    @pytest.fixture
    def branching_workflow_def(self):
        """Create a workflow with branching."""
        return {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "data": {"variables": [{"name": "value", "type": "number"}]},
                },
                {
                    "id": "condition",
                    "type": "condition",
                    "data": {
                        "conditions": [
                            {"variable": "{{value}}", "operator": ">", "value": "50"}
                        ],
                    },
                },
                {
                    "id": "branch_true",
                    "type": "template",
                    "data": {"template": "Value is high"},
                },
                {
                    "id": "branch_false",
                    "type": "template",
                    "data": {"template": "Value is low"},
                },
                {
                    "id": "end",
                    "type": "answer",
                    "data": {"answer": "{{result}}"},
                },
            ],
            "edges": [
                {"source": "start", "target": "condition"},
                {
                    "source": "condition",
                    "target": "branch_true",
                    "sourceHandle": "true",
                },
                {
                    "source": "condition",
                    "target": "branch_false",
                    "sourceHandle": "false",
                },
                {"source": "branch_true", "target": "end"},
                {"source": "branch_false", "target": "end"},
            ],
        }

    def test_branching_workflow_parsing(self, branching_workflow_def):
        """Test branching workflow can be parsed."""
        from app.services.workflow.plan import ExecutionPlan

        plan = ExecutionPlan.from_workflow(branching_workflow_def)

        condition_node = plan.get_node("condition")
        assert condition_node is not None
        assert "true" in condition_node.handle_map
        assert "false" in condition_node.handle_map


class TestWorkflowOrchestratorIteration:
    """Tests for iteration execution in WorkflowOrchestrator."""

    @pytest.fixture
    def iteration_workflow_def(self):
        """Create a workflow with iteration."""
        return {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "data": {"variables": [{"name": "items", "type": "array"}]},
                },
                {
                    "id": "iteration",
                    "type": "iteration",
                    "data": {
                        "items": "{{items}}",
                        "itemVariable": "item",
                    },
                },
                {
                    "id": "process",
                    "type": "template",
                    "data": {"template": "Processing {{item}}"},
                },
                {
                    "id": "end",
                    "type": "answer",
                    "data": {"answer": "Done"},
                },
            ],
            "edges": [
                {"source": "start", "target": "iteration"},
                {"source": "iteration", "target": "process"},
                {"source": "iteration", "target": "end", "sourceHandle": "complete"},
            ],
        }

    def test_iteration_workflow_parsing(self, iteration_workflow_def):
        """Test iteration workflow can be parsed."""
        from app.services.workflow.plan import ExecutionPlan

        plan = ExecutionPlan.from_workflow(iteration_workflow_def)

        iteration_node = plan.get_node("iteration")
        assert iteration_node is not None
        assert iteration_node.node_type == "iteration"


class TestWorkflowOrchestratorBehavior:
    @pytest.fixture
    def orchestrator(self):
        return WorkflowOrchestrator(
            timeout=10,
            max_nodes=2,
            enable_retry=False,
            enable_cache=False,
            enable_metrics=False,
        )

    @pytest.mark.asyncio
    async def test_run_validation_failure_marks_run_failed_and_streams_error(
        self, orchestrator
    ):
        workflow_id = uuid4()
        run = MagicMock(id=uuid4())
        workflow = MagicMock(id=workflow_id, name="Invalid")
        context = MagicMock(set_inputs=AsyncMock())
        plan = MagicMock()
        plan.validate.return_value = ["missing start node"]
        stream = MagicMock(
            publish_workflow_error=AsyncMock(),
            publish_workflow_start=AsyncMock(),
        )

        orchestrator._load_workflow = AsyncMock(return_value=workflow)
        orchestrator._get_workflow_definition = AsyncMock(return_value={})
        orchestrator._create_run = AsyncMock(return_value=run)
        orchestrator._get_execution_plan = AsyncMock(return_value=plan)
        orchestrator._fail_run = AsyncMock()

        with (
            patch("app.services.workflow.orchestrator.get_redis", new=AsyncMock()),
            patch(
                "app.services.workflow.orchestrator.ExecutionContext.create",
                new=AsyncMock(return_value=context),
            ),
            patch(
                "app.services.workflow.orchestrator.StreamManager",
                return_value=stream,
            ),
            pytest.raises(WorkflowValidationError),
        ):
            await orchestrator.run(workflow_id, {}, uuid4())

        orchestrator._fail_run.assert_awaited_once()
        assert "missing start node" in str(orchestrator._fail_run.await_args.args[1])
        stream.publish_workflow_start.assert_not_awaited()
        stream.publish_workflow_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_with_run_id_rejects_missing_run(self, orchestrator):
        orchestrator._load_workflow = AsyncMock(return_value=MagicMock())
        orchestrator._get_workflow_definition = AsyncMock(return_value={})

        with (
            patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
            pytest.raises(WorkflowNotFoundError),
        ):
            run_model.filter.return_value.first = AsyncMock(return_value=None)
            await orchestrator.run_with_run_id(uuid4(), uuid4(), {}, uuid4())

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("start_time", "status", "error_type"),
        [
            (0, "running", ExecutionTimeoutError),
            (None, "cancelled", ExecutionCancelledError),
        ],
    )
    async def test_execute_stops_at_timeout_or_cancellation(
        self, orchestrator, start_time, status, error_type
    ):
        context = MagicMock(get_status=AsyncMock(return_value=status))
        plan = MagicMock(stages=[MagicMock(node_ids=[])])

        with pytest.raises(error_type):
            await orchestrator._execute(
                plan,
                context,
                MagicMock(),
                None,
                start_time if start_time is not None else __import__("time").time(),
            )

    @pytest.mark.asyncio
    async def test_execute_enforces_max_nodes_boundary(self, orchestrator):
        node = MagicMock(node_type="template", upstream=set())
        plan = MagicMock(stages=[MagicMock(node_ids=["one", "two", "three"])])
        plan.get_node.return_value = node
        context = MagicMock(get_status=AsyncMock(return_value="running"))
        orchestrator._execute_node = AsyncMock(return_value=ExecutionResult())

        with pytest.raises(NodeExecutionError, match="maximum node count"):
            await orchestrator._execute(
                plan, context, MagicMock(), None, __import__("time").time()
            )

        assert orchestrator._execute_node.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_skips_untaken_branch_and_collects_answer(self, orchestrator):
        condition = MagicMock(
            node_type="condition",
            upstream=set(),
            handle_map={"true": ["answer"], "false": ["unused"]},
        )
        answer = MagicMock(node_type="answer", upstream=set(), handle_map={})
        unused = MagicMock(node_type="template", upstream=set(), handle_map={})
        nodes = {"condition": condition, "answer": answer, "unused": unused}
        plan = MagicMock(
            stages=[
                MagicMock(node_ids=["condition"]),
                MagicMock(node_ids=["answer", "unused"]),
            ]
        )
        plan.get_node.side_effect = nodes.get
        plan.get_all_downstream.return_value = []
        context = MagicMock(get_status=AsyncMock(return_value="running"))
        orchestrator._execute_node = AsyncMock(
            side_effect=[
                ExecutionResult(next_handles=["true"]),
                ExecutionResult(outputs={"answer": "done"}),
            ]
        )

        outputs, count = await orchestrator._execute(
            plan, context, MagicMock(), None, __import__("time").time()
        )

        assert outputs == {"answer": "done"}
        assert count == 2
        assert [
            call.kwargs["node_id"]
            for call in orchestrator._execute_node.await_args_list
        ] == [
            "condition",
            "answer",
        ]

    @pytest.mark.asyncio
    async def test_execute_node_success_serializes_boundary_outputs(self, orchestrator):
        node = MagicMock(
            node_type="template",
            node_data={"data": {"label": "Template", "config": {}}},
        )
        plan = MagicMock()
        plan.get_node.return_value = node
        run = MagicMock(id=uuid4())
        context = MagicMock(set_node_outputs=AsyncMock())
        execution = MagicMock(save=AsyncMock())
        executor = MagicMock(
            execute=AsyncMock(
                return_value=ExecutionResult(
                    outputs={"ok": {"value": 1}, "opaque": object()}
                )
            )
        )

        with (
            patch(
                "app.services.workflow.orchestrator.NodeExecution"
            ) as execution_model,
            patch(
                "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
                return_value=executor,
            ),
        ):
            execution_model.filter.return_value.all = AsyncMock(return_value=[])
            execution_model.create = AsyncMock(return_value=execution)
            result = await orchestrator._execute_node(
                "template", plan, context, run, None
            )

        assert result.outputs["ok"] == {"value": 1}
        assert execution.status == NodeStatus.SUCCESS
        assert execution.outputs["ok"] == {"value": 1}
        assert execution.outputs["opaque"] == "__NON_SERIALIZABLE_object__"
        context.set_node_outputs.assert_awaited_once_with("template", result.outputs)

    @pytest.mark.asyncio
    async def test_execute_node_executor_error_records_failure(self, orchestrator):
        node = MagicMock(
            node_type="template", node_data={"data": {"label": "Template"}}
        )
        plan = MagicMock()
        plan.get_node.return_value = node
        execution = MagicMock(save=AsyncMock())
        stream = MagicMock(
            publish_node_start=AsyncMock(), publish_node_error=AsyncMock()
        )
        executor = MagicMock(
            execute=AsyncMock(return_value=ExecutionResult(error="bad input"))
        )

        with (
            patch(
                "app.services.workflow.orchestrator.NodeExecution"
            ) as execution_model,
            patch(
                "app.services.workflow.orchestrator.NodeExecutorRegistry.get",
                return_value=executor,
            ),
            pytest.raises(NodeExecutionError),
        ):
            execution_model.filter.return_value.all = AsyncMock(return_value=[])
            execution_model.create = AsyncMock(return_value=execution)
            await orchestrator._execute_node(
                "template", plan, MagicMock(), MagicMock(id=uuid4()), stream
            )

        assert execution.status == NodeStatus.FAILED
        assert execution.error_type == "NodeExecutionError"
        execution.save.assert_awaited_once()
        stream.publish_node_error.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_pending_run_survives_missing_context(self, orchestrator):
        run = MagicMock(status=RunStatus.PENDING, save=AsyncMock())
        stream = MagicMock(publish_workflow_error=AsyncMock())

        with (
            patch("app.services.workflow.orchestrator.WorkflowRun") as run_model,
            patch("app.services.workflow.orchestrator.get_redis", new=AsyncMock()),
            patch(
                "app.services.workflow.orchestrator.ExecutionContext.load",
                new=AsyncMock(side_effect=RuntimeError("not created")),
            ),
            patch(
                "app.services.workflow.orchestrator.StreamManager",
                return_value=stream,
            ),
        ):
            run_model.filter.return_value.first = AsyncMock(return_value=run)
            assert await orchestrator.cancel(str(uuid4())) is True

        assert run.status == RunStatus.CANCELLED
        run.save.assert_awaited_once()
        stream.publish_workflow_error.assert_awaited_once()
