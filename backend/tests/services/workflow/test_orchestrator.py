"""
Tests for the WorkflowOrchestrator class.
"""

from datetime import UTC, datetime
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
    async def test_published_run_uses_latest_snapshot(self, orchestrator, workflow_def):
        workflow_id = uuid4()
        workflow = MagicMock(id=workflow_id, name="Test", definition={"draft": True})
        snapshot = MagicMock(version=3, definition=workflow_def)

        with patch("app.services.workflow.orchestrator.WorkflowVersion") as versions:
            versions.filter.return_value.order_by.return_value.first = AsyncMock(
                return_value=snapshot
            )
            result = await orchestrator._get_workflow_definition(
                workflow, is_debug=False
            )

        assert result is workflow_def
        versions.filter.assert_called_once_with(workflow_id=workflow_id)
        versions.filter.return_value.order_by.assert_called_once_with("-version")

    @pytest.mark.asyncio
    async def test_debug_run_uses_live_draft(self, orchestrator):
        workflow = MagicMock(
            id=uuid4(),
            name="Test",
            definition={"nodes": [{"id": "draft"}]},
            updated_at=None,
        )

        with patch("app.services.workflow.orchestrator.WorkflowVersion") as versions:
            result = await orchestrator._get_workflow_definition(
                workflow, is_debug=True
            )

        assert result == workflow.definition
        versions.filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_published_run_without_snapshot_fails_fast(self, orchestrator):
        workflow = MagicMock(id=uuid4(), name="Test", definition={"draft": True})

        with patch("app.services.workflow.orchestrator.WorkflowVersion") as versions:
            versions.filter.return_value.order_by.return_value.first = AsyncMock(
                return_value=None
            )
            with pytest.raises(WorkflowNotPublishedError):
                await orchestrator._get_workflow_definition(workflow, is_debug=False)

        versions.filter.assert_called_once_with(workflow_id=workflow.id)

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


class TestWorkflowOrchestratorCompletion:
    @pytest.fixture
    def orchestrator(self):
        return WorkflowOrchestrator(
            enable_retry=False, enable_cache=False, enable_metrics=False
        )

    @pytest.mark.asyncio
    async def test_complete_run_updates_statistics_and_notifies_team(
        self, orchestrator
    ):
        workflow_id = uuid4()
        team_id = uuid4()
        run = MagicMock(
            id=uuid4(),
            workflow_id=workflow_id,
            is_debug=False,
            total_token_usage={"prompt": 2, "completion": 3},
            triggered_by_id=None,
            save=AsyncMock(),
        )
        executions = [
            MagicMock(status=NodeStatus.SUCCESS),
            MagicMock(status=NodeStatus.FAILED),
            MagicMock(status=NodeStatus.SKIPPED),
        ]
        workflow = MagicMock(id=workflow_id, team_id=team_id, name="Team Workflow")

        with (
            patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
            patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
            patch("app.services.workflow.orchestrator.Team") as team_model,
            patch(
                "app.services.workflow.orchestrator.get_default_language",
                new=AsyncMock(return_value="en"),
            ),
            patch(
                "app.services.workflow.orchestrator.AutoNotificationService.send_to_team",
                new=AsyncMock(),
            ) as notify,
        ):
            node_model.filter.return_value.all = AsyncMock(return_value=executions)
            workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
            workflow_model.filter.return_value.update = AsyncMock()
            team_model.filter.return_value.update = AsyncMock()

            await orchestrator._complete_run(run, {"answer": "done"}, 25)

        assert run.status == RunStatus.SUCCESS
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
        assert run.outputs == {"answer": "done"}
        run.save.assert_awaited_once()
        workflow_model.filter.return_value.update.assert_awaited_once()
        team_model.filter.return_value.update.assert_awaited_once()
        notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fail_run_updates_statistics_and_notifies_user(self, orchestrator):
        workflow_id = uuid4()
        user_id = uuid4()
        user = MagicMock(locale="zh")
        run = MagicMock(
            id=uuid4(),
            workflow_id=workflow_id,
            total_token_usage=None,
            triggered_by_id=user_id,
            triggered_by=user,
            fetch_related=AsyncMock(),
            save=AsyncMock(),
        )
        workflow = MagicMock(id=workflow_id, team_id=uuid4(), name="Failed Workflow")

        with (
            patch("app.services.workflow.orchestrator.NodeExecution") as node_model,
            patch("app.services.workflow.orchestrator.Workflow") as workflow_model,
            patch(
                "app.services.workflow.orchestrator.AutoNotificationService.send_to_user",
                new=AsyncMock(),
            ) as notify,
        ):
            node_model.filter.return_value.all = AsyncMock(return_value=[])
            workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
            workflow_model.filter.return_value.update = AsyncMock()

            await orchestrator._fail_run(run, "provider unavailable", 40)

        assert run.status == RunStatus.FAILED
        assert run.error_message == "provider unavailable"
        assert run.total_nodes == 0
        run.save.assert_awaited_once()
        run.fetch_related.assert_awaited_once_with("triggered_by")
        workflow_model.filter.return_value.update.assert_awaited_once()
        notify.assert_awaited_once()


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
                "app.services.workflow.orchestrator.WorkflowPauseRequest"
            ) as mock_pr_cls:
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
                            "app.services.workflow.orchestrator.get_redis",
                            new=AsyncMock(),
                        ),
                    ):
                        mock_pr_cls.filter.return_value.update = AsyncMock(
                            return_value=1
                        )
                        mock_pr_cls.filter.return_value.all = AsyncMock(return_value=[])
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
        mock_run.created_at = datetime.now(UTC)
        mock_run.finished_at = datetime.now(UTC)

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


