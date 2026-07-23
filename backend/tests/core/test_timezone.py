from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from app.core import timezone as timezone_utils


def test_get_timezone_uses_configuration_and_rejects_unknown_zone(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")
    assert timezone_utils.get_timezone() == ZoneInfo("Asia/Shanghai")

    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Invalid/Timezone")
    with pytest.raises(ZoneInfoNotFoundError):
        timezone_utils.get_timezone()


def test_clocks_return_aware_datetimes(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.now().tzinfo == ZoneInfo("Asia/Shanghai")
    assert timezone_utils.now_utc().tzinfo is timezone.utc


def test_to_local_handles_none_naive_and_dst_boundary(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "America/New_York")

    assert timezone_utils.to_local(None) is None
    assert timezone_utils.to_local(datetime(2026, 1, 1, 5)).isoformat() == (
        "2026-01-01T00:00:00-05:00"
    )
    assert (
        timezone_utils.to_local(
            datetime(2026, 3, 8, 7, tzinfo=timezone.utc)
        ).isoformat()
        == "2026-03-08T03:00:00-04:00"
    )


def test_to_utc_handles_none_naive_and_aware_values(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.to_utc(None) is None
    assert timezone_utils.to_utc(datetime(2026, 1, 1, 8)) == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    assert timezone_utils.to_utc(
        datetime(2026, 1, 1, 8, tzinfo=ZoneInfo("Asia/Shanghai"))
    ) == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_format_datetime_handles_none_and_custom_format(monkeypatch):
    monkeypatch.setattr(timezone_utils.settings, "TIMEZONE", "Asia/Shanghai")

    assert timezone_utils.format_datetime(None) == ""
    assert (
        timezone_utils.format_datetime(
            datetime(2026, 1, 1, tzinfo=timezone.utc), "%Y/%m/%d %H:%M %z"
        )
        == "2026/01/01 08:00 +0800"
    )
