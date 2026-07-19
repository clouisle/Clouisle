from datetime import datetime, timezone

import pytest

from app.core import timezone as timezone_utils
from app.services import error_messages


def test_timezone_converts_naive_and_aware_datetimes(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")
    utc_time = datetime(2026, 7, 20, 0, 30, tzinfo=timezone.utc)

    assert timezone_utils.to_local(utc_time).isoformat() == "2026-07-20T08:30:00+08:00"
    assert timezone_utils.to_local(datetime(2026, 7, 20, 0, 30)).isoformat() == (
        "2026-07-20T08:30:00+08:00"
    )
    assert timezone_utils.to_utc(datetime(2026, 7, 20, 8, 30)).isoformat() == (
        "2026-07-20T00:30:00+00:00"
    )
    assert timezone_utils.to_local(None) is None
    assert timezone_utils.to_utc(None) is None


def test_timezone_formats_and_exposes_configured_now(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "UTC")
    utc_time = datetime(2026, 7, 20, 8, 30, tzinfo=timezone.utc)

    assert timezone_utils.get_timezone().key == "UTC"
    assert timezone_utils.now().tzinfo.key == "UTC"
    assert timezone_utils.now_utc().tzinfo == timezone.utc
    assert timezone_utils.format_datetime(utc_time, "%H:%M") == "08:30"
    assert timezone_utils.format_datetime(None) == ""


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("The request was rejected", True),
        (None, False),
        ("  ", False),
        ("validation.error", False),
        ("Traceback: internal failure", False),
        ('File "/tmp/secret", line 1', False),
        ("line one\nline two", False),
        ("x" * 401, False),
    ],
)
def test_error_message_safety_filters_internal_and_unsafe_content(message, expected):
    assert error_messages.is_safe_user_visible_error(message) is expected


def test_error_message_resolution_prefers_translations_and_safe_text(monkeypatch):
    monkeypatch.setattr(
        error_messages, "has_translation", lambda value: value == "known.key"
    )
    monkeypatch.setattr(error_messages, "t", lambda key: f"translated:{key}")

    assert (
        error_messages.resolve_user_visible_error("known.key") == "translated:known.key"
    )
    assert (
        error_messages.resolve_user_visible_error("The request was rejected")
        == "The request was rejected"
    )
    assert error_messages.resolve_user_visible_error("Traceback: private") == (
        "translated:tool_execution_failed"
    )
    assert error_messages.resolve_user_visible_error(
        None, fallback_key="fallback.key"
    ) == ("translated:fallback.key")
