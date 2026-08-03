import math
import time
from datetime import datetime, timezone

import pytest

from app.llm.tools.builtin.calculator import calculate, safe_eval, unit_convert
from app.llm.tools.builtin.time import format_datetime


def test_safe_eval_supports_arithmetic_functions_and_constants():
    assert safe_eval("2 + 3 * 4") == 14
    assert safe_eval("sqrt(16) + sin(pi / 2)") == 5


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').getcwd()",
        "(1).__class__",
        "2 ** 1001",
        "'not a number'",
    ],
)
def test_safe_eval_rejects_unsafe_or_unsupported_expressions(expression):
    with pytest.raises(ValueError):
        safe_eval(expression)


@pytest.mark.anyio
async def test_calculate_normalizes_float_results_and_hides_failures():
    assert await calculate("0.1 + 0.2") == {
        "expression": "0.1 + 0.2",
        "result": 0.3,
        "success": True,
    }

    failure = await calculate("1 / 0")
    assert failure["expression"] == "1 / 0"
    assert failure["success"] is False
    assert failure["error"]
    assert "division" not in failure["error"].lower()


@pytest.mark.anyio
async def test_unit_convert_handles_temperature_and_case_insensitive_units():
    assert (await unit_convert(32, "F", "c"))["result"] == 0
    assert (await unit_convert(1, "KM", "m"))["result"] == 1000


@pytest.mark.anyio
async def test_unit_convert_rejects_incompatible_units():
    result = await unit_convert(1, "kg", "m")

    assert result["success"] is False
    assert result["from_unit"] == "kg"
    assert result["to_unit"] == "m"
    assert result["error"]


@pytest.mark.anyio
async def test_format_datetime_converts_fixed_timestamp_between_timezones():
    utc = await format_datetime(0, "%Y-%m-%d %H:%M:%S %z", "UTC")
    shanghai = await format_datetime(0, "%Y-%m-%d %H:%M:%S %z", "Asia/Shanghai")

    assert utc == {
        "formatted": "1970-01-01 00:00:00 +0000",
        "timezone": "UTC",
        "timestamp": 0,
    }
    assert shanghai == {
        "formatted": "1970-01-01 08:00:00 +0800",
        "timezone": "Asia/Shanghai",
        "timestamp": 0,
    }


@pytest.mark.anyio
async def test_format_datetime_falls_back_to_utc_for_unknown_timezone():
    result = await format_datetime(0, "%Y-%m-%d %H:%M:%S %z", "Mars/Olympus")

    assert result == {
        "formatted": "1970-01-01 00:00:00 +0000",
        "timezone": "UTC",
        "timestamp": 0,
    }


@pytest.mark.anyio
async def test_format_datetime_uses_current_time_when_timestamp_omitted():
    before = int(time.time())
    result = await format_datetime(None, "%Y", "UTC")
    after = int(time.time())

    assert result["timezone"] == "UTC"
    assert before <= result["timestamp"] <= after
    expected_year = datetime.fromtimestamp(result["timestamp"], tz=timezone.utc).year
    assert int(result["formatted"]) == expected_year


def test_safe_eval_math_constant_matches_stdlib():
    assert safe_eval("pi") == math.pi
