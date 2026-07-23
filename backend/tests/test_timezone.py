"""Behavioral tests for configured timezone utilities."""

from datetime import datetime, timezone

from app.core import timezone as timezone_utils


def test_timezone_and_clock_helpers_use_configured_zone(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.get_timezone().key == "Asia/Shanghai"
    assert timezone_utils.now().tzinfo == timezone_utils.get_timezone()
    assert timezone_utils.now_utc().tzinfo == timezone.utc


def test_to_local_handles_none_and_treats_naive_datetime_as_utc(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.to_local(None) is None
    assert timezone_utils.to_local(datetime(2026, 1, 1, 0, 0)) == datetime(
        2026, 1, 1, 8, 0, tzinfo=timezone_utils.get_timezone()
    )


def test_to_utc_handles_none_and_treats_naive_datetime_as_local(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.to_utc(None) is None
    assert timezone_utils.to_utc(datetime(2026, 1, 1, 8, 0)) == datetime(
        2026, 1, 1, 0, 0, tzinfo=timezone.utc
    )


def test_format_datetime_converts_to_local_before_formatting(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.format_datetime(None) == ""
    assert (
        timezone_utils.format_datetime(
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), "%Y-%m-%d %H:%M %z"
        )
        == "2026-01-01 08:00 +0800"
    )