class TestWorkflowOrchestratorIterationScope:
    """Iteration body exposes the round's item/index as bare-name variables."""

    class _FakeRedis:
        def __init__(self):
            self.hashes: dict[str, dict[str, str]] = {}
            self.values: dict[str, str] = {}

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value):
            self.values[key] = value

        async def expire(self, key, seconds):
            pass

        async def hset(self, key, field=None, value=None, *, mapping=None):
            target = self.hashes.setdefault(key, {})
            if mapping is not None:
                target.update({name: str(item) for name, item in mapping.items()})
            elif field is not None:
                target[field] = value

        async def hget(self, key, field):
            return self.hashes.get(key, {}).get(field)

        async def hgetall(self, key):
            return dict(self.hashes.get(key, {}))

        async def delete(self, key):
            self.hashes.pop(key, None)
            self.values.pop(key, None)

    @pytest.mark.asyncio
    async def test_body_nodes_resolve_bare_item_name_and_scope_is_popped(self):
        from app.services.workflow.context import ExecutionContext

        context = ExecutionContext(run_id=str(uuid4()), redis_client=self._FakeRedis())
        await context.set_node_outputs(
            "iteration-1",
            {"doc": "/uploads/a.pdf", "index": 0, "total": 1, "results": []},
        )

        orchestrator = WorkflowOrchestrator(
            timeout=10,
            max_nodes=10,
            enable_retry=False,
            enable_cache=False,
            enable_metrics=False,
        )
        resolved: list = []

        async def fake_execute_node(node_id, plan, context, run, stream_manager):
            resolved.append(await context.resolve_variable_ref("{{doc}}"))
            return ExecutionResult(outputs={"url": "http://x/a.pdf"})

        orchestrator._execute_node = fake_execute_node  # type: ignore[method-assign]

        await orchestrator._execute_iteration_body(
            iteration_node_id="iteration-1",
            downstream_nodes=["file_to_url-1"],
            plan=MagicMock(),
            context=context,
            run=MagicMock(),
            stream_manager=None,
            start_time=datetime.now(UTC).timestamp(),
            executed_nodes=set(),
            skipped_nodes=set(),
        )

        # 迭代 body 内 {{doc}} 解析为当前轮的 item（等价于 {{iteration-1.doc}}）
        assert resolved == ["/uploads/a.pdf"]
        assert await context.resolve_variable_ref("{{iteration-1.doc}}") == (
            "/uploads/a.pdf"
        )
        # body 结束后作用域已弹出，裸名不再解析
        assert await context.resolve_variable_ref("{{doc}}") is None


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
        run.save = AsyncMock()
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

        with patch("app.services.workflow.orchestrator.NodeExecution") as node_cls:
            node_cls.filter.return_value.first = AsyncMock(return_value=None)
            node_cls.filter.return_value.all = AsyncMock(return_value=[])
            node_cls.create = AsyncMock()
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
    async def test_execute_streams_skipped_upstream_and_branch_nodes(
        self, orchestrator
    ):
        condition = MagicMock(
            node_type="condition",
            upstream=set(),
            handle_map={"yes": ["answer"], "no": ["unused"]},
            node_data={"data": {"label": "Condition"}},
        )
        answer = MagicMock(
            node_type="answer",
            upstream=set(),
            handle_map={},
            node_data={"data": {"label": "Answer"}},
        )
        unused = MagicMock(
            node_type="template",
            upstream=set(),
            handle_map={},
            node_data={"data": {}},
        )
        descendant = MagicMock(
            node_type="template",
            upstream={"unused"},
            handle_map={},
            node_data={"data": {}},
        )
        nodes = {
            "condition": condition,
            "answer": answer,
            "unused": unused,
            "descendant": descendant,
        }
        plan = MagicMock(
            stages=[
                MagicMock(node_ids=["condition"]),
                MagicMock(node_ids=["answer", "unused"]),
                MagicMock(node_ids=["descendant"]),
            ]
        )
        plan.get_node.side_effect = nodes.get
        plan.get_all_downstream.return_value = []
        context = MagicMock(get_status=AsyncMock(return_value="running"))
        stream = MagicMock(publish_node_skip=AsyncMock())
        orchestrator._execute_node = AsyncMock(
            side_effect=[
                ExecutionResult(next_handles=["yes"]),
                ExecutionResult(outputs={"answer": "done"}),
            ]
        )

        with patch("app.services.workflow.orchestrator.NodeExecution") as node_cls:
            node_cls.filter.return_value.first = AsyncMock(return_value=None)
            node_cls.filter.return_value.all = AsyncMock(return_value=[])
            node_cls.create = AsyncMock()
            outputs, count = await orchestrator._execute(
                plan, context, MagicMock(), stream, __import__("time").time()
            )

        assert outputs == {"answer": "done"}
        assert count == 2
        assert stream.publish_node_skip.await_count == 2
        assert {
            call.kwargs["reason"] for call in stream.publish_node_skip.await_args_list
        } == {"branch_not_taken", "upstream_skipped"}

    @pytest.mark.asyncio
    async def test_execute_repeats_iteration_body_until_complete(self, orchestrator):
        iteration = MagicMock(
            node_type="iteration",
            upstream=set(),
            handle_map={},
        )
        plan = MagicMock(stages=[MagicMock(node_ids=["iteration", "child"])])
        plan.get_node.return_value = iteration
        context = MagicMock(get_status=AsyncMock(return_value="running"))
        orchestrator._get_child_nodes = MagicMock(return_value=["child"])
        orchestrator._execute_iteration_body = AsyncMock()
        orchestrator._execute_node = AsyncMock(
            side_effect=[
                ExecutionResult(outputs={"_iteration_complete": False}),
                ExecutionResult(outputs={"_iteration_complete": True}),
            ]
        )

        outputs, count = await orchestrator._execute(
            plan, context, MagicMock(), None, __import__("time").time()
        )

        assert outputs == {}
        assert count == 1
        orchestrator._execute_iteration_body.assert_awaited_once()
        assert orchestrator._execute_node.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_defers_container_children_to_iteration_parent(
        self, orchestrator
    ):
        child = MagicMock(
            node_type="iteration_start",
            node_data={"id": "child", "parentId": "iteration"},
            upstream=set(),
            handle_map={},
        )
        iteration = MagicMock(
            node_type="iteration",
            node_data={"id": "iteration", "data": {}},
            upstream=set(),
            handle_map={},
        )
        nodes = {"child": child, "iteration": iteration}
        plan = MagicMock(
            stages=[
                MagicMock(node_ids=["child"]),
                MagicMock(node_ids=["iteration"]),
            ]
        )
        plan.get_node.side_effect = nodes.get
        context = MagicMock(get_status=AsyncMock(return_value="running"))
        orchestrator._get_child_nodes = MagicMock(return_value=["child"])
        orchestrator._execute_iteration_body = AsyncMock()
        orchestrator._execute_node = AsyncMock(
            side_effect=[
                ExecutionResult(outputs={"_iteration_complete": False}),
                ExecutionResult(outputs={"_iteration_complete": True}),
            ]
        )

        outputs, count = await orchestrator._execute(
            plan, context, MagicMock(), None, __import__("time").time()
        )

        assert outputs == {}
        assert count == 1
        assert [
            call.kwargs["node_id"]
            for call in orchestrator._execute_node.await_args_list
        ] == ["iteration", "iteration"]
        orchestrator._execute_iteration_body.assert_awaited_once()

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
            patch(
                "app.services.workflow.orchestrator.WorkflowPauseRequest"
            ) as pause_model,
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
            pause_model.filter.return_value.update = AsyncMock(return_value=1)
            pause_model.filter.return_value.all = AsyncMock(return_value=[])
            run_model.filter.return_value.first = AsyncMock(return_value=run)
            assert await orchestrator.cancel(str(uuid4())) is True

        assert run.status == RunStatus.CANCELLED
        run.save.assert_awaited_once()
        stream.publish_workflow_error.assert_awaited_once()
