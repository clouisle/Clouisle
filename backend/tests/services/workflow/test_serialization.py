"""Tests for the workflow runtime serialization layer."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.workflow.serialization import dumps_value, loads_value


class TestRoundTrip:
    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "hello",
            "中文 测试 🎉",
            0,
            1,
            -1,
            1.5,
            True,
            False,
            [],
            {},
            [1, 2, 3],
            {"a": 1, "b": "x"},
            {"nested": {"a": [1, {"b": "c"}], "d": None}},
            [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}],
            b"binary-bytes-payload",
        ],
    )
    def test_round_trip(self, value):
        encoded = dumps_value(value)
        assert isinstance(encoded, str)
        assert encoded.startswith("mp1:")
        assert loads_value(encoded) == value

    def test_round_trip_accepts_bytes_input(self):
        encoded = dumps_value({"a": 1})
        assert loads_value(encoded.encode("ascii")) == {"a": 1}

    def test_loads_none_or_empty(self):
        assert loads_value(None) is None
        assert loads_value("") is None
        assert loads_value(b"") is None


class TestNormalization:
    def test_datetime_normalized_to_isoformat(self):
        dt = datetime(2026, 4, 24, 10, 30, 0)
        assert loads_value(dumps_value({"ts": dt})) == {"ts": dt.isoformat()}

    def test_date_normalized_to_isoformat(self):
        d = date(2026, 4, 24)
        assert loads_value(dumps_value({"d": d})) == {"d": d.isoformat()}

    def test_uuid_normalized_to_str(self):
        u = uuid4()
        assert loads_value(dumps_value(u)) == str(u)

    def test_decimal_normalized_to_float(self):
        assert loads_value(dumps_value(Decimal("1.5"))) == 1.5

    def test_set_normalized_to_list(self):
        out = loads_value(dumps_value({1, 2, 3}))
        assert sorted(out) == [1, 2, 3]

    def test_unsupported_type_raises(self):
        class Custom:
            pass

        with pytest.raises(TypeError):
            dumps_value(Custom())


class TestFraming:
    def test_missing_prefix_raises(self):
        with pytest.raises(ValueError):
            loads_value("not-a-valid-frame")

    def test_corrupted_payload_raises(self):
        with pytest.raises(Exception):
            loads_value("mp1:not-valid-base64-or-msgpack!!!")
