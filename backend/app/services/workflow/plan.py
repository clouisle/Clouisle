"""
Execution plan for workflow DAG.

Handles parsing workflow definition, building execution graph,
and determining execution order.
"""

from dataclasses import dataclass, field
from typing import Any
import logging

from .errors import CyclicDependencyError, WorkflowValidationError

logger = logging.getLogger(__name__)


@dataclass
class NodeDependency:
    """
    Represents a node and its dependencies.

    Attributes:
        node_id: Unique node identifier
        node_type: Node type (e.g., "llm", "condition")
        node_data: Full node data from workflow definition
        upstream: Set of upstream node IDs (dependencies)
        downstream: Set of downstream node IDs (dependents)
        handle_map: Map of source handle to downstream node IDs
    """

    node_id: str
    node_type: str
    node_data: dict
    upstream: set[str] = field(default_factory=set)
    downstream: set[str] = field(default_factory=set)
    handle_map: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ExecutionStage:
    """
    A stage of parallel node execution.

    Nodes within a stage can be executed in parallel since
    they have no dependencies on each other.

    Attributes:
        stage_index: Stage number (0-based)
        node_ids: List of node IDs in this stage
    """

    stage_index: int
    node_ids: list[str]


@dataclass
class ExecutionPlan:
    """
    Execution plan for a workflow.

    Provides methods to:
    - Parse workflow definition
    - Build dependency graph
    - Generate execution order (topological sort)
    - Get parallel execution stages

    Attributes:
        workflow_def: Original workflow definition
        nodes: Map of node_id to NodeDependency
        start_node_id: ID of the start node
        stages: List of execution stages
    """

    workflow_def: dict
    nodes: dict[str, NodeDependency] = field(default_factory=dict)
    start_node_id: str | None = None
    stages: list[ExecutionStage] = field(default_factory=list)

    @classmethod
    def from_workflow(cls, workflow_def: dict) -> "ExecutionPlan":
        """
        Create an execution plan from a workflow definition.

        Args:
            workflow_def: Workflow definition dictionary
                {
                    "nodes": [...],
                    "edges": [...],
                    "viewport": {...}
                }

        Returns:
            ExecutionPlan instance

        Raises:
            WorkflowValidationError: If workflow is invalid
            CyclicDependencyError: If workflow has cycles
        """
        plan = cls(workflow_def=workflow_def)
        plan._parse_nodes()
        plan._parse_edges()
        plan._find_start_node()
        plan._build_stages()
        return plan

    def _parse_nodes(self):
        """Parse nodes from workflow definition."""
        nodes = self.workflow_def.get("nodes", [])

        for node in nodes:
            node_id = node.get("id")
            if not node_id:
                continue

            # Get node type from data.type (as per frontend structure)
            node_data = node.get("data", {})
            node_type = node_data.get("type", node.get("type", "unknown"))

            self.nodes[node_id] = NodeDependency(
                node_id=node_id,
                node_type=node_type,
                node_data=node,
            )

        logger.debug(f"Parsed {len(self.nodes)} nodes")

    def _parse_edges(self):
        """Parse edges and build dependency relationships."""
        edges = self.workflow_def.get("edges", [])

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            source_handle = edge.get("sourceHandle", "output")

            if not source or not target:
                continue

            if source not in self.nodes or target not in self.nodes:
                logger.warning(f"Edge references missing node: {source} -> {target}")
                continue

            source_node = self.nodes[source]
            target_node = self.nodes[target]

            # Add to dependency sets
            source_node.downstream.add(target)
            target_node.upstream.add(source)

            # Add to handle map (for branching)
            if source_handle not in source_node.handle_map:
                source_node.handle_map[source_handle] = []
            source_node.handle_map[source_handle].append(target)

        logger.debug(f"Parsed {len(edges)} edges")

    def _find_start_node(self):
        """Find the start node (user_input or trigger)."""
        start_types = {"user_input", "trigger"}

        for node_id, node in self.nodes.items():
            if node.node_type in start_types:
                if self.start_node_id:
                    raise WorkflowValidationError("Workflow has multiple start nodes")
                self.start_node_id = node_id

        if not self.start_node_id:
            raise WorkflowValidationError("Workflow has no start node")

        logger.debug(f"Start node: {self.start_node_id}")

    def _build_stages(self):
        """
        Build execution stages using topological sort.

        Groups nodes into stages where all nodes in a stage can be
        executed in parallel (all dependencies satisfied).
        """
        # Kahn's algorithm with level tracking
        in_degree = {
            node_id: len(node.upstream) for node_id, node in self.nodes.items()
        }
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        processed = set()

        while queue:
            # Current stage - all nodes with no pending dependencies
            current_stage = ExecutionStage(
                stage_index=len(self.stages),
                node_ids=queue[:],
            )
            self.stages.append(current_stage)

            # Prepare next stage
            next_queue = []

            for node_id in queue:
                processed.add(node_id)
                node = self.nodes[node_id]

                for downstream_id in node.downstream:
                    in_degree[downstream_id] -= 1
                    if in_degree[downstream_id] == 0:
                        next_queue.append(downstream_id)

            queue = next_queue

        # Check for cycles
        if len(processed) != len(self.nodes):
            unprocessed = set(self.nodes.keys()) - processed
            raise CyclicDependencyError(
                f"Cyclic dependency detected involving nodes: {unprocessed}"
            )

        logger.debug(f"Built {len(self.stages)} execution stages")

    def get_node(self, node_id: str) -> NodeDependency | None:
        """Get node dependency info by ID."""
        return self.nodes.get(node_id)

    def get_execution_order(self) -> list[str]:
        """
        Get flat execution order (all stages combined).

        Returns:
            List of node IDs in execution order
        """
        order = []
        for stage in self.stages:
            order.extend(stage.node_ids)
        return order

    def get_downstream_nodes(
        self,
        node_id: str,
        handle: str | None = None,
    ) -> list[str]:
        """
        Get downstream node IDs for a node.

        Args:
            node_id: Source node ID
            handle: Optional source handle to filter by

        Returns:
            List of downstream node IDs
        """
        node = self.nodes.get(node_id)
        if not node:
            return []

        if handle:
            return node.handle_map.get(handle, [])

        return list(node.downstream)

    def get_upstream_nodes(self, node_id: str) -> list[str]:
        """
        Get upstream node IDs for a node.

        Args:
            node_id: Target node ID

        Returns:
            List of upstream node IDs
        """
        node = self.nodes.get(node_id)
        if not node:
            return []

        return list(node.upstream)

    def get_branch_paths(self, node_id: str) -> dict[str, list[str]]:
        """
        Get branch paths for a branching node (condition, etc.).

        Args:
            node_id: Branching node ID

        Returns:
            Dictionary of handle -> downstream node IDs
        """
        node = self.nodes.get(node_id)
        if not node:
            return {}

        return dict(node.handle_map)

    def get_all_downstream(self, node_id: str) -> set[str]:
        """
        Get all downstream nodes (recursively) from a node.

        Useful for determining which nodes to skip when a branch is not taken.

        Args:
            node_id: Starting node ID

        Returns:
            Set of all downstream node IDs
        """
        result = set()
        queue = [node_id]

        while queue:
            current = queue.pop(0)
            node = self.nodes.get(current)
            if not node:
                continue

            for downstream in node.downstream:
                if downstream not in result:
                    result.add(downstream)
                    queue.append(downstream)

        return result

    def validate(self) -> list[str]:
        """
        Validate the execution plan.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check start node exists
        if not self.start_node_id:
            errors.append("No start node found")

        # Check for isolated nodes (no connections)
        for node_id, node in self.nodes.items():
            # Skip start nodes and internal subgraph nodes
            if node.node_type not in {
                "user_input",
                "trigger",
                "iteration_start",
                "loop_start",
            }:
                if not node.upstream:
                    errors.append(f"Node {node_id} has no upstream connections")

            if node.node_type != "answer":
                if not node.downstream and node.node_type not in {
                    "user_input",
                    "trigger",
                }:
                    # Allow answer nodes and start nodes to have no downstream
                    pass  # OK for now, could be a dead branch

        # Check answer nodes exist
        answer_nodes = [
            node_id
            for node_id, node in self.nodes.items()
            if node.node_type == "answer"
        ]
        if not answer_nodes:
            errors.append("No answer (output) node found")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize execution plan to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "start_node_id": self.start_node_id,
            "node_count": len(self.nodes),
            "stage_count": len(self.stages),
            "stages": [
                {
                    "index": stage.stage_index,
                    "nodes": stage.node_ids,
                }
                for stage in self.stages
            ],
            "execution_order": self.get_execution_order(),
        }
