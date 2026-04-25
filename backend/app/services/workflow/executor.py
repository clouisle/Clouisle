"""
Node executor base class and registry.

Provides the foundation for implementing node type executors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from .context import ExecutionContext
    from .stream import StreamEvent

from .types import NodeInputMapping, NodeOutputDecl, WorkflowValue

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

    outputs: dict[str, WorkflowValue] = field(default_factory=dict)
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
        input_mappings: list[NodeInputMapping],
    ) -> dict[str, WorkflowValue]:
        """
        Resolve input variable mappings.

        Args:
            context: Execution context
            input_mappings: List of input mappings
                [
                    NodeInputMapping(name="query", source="variable", variableRef="{{start.query}}"),
                    NodeInputMapping(name="limit", source="constant", constantValue="10"),
                ]

        Returns:
            Dictionary of resolved input values
        """
        from app.core.i18n import t

        # Check for duplicate parameter names
        names: list[str] = []
        for m in input_mappings:
            name = m.name if isinstance(m, NodeInputMapping) else m.get("name")
            if name and isinstance(name, str):
                names.append(name)

        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in names:
            if name in seen:
                duplicates.add(name)
            seen.add(name)

        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(t("duplicate_input_parameter_names", names=duplicate_list))

        inputs: dict[str, WorkflowValue] = {}

        for mapping in input_mappings:
            if isinstance(mapping, NodeInputMapping):
                name = mapping.name
                source = mapping.source

                if source == "variable" and mapping.variableRef:
                    inputs[name] = await context.resolve_variable_ref(mapping.variableRef)
                else:  # constant
                    inputs[name] = mapping.constantValue if mapping.constantValue is not None else ""
            else:
                # Handle raw dict for backward compatibility
                name = mapping.get("name")
                if not name:
                    continue

                source = mapping.get("source", "variable")
                if source == "variable":
                    variable_ref = mapping.get("variableRef") or mapping.get("value", "")
                    inputs[name] = await context.resolve_variable_ref(variable_ref)
                else:
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

        Legacy form: `[{"name": "response", "type": "string"}]`. Prefer
        `get_output_specs()` for new code — it carries structural TypeSpec
        info (object fields, array item types). Both are kept until callers
        finish migrating; the default `get_output_specs` reads from this
        method when a subclass has not overridden it.

        Override either method in subclasses; if you only override
        `get_output_variables`, structural type info defaults to a flat
        scalar/`any` TypeSpec derived from the legacy type string.
        """
        return []

    def get_output_specs(self, config: dict) -> list["NodeOutputDecl"]:
        """
        Structural output declarations for this node.

        Default implementation lifts the legacy `get_output_variables`
        dict-list, converting each `type` string to a flat `TypeSpec`. Override
        directly when the executor knows richer structure (object fields,
        array item types, user-declared schema in `config`).
        """
        from .types import NodeOutputDecl, legacy_type_to_spec

        decls: list[NodeOutputDecl] = []
        for entry in self.get_output_variables(config):
            name = entry.get("name")
            if not name or not isinstance(name, str):
                continue
            type_str = entry.get("type") if isinstance(entry, dict) else None
            description = entry.get("description") if isinstance(entry, dict) else None
            decls.append(
                NodeOutputDecl(
                    name=name,
                    type=legacy_type_to_spec(type_str)
                    if isinstance(type_str, str)
                    else legacy_type_to_spec(None),
                    description=description if isinstance(description, str) else None,
                )
            )
        return decls


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
