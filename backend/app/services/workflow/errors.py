"""
Workflow execution errors.
"""

from typing import Any


class WorkflowError(Exception):
    """Base class for workflow errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class WorkflowNotFoundError(WorkflowError):
    """Workflow not found."""

    pass


class WorkflowNotPublishedError(WorkflowError):
    """Workflow is not published and cannot be executed."""

    pass


class WorkflowValidationError(WorkflowError):
    """Workflow definition is invalid."""

    pass


class NodeExecutionError(WorkflowError):
    """Error during node execution."""

    def __init__(
        self,
        message: str,
        node_id: str,
        node_type: str,
        details: dict[str, Any] | None = None,
    ):
        self.node_id = node_id
        self.node_type = node_type
        super().__init__(message, details)


class VariableNotFoundError(WorkflowError):
    """Referenced variable not found."""

    def __init__(self, variable_ref: str):
        self.variable_ref = variable_ref
        super().__init__(f"Variable not found: {variable_ref}")


class NodeTypeNotFoundError(WorkflowError):
    """Node executor not found for the given type."""

    def __init__(self, node_type: str):
        self.node_type = node_type
        super().__init__(f"No executor registered for node type: {node_type}")


class ExecutionTimeoutError(WorkflowError):
    """Workflow or node execution timed out."""

    pass


class ExecutionCancelledError(WorkflowError):
    """Workflow execution was cancelled."""

    pass


class CyclicDependencyError(WorkflowError):
    """Workflow contains cyclic dependencies."""

    pass


class MaxDepthExceededError(WorkflowError):
    """Maximum sub-workflow depth exceeded."""

    def __init__(self, max_depth: int, current_depth: int):
        self.max_depth = max_depth
        self.current_depth = current_depth
        super().__init__(
            f"Maximum sub-workflow depth ({max_depth}) exceeded. Current: {current_depth}"
        )
