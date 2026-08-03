"""Tests for public workflow error handling."""

from app.core.i18n import t
from app.services.workflow.errors import (
    CyclicDependencyError,
    ExecutionCancelledError,
    ExecutionTimeoutError,
    MaxDepthExceededError,
    NodeExecutionError,
    NodeTypeNotFoundError,
    VariableNotFoundError,
    WorkflowError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
    WorkflowValidationError,
    get_public_workflow_error_key,
    translate_public_workflow_error,
)


def test_workflow_error_preserves_message_details_and_kwargs():
    error = WorkflowError("broken", {"node": "start"}, code="E1")

    assert str(error) == "broken"
    assert error.message == "broken"
    assert error.details == {"node": "start"}
    assert error.kwargs == {"code": "E1"}


def test_public_error_key_handles_workflow_errors_and_message_boundaries():
    assert (
        get_public_workflow_error_key(ExecutionCancelledError())
        == "workflow_run_cancelled"
    )
    assert get_public_workflow_error_key(None) == "workflow_execution_error"
    assert get_public_workflow_error_key("  ") == "workflow_execution_error"
    assert get_public_workflow_error_key("Request timed out") == "request_timeout"
    assert (
        get_public_workflow_error_key("workflow validation failed: bad graph")
        == "validation_error"
    )
    assert (
        get_public_workflow_error_key("sub-workflow failed")
        == "workflow_execution_error"
    )
    assert get_public_workflow_error_key("internal failure") is None


def test_public_error_key_detects_cancelled_message_string():
    assert (
        get_public_workflow_error_key("operation cancelled unexpectedly")
        == "workflow_run_cancelled"
    )


def test_translate_public_error_uses_message_key_and_hides_unsafe_messages():
    error = WorkflowError("internal", msg_key="request_timeout")

    assert translate_public_workflow_error(error) == t("request_timeout")
    assert translate_public_workflow_error("A readable error") == "A readable error"
    assert translate_public_workflow_error('File "/tmp/secret.py", line 1') == t(
        "workflow_execution_error"
    )


def test_workflow_not_published_message_and_key_include_optional_name():
    named = WorkflowNotPublishedError("Daily sync")
    unnamed = WorkflowNotPublishedError()

    assert named.message == t("workflow_not_published", workflow_name="Daily sync")
    assert named.msg_key == unnamed.msg_key == "workflow_not_published"
    assert named.kwargs == {"workflow_name": "Daily sync"}
    assert unnamed.kwargs == {"workflow_name": None}


def test_validation_error_uses_supplied_message_or_detail_errors():
    explicit = WorkflowValidationError("Invalid input", {"errors": ["ignored"]})
    detailed = WorkflowValidationError(details={"errors": ["missing start", 42]})
    default = WorkflowValidationError()

    assert explicit.message == "Invalid input"
    assert explicit.msg_key == "validation_error"
    assert detailed.message == t(
        "workflow_validation_failed_with_errors", errors="missing start; 42"
    )
    assert detailed.kwargs == {"errors": "missing start; 42"}
    assert default.message == t("validation_error")


def test_contextual_errors_preserve_context_and_public_keys():
    node_error = NodeExecutionError("failed", "node-1", "llm", {"attempt": 2})
    variable_error = VariableNotFoundError("{{start.name}}")
    type_error = NodeTypeNotFoundError("custom")
    timeout_error = ExecutionTimeoutError(30)
    depth_error = MaxDepthExceededError(3, 4)

    assert node_error.node_id == "node-1"
    assert node_error.node_type == "llm"
    assert node_error.details == {"attempt": 2}
    assert variable_error.variable_ref == "{{start.name}}"
    assert type_error.node_type == "custom"
    assert timeout_error.kwargs == {"timeout_seconds": 30}
    assert depth_error.max_depth == 3
    assert depth_error.current_depth == 4
    assert get_public_workflow_error_key(variable_error) == "workflow_execution_error"
    assert get_public_workflow_error_key(timeout_error) == "request_timeout"


def test_plain_workflow_error_subclasses_keep_base_behavior():
    not_found = WorkflowNotFoundError("not found")
    cyclic = CyclicDependencyError("cycle", {"nodes": ["a", "b"]})

    assert not_found.message == "not found"
    assert cyclic.details == {"nodes": ["a", "b"]}
