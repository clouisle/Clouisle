"""
Node executor base class and registry.

Provides the foundation for implementing node type executors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from .context import ExecutionContext
    from .stream import StreamEvent

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """
    Result of a node execution.

    Attributes:
        outputs: Output variables dictionary
        next_handles: List of active output handles (for branch nodes)
        stream_events: List of stream events generated during execution
        error: Error message if execution failed
    """

    outputs: dict[str, Any] = field(default_factory=dict)
    next_handles: list[str] | None = None
    stream_events: list["StreamEvent"] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.error is None


class NodeExecutor(ABC):
    """
    Base class for node executors.

    Each node type should have a corresponding executor that handles
    its execution logic.

    Example:
        @NodeExecutorRegistry.register("llm")
        class LLMNodeExecutor(NodeExecutor):
            async def execute(self, node, context, run):
                # ... execution logic
                return ExecutionResult(outputs={"response": "..."})
    """

    # Node type identifier (should match frontend node type)
    node_type: str = ""

    @abstractmethod
    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        """
        Execute the node.

        Args:
            node: Node definition from workflow
                  {
                      "id": "node-1",
                      "type": "llm",
                      "position": {"x": 0, "y": 0},
                      "data": {
                          "type": "llm",
                          "label": "LLM Node",
                          "config": {...},
                          "llmConfig": {...}  # type-specific config
                      }
                  }
            context: Execution context for variable access
            run: Workflow run record

        Returns:
            ExecutionResult with outputs and optional branch info
        """
        pass

    async def resolve_inputs(
        self,
        context: "ExecutionContext",
        input_mappings: list[dict],
    ) -> dict[str, Any]:
        """
        Resolve input variable mappings.

        Args:
            context: Execution context
            input_mappings: List of input mappings
                [
                    {
                        "name": "query",
                        "source": "variable",
                        "variableRef": "{{start.query}}",
                    },
                    {
                        "name": "limit",
                        "source": "constant",
                        "constantValue": "10",
                    }
                ]

        Returns:
            Dictionary of resolved input values
        """
        inputs = {}

        for mapping in input_mappings:
            name = mapping.get("name")
            if not name:
                continue

            source = mapping.get("source", "variable")

            if source == "variable":
                ref = mapping.get("variableRef", mapping.get("value", ""))
                inputs[name] = await context.resolve_variable_ref(ref)
            else:  # constant
                inputs[name] = mapping.get("constantValue", "")

        return inputs

    async def validate_config(self, config: dict) -> list[str]:
        """
        Validate node configuration.

        Override in subclasses to add validation logic.

        Args:
            config: Node configuration

        Returns:
            List of validation error messages (empty if valid)
        """
        return []

    def get_output_variables(self, config: dict) -> list[dict]:
        """
        Get the list of output variables this node produces.

        Override in subclasses to define outputs.

        Args:
            config: Node configuration

        Returns:
            List of output variable definitions
            [{"name": "response", "type": "string"}]
        """
        return []


class NodeExecutorRegistry:
    """
    Registry for node executors.

    Provides registration and lookup of executors by node type.
    """

    _executors: dict[str, type[NodeExecutor]] = {}

    @classmethod
    def register(cls, node_type: str):
        """
        Decorator to register a node executor.

        Example:
            @NodeExecutorRegistry.register("llm")
            class LLMNodeExecutor(NodeExecutor):
                ...
        """

        def decorator(executor_cls: type[NodeExecutor]):
            cls._executors[node_type] = executor_cls
            executor_cls.node_type = node_type
            logger.debug(f"Registered executor for node type: {node_type}")
            return executor_cls

        return decorator

    @classmethod
    def get(cls, node_type: str) -> NodeExecutor:
        """
        Get an executor instance for a node type.

        Args:
            node_type: Node type identifier

        Returns:
            NodeExecutor instance

        Raises:
            NodeTypeNotFoundError: If no executor is registered for the type
        """
        from .errors import NodeTypeNotFoundError

        executor_cls = cls._executors.get(node_type)
        if not executor_cls:
            raise NodeTypeNotFoundError(node_type)

        return executor_cls()

    @classmethod
    def has(cls, node_type: str) -> bool:
        """Check if an executor is registered for a node type."""
        return node_type in cls._executors

    @classmethod
    def list_types(cls) -> list[str]:
        """List all registered node types."""
        return list(cls._executors.keys())

    @classmethod
    def clear(cls):
        """Clear all registered executors (for testing)."""
        cls._executors.clear()
