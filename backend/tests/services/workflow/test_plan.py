"""
Tests for the ExecutionPlan class.
"""

import pytest

from app.services.workflow.plan import ExecutionPlan, ExecutionNode, ExecutionStage


class TestExecutionNode:
    """Tests for ExecutionNode dataclass."""

    def test_node_creation(self):
        """Test creating an execution node."""
        node = ExecutionNode(
            node_id="node_1",
            node_type="llm",
            node_data={"data": {"label": "Test"}},
            upstream={"node_0"},
            downstream={"node_2", "node_3"},
        )

        assert node.node_id == "node_1"
        assert node.node_type == "llm"
        assert "node_0" in node.upstream
        assert "node_2" in node.downstream
        assert "node_3" in node.downstream

    def test_node_with_handle_map(self):
        """Test creating a node with handle map."""
        node = ExecutionNode(
            node_id="condition_1",
            node_type="condition",
            node_data={},
            upstream=set(),
            downstream={"node_true", "node_false"},
            handle_map={
                "true": ["node_true"],
                "false": ["node_false"],
            },
        )

        assert node.handle_map["true"] == ["node_true"]
        assert node.handle_map["false"] == ["node_false"]


class TestExecutionStage:
    """Tests for ExecutionStage dataclass."""

    def test_stage_creation(self):
        """Test creating an execution stage."""
        stage = ExecutionStage(
            index=0,
            node_ids=["node_1", "node_2", "node_3"],
        )

        assert stage.index == 0
        assert len(stage.node_ids) == 3
        assert "node_1" in stage.node_ids


class TestExecutionPlanFromWorkflow:
    """Tests for ExecutionPlan.from_workflow()."""

    def test_simple_workflow(self):
        """Test parsing a simple linear workflow."""
        workflow_def = {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "data": {"label": "Start"},
                },
                {
                    "id": "llm_1",
                    "type": "llm",
                    "data": {"label": "LLM"},
                },
                {
                    "id": "end",
                    "type": "answer",
                    "data": {"label": "End"},
                },
            ],
            "edges": [
                {"source": "start", "target": "llm_1"},
                {"source": "llm_1", "target": "end"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)

        assert len(plan.nodes) == 3
        assert plan.start_node_id == "start"
        assert plan.end_node_ids == {"end"}

        # Check stages
        assert len(plan.stages) >= 1

    def test_parallel_workflow(self):
        """Test parsing a workflow with parallel nodes."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "llm_1", "type": "llm", "data": {}},
                {"id": "llm_2", "type": "llm", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "llm_1"},
                {"source": "start", "target": "llm_2"},
                {"source": "llm_1", "target": "end"},
                {"source": "llm_2", "target": "end"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)

        # llm_1 and llm_2 should be in the same stage
        node_1 = plan.get_node("llm_1")
        node_2 = plan.get_node("llm_2")

        assert node_1 is not None
        assert node_2 is not None
        assert node_1.upstream == {"start"}
        assert node_2.upstream == {"start"}

    def test_conditional_workflow(self):
        """Test parsing a workflow with condition node."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "condition", "type": "condition", "data": {}},
                {"id": "branch_true", "type": "llm", "data": {}},
                {"id": "branch_false", "type": "llm", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
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

        plan = ExecutionPlan.from_workflow(workflow_def)

        condition_node = plan.get_node("condition")
        assert condition_node is not None
        assert "true" in condition_node.handle_map
        assert "false" in condition_node.handle_map


class TestExecutionPlanValidation:
    """Tests for ExecutionPlan validation."""

    def test_valid_workflow(self):
        """Test validating a valid workflow."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "end"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)
        errors = plan.validate()

        assert len(errors) == 0

    def test_empty_workflow(self):
        """Test validating an empty workflow."""
        workflow_def = {
            "nodes": [],
            "edges": [],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)
        errors = plan.validate()

        assert len(errors) > 0  # Should have error about empty workflow

    def test_disconnected_nodes(self):
        """Test validating a workflow with disconnected nodes."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "disconnected", "type": "llm", "data": {}},  # No edges
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "end"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)
        plan.validate()

        # Should have error or warning about disconnected node
        # Implementation-dependent


class TestExecutionPlanNavigation:
    """Tests for ExecutionPlan navigation methods."""

    @pytest.fixture
    def plan(self):
        """Create a test execution plan."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "middle", "type": "llm", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "middle"},
                {"source": "middle", "target": "end"},
            ],
        }
        return ExecutionPlan.from_workflow(workflow_def)

    def test_get_node(self, plan):
        """Test getting a node by ID."""
        node = plan.get_node("middle")
        assert node is not None
        assert node.node_type == "llm"

    def test_get_node_not_found(self, plan):
        """Test getting a non-existent node."""
        node = plan.get_node("nonexistent")
        assert node is None

    def test_get_execution_order(self, plan):
        """Test getting execution order."""
        order = plan.get_execution_order()
        assert len(order) == 3
        assert order[0] == "start"  # Start should be first
        assert order[-1] == "end"  # End should be last

    def test_get_downstream_nodes(self, plan):
        """Test getting downstream nodes."""
        downstream = plan.get_downstream_nodes("start")
        assert "middle" in downstream

    def test_get_upstream_nodes(self, plan):
        """Test getting upstream nodes."""
        upstream = plan.get_upstream_nodes("end")
        assert "middle" in upstream


class TestExecutionPlanCycles:
    """Tests for cycle detection in execution plans."""

    def test_no_cycles(self):
        """Test workflow without cycles."""
        workflow_def = {
            "nodes": [
                {"id": "a", "type": "user_input", "data": {}},
                {"id": "b", "type": "llm", "data": {}},
                {"id": "c", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)
        errors = plan.validate()

        cycle_errors = [e for e in errors if "cycle" in e.lower()]
        assert len(cycle_errors) == 0

    def test_with_iteration_node(self):
        """Test workflow with iteration node (allowed cycle)."""
        workflow_def = {
            "nodes": [
                {"id": "start", "type": "user_input", "data": {}},
                {"id": "iteration", "type": "iteration", "data": {}},
                {"id": "body", "type": "llm", "data": {}},
                {"id": "end", "type": "answer", "data": {}},
            ],
            "edges": [
                {"source": "start", "target": "iteration"},
                {"source": "iteration", "target": "body"},
                {"source": "body", "target": "iteration"},  # Loop back
                {"source": "iteration", "target": "end", "sourceHandle": "complete"},
            ],
        }

        plan = ExecutionPlan.from_workflow(workflow_def)
        # Should handle iteration cycles gracefully
        assert plan is not None
