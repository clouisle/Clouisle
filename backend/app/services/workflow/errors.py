"""
Workflow execution errors.
"""

from typing import Any

from app.core.i18n import has_translation, t
from app.services.error_messages import is_safe_user_visible_error


class WorkflowError(Exception):
    """Base class for workflow errors."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        msg_key: str | None = None,
        **kwargs: Any,
    ):
        self.message = message
        self.details = details or {}
        self.msg_key = msg_key
        self.kwargs = kwargs
        super().__init__(message)


def get_public_workflow_error_key(error: BaseException | str | None) -> str | None:
    if isinstance(error, WorkflowError) and error.msg_key:
        return error.msg_key

    raw_message = str(error or "").strip()
    if not raw_message:
        return "workflow_execution_error"

    if has_translation(raw_message):
        return raw_message

    lowered = raw_message.lower()
    if "cancelled" in lowered:
        return "workflow_run_cancelled"
    if "timeout" in lowered or "timed out" in lowered:
        return "request_timeout"
    if "workflow validation failed" in lowered:
        return "validation_error"
    if "sub-workflow" in lowered:
        return "workflow_execution_error"

    return None


def translate_public_workflow_error(error: BaseException | str | None) -> str:
    if isinstance(error, WorkflowError) and error.msg_key:
        return t(error.msg_key, **error.kwargs)

    msg_key = get_public_workflow_error_key(error)
    if msg_key:
        return t(msg_key)

    raw_message = str(error or "").strip()
    if is_safe_user_visible_error(raw_message):
        return raw_message

    return t("workflow_execution_error")


class WorkflowNotFoundError(WorkflowError):
    """Workflow not found."""

    pass


class WorkflowNotPublishedError(WorkflowError):
    """Workflow is not published and cannot be executed."""

    def __init__(self, workflow_name: str | None = None):
        super().__init__(
            t("workflow_not_published", workflow_name=workflow_name)
            if workflow_name
            else t("workflow_not_published"),
            msg_key="workflow_not_published",
            workflow_name=workflow_name,
        )


class WorkflowValidationError(WorkflowError):
    """Workflow definition is invalid."""

    def __init__(
        self, message: str | None = None, details: dict[str, Any] | None = None
    ):
        errors = (details or {}).get("errors") or []
        if message is not None:
            super().__init__(message, details, msg_key="validation_error")
            return

        if errors:
            joined = "; ".join(str(e) for e in errors)
            super().__init__(
                t("workflow_validation_failed_with_errors", errors=joined),
                details,
                msg_key="workflow_validation_failed_with_errors",
                errors=joined,
            )
        else:
            super().__init__(t("validation_error"), details, msg_key="validation_error")


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
        super().__init__(
            t("workflow_execution_error"),
            msg_key="workflow_execution_error",
            variable_ref=variable_ref,
        )


class NodeTypeNotFoundError(WorkflowError):
    """Node executor not found for the given type."""

    def __init__(self, node_type: str):
        self.node_type = node_type
        super().__init__(
            t("workflow_execution_error"),
            msg_key="workflow_execution_error",
            node_type=node_type,
        )


class ExecutionTimeoutError(WorkflowError):
    """Workflow or node execution timed out."""

    def __init__(self, timeout_seconds: int | None = None):
        super().__init__(
            t("request_timeout"),
            msg_key="request_timeout",
            timeout_seconds=timeout_seconds,
        )


class ExecutionCancelledError(WorkflowError):
    """Workflow execution was cancelled."""

    def __init__(self):
        super().__init__(t("workflow_run_cancelled"), msg_key="workflow_run_cancelled")


class CyclicDependencyError(WorkflowError):
    """Workflow contains cyclic dependencies."""

    pass


class MaxDepthExceededError(WorkflowError):
    """Maximum sub-workflow depth exceeded."""

    def __init__(self, max_depth: int, current_depth: int):
        self.max_depth = max_depth
        self.current_depth = current_depth
        super().__init__(
            t("workflow_execution_error"),
            msg_key="workflow_execution_error",
            max_depth=max_depth,
            current_depth=current_depth,
        )
