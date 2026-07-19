from unittest.mock import MagicMock

import pytest

from app.services import error_messages


@pytest.mark.parametrize(
    "message, expected",
    [
        (None, False),
        ("   ", False),
        ("x" * 400, True),
        ("x" * 401, False),
        ("safe message", True),
        ("line one\nline two", False),
        ("tool.execution_failed", False),
        ("Traceback: boom", False),
        ('File "/tmp/app.py", line 2', False),
        ("Exception: boom", True),
        ("at worker.py:2:3", False),
        ("failed in /private/data", False),
        (r"failed in C:\\temp", False),
    ],
)
def test_is_safe_user_visible_error_boundaries(message, expected):
    assert error_messages.is_safe_user_visible_error(message) is expected


def test_resolve_user_visible_error_uses_fallback_for_missing_and_unsafe(monkeypatch):
    translate = MagicMock(side_effect=lambda key: f"translated:{key}")
    monkeypatch.setattr(error_messages, "t", translate)
    monkeypatch.setattr(
        error_messages, "has_translation", MagicMock(return_value=False)
    )

    assert error_messages.resolve_user_visible_error(None) == (
        "translated:tool_execution_failed"
    )
    assert error_messages.resolve_user_visible_error(
        "   ", fallback_key="fallback"
    ) == ("translated:fallback")
    assert error_messages.resolve_user_visible_error("Traceback: secret") == (
        "translated:tool_execution_failed"
    )


def test_resolve_user_visible_error_translates_known_key(monkeypatch):
    translate = MagicMock(return_value="Localized failure")
    has_translation = MagicMock(return_value=True)
    monkeypatch.setattr(error_messages, "t", translate)
    monkeypatch.setattr(error_messages, "has_translation", has_translation)

    assert error_messages.resolve_user_visible_error(" tool.execution_failed ") == (
        "Localized failure"
    )
    has_translation.assert_called_once_with("tool.execution_failed")
    translate.assert_called_once_with("tool.execution_failed")


def test_resolve_user_visible_error_returns_safe_message(monkeypatch):
    translate = MagicMock()
    monkeypatch.setattr(error_messages, "t", translate)
    monkeypatch.setattr(
        error_messages, "has_translation", MagicMock(return_value=False)
    )

    assert error_messages.resolve_user_visible_error("  Provider unavailable  ") == (
        "Provider unavailable"
    )
    translate.assert_not_called()
