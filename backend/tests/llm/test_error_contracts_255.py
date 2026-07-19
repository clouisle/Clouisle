from __future__ import annotations

import pytest

from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InsufficientQuotaError,
    InvalidRequestError,
    LLMError,
    ModelDisabledError,
    ModelNotFoundError,
    ProviderError,
    QuotaExceededError,
    RateLimitError,
    TaskNotFoundError,
    TimeoutError,
    UnsupportedOperationError,
)
from app.services import error_messages


def test_llm_error_preserves_exception_and_serialization_contract():
    details = {"request_id": "req-1"}
    error = LLMError(
        "Provider unavailable",
        code="upstream_error",
        provider="openai",
        model="gpt-test",
        details=details,
    )

    assert str(error) == "Provider unavailable"
    assert error.args == ("Provider unavailable",)
    assert error.to_dict() == {
        "code": "upstream_error",
        "message": "Provider unavailable",
        "provider": "openai",
        "model": "gpt-test",
        "details": details,
    }


@pytest.mark.parametrize(
    ("error", "code", "details", "attributes"),
    [
        (AuthenticationError(provider="p", model="m"), "authentication_error", {}, {}),
        (
            RateLimitError(retry_after=30, provider="p", model="m"),
            "rate_limit_error",
            {"retry_after": 30},
            {"retry_after": 30},
        ),
        (
            ContextLengthError(
                max_tokens=4096, actual_tokens=5000, provider="p", model="m"
            ),
            "context_length_error",
            {"max_tokens": 4096, "actual_tokens": 5000},
            {"max_tokens": 4096, "actual_tokens": 5000},
        ),
        (
            ContentFilterError(filter_type="violence", provider="p", model="m"),
            "content_filter_error",
            {"filter_type": "violence"},
            {"filter_type": "violence"},
        ),
        (ModelNotFoundError(model="m"), "model_not_found", {}, {}),
        (ModelDisabledError(model="m"), "model_disabled", {}, {}),
        (
            ProviderError(status_code=503, provider="p", model="m"),
            "provider_error",
            {"status_code": 503},
            {"status_code": 503},
        ),
        (
            TimeoutError(timeout=2.5, provider="p", model="m"),
            "timeout_error",
            {"timeout": 2.5},
            {"timeout": 2.5},
        ),
        (
            InvalidRequestError(field="temperature", provider="p", model="m"),
            "invalid_request",
            {"field": "temperature"},
            {"field": "temperature"},
        ),
        (
            InsufficientQuotaError(quota_type="tokens", provider="p", model="m"),
            "insufficient_quota",
            {"quota_type": "tokens"},
            {"quota_type": "tokens"},
        ),
        (
            QuotaExceededError(quota_type="tokens", team_id="team-1", model="m"),
            "quota_exceeded",
            {"quota_type": "tokens", "team_id": "team-1"},
            {"quota_type": "tokens", "team_id": "team-1"},
        ),
        (
            TaskNotFoundError(task_id="task-1", provider="p"),
            "task_not_found",
            {"task_id": "task-1"},
            {"task_id": "task-1"},
        ),
        (
            UnsupportedOperationError(operation="video", provider="p", model="m"),
            "unsupported_operation",
            {"operation": "video"},
            {"operation": "video"},
        ),
    ],
)
def test_specialized_errors_expose_code_metadata_and_attributes(
    error: LLMError,
    code: str,
    details: dict[str, object],
    attributes: dict[str, object],
):
    serialized = error.to_dict()

    assert isinstance(error, LLMError)
    assert serialized["code"] == code
    assert serialized["details"] == details
    assert serialized["provider"] == getattr(error, "provider")
    assert serialized["model"] == getattr(error, "model")
    assert str(error) == error.message
    for name, value in attributes.items():
        assert getattr(error, name) == value


@pytest.mark.parametrize(
    ("error", "attribute"),
    [
        (RateLimitError(retry_after=0), "retry_after"),
        (ProviderError(status_code=0), "status_code"),
        (TimeoutError(timeout=0), "timeout"),
        (ContentFilterError(filter_type=""), "filter_type"),
    ],
)
def test_optional_zero_or_empty_metadata_remains_on_attribute_but_not_details(
    error: LLMError, attribute: str
):
    assert getattr(error, attribute) in (0, "")
    assert error.details == {}


def test_quota_exceeded_keeps_explicit_null_metadata():
    error = QuotaExceededError()

    assert error.details == {"quota_type": None, "team_id": None}


@pytest.mark.parametrize(
    "message",
    [
        None,
        "",
        "   ",
        "tool.execution_failed",
        "Traceback: secret",
        'File "/tmp/secret.py", line 7',
        "at worker.js:12:4",
        "x" * 401,
        "first line\nsecond line",
    ],
)
def test_resolve_user_visible_error_replaces_unsafe_messages(
    monkeypatch: pytest.MonkeyPatch, message: str | None
):
    monkeypatch.setattr(error_messages, "has_translation", lambda _message: False)
    monkeypatch.setattr(error_messages, "t", lambda key: f"translated:{key}")

    assert (
        error_messages.resolve_user_visible_error(message, fallback_key="safe_fallback")
        == "translated:safe_fallback"
    )


def test_resolve_user_visible_error_translates_known_key(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        error_messages, "has_translation", lambda message: message == "known.error"
    )
    monkeypatch.setattr(error_messages, "t", lambda key: f"translated:{key}")

    assert (
        error_messages.resolve_user_visible_error("  known.error  ")
        == "translated:known.error"
    )


@pytest.mark.parametrize("message", ["Provider temporarily unavailable", "x" * 400])
def test_resolve_user_visible_error_preserves_safe_bounded_messages(
    monkeypatch: pytest.MonkeyPatch, message: str
):
    monkeypatch.setattr(error_messages, "has_translation", lambda _message: False)

    assert error_messages.resolve_user_visible_error(f"  {message}  ") == message
