import pytest

from app.services.workflow import errors
from app.services.workflow.errors import (
    ExecutionCancelledError,
    WorkflowError,
    WorkflowValidationError,
    get_public_workflow_error_key,
    translate_public_workflow_error,
)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, "workflow_execution_error"),
        ("request timed out", "request_timeout"),
        ("Run cancelled by user", "workflow_run_cancelled"),
        ("Workflow validation failed", "validation_error"),
        ("sub-workflow unavailable", "workflow_execution_error"),
        ("unexpected internal detail", None),
    ],
)
def test_get_public_workflow_error_key_maps_known_messages(
    error, expected, monkeypatch
):
    monkeypatch.setattr(errors, "has_translation", lambda message: False)

    assert get_public_workflow_error_key(error) == expected


def test_get_public_workflow_error_key_preserves_translated_and_explicit_keys(
    monkeypatch,
):
    monkeypatch.setattr(
        errors, "has_translation", lambda message: message == "known_key"
    )

    assert get_public_workflow_error_key("known_key") == "known_key"
    assert (
        get_public_workflow_error_key(WorkflowError("ignored", msg_key="explicit_key"))
        == "explicit_key"
    )


def test_translate_public_workflow_error_uses_explicit_keys_and_safe_messages(
    monkeypatch,
):
    translations = []
    monkeypatch.setattr(
        errors, "t", lambda key, **kwargs: translations.append((key, kwargs)) or key
    )
    monkeypatch.setattr(errors, "has_translation", lambda message: False)
    monkeypatch.setattr(
        errors, "is_safe_user_visible_error", lambda message: message == "safe detail"
    )

    assert (
        translate_public_workflow_error(
            WorkflowError("ignored", msg_key="custom", value=1)
        )
        == "custom"
    )
    assert translations == [("custom", {"value": 1})]
    assert translate_public_workflow_error("safe detail") == "safe detail"
    assert (
        translate_public_workflow_error("private detail") == "workflow_execution_error"
    )


def test_workflow_error_subclasses_set_public_error_keys(monkeypatch):
    monkeypatch.setattr(errors, "t", lambda key, **kwargs: key)

    assert WorkflowValidationError().msg_key == "validation_error"
    assert (
        WorkflowValidationError(details={"errors": ["missing input"]}).msg_key
        == "workflow_validation_failed_with_errors"
    )
    assert ExecutionCancelledError().msg_key == "workflow_run_cancelled"
