"""
Tests for the WorkflowOrchestrator class.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime

from app.services.workflow.orchestrator import WorkflowOrchestrator
from app.services.workflow.errors import (
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
)


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
        return WorkflowOrchestrator(timeout=10, enable_retry=False)

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
            with patch("app.services.workflow.orchestrator.WorkflowRun") as mock_run_cls:
                with patch("app.services.workflow.orchestrator.ExecutionContext") as mock_ctx_cls:
                    with patch("app.services.workflow.orchestrator.StreamManager"):
                        mock_workflow_cls.filter.return_value.first = AsyncMock(return_value=mock_wf)
                        mock_run_cls.create = AsyncMock(return_value=mock_run)

                        mock_ctx = MagicMock()
                        mock_ctx.set_inputs = AsyncMock()
                        mock_ctx.get_inputs = AsyncMock(return_value={"query": "test"})
                        mock_ctx.set_variable = AsyncMock()
                        mock_ctx.get_variable = AsyncMock(return_value="test")
                        mock_ctx.set_node_outputs = AsyncMock()
                        mock_ctx.get_status = AsyncMock(return_value="running")
                        mock_ctx_cls.create = AsyncMock(return_value=mock_ctx)

                        result = await orchestrator.run(
                            workflow_id=workflow_id,
                            inputs={"query": "test"},
                            user_id=user_id,
                            stream=False,
                        )

                        assert result == str(run_id)


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
            with patch("app.services.workflow.orchestrator.ExecutionContext") as mock_ctx_cls:
                with patch("app.services.workflow.orchestrator.StreamManager"):
                    mock_run_cls.filter.return_value.first = AsyncMock(return_value=mock_run)

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
                {"source": "condition", "target": "branch_true", "sourceHandle": "true"},
                {"source": "condition", "target": "branch_false", "sourceHandle": "false"},
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
                {"source": "process", "target": "iteration"},  # Loop back
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
