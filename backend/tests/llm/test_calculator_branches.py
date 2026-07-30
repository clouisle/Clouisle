import math

import pytest

from app.llm.tools.builtin import calculator


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("7 + 3", 10),
        ("7 - 3", 4),
        ("7 * 3", 21),
        ("7 / 2", 3.5),
        ("7 // 2", 3),
        ("7 % 3", 1),
        ("2**10", 1024),
        ("-2", -2),
        ("+2", 2),
        ("abs(-2)", 2),
        ("round(1.234, 2)", 1.23),
        ("min(3, 1)", 1),
        ("max(3, 1)", 3),
        ("sqrt(9)", 3),
        ("sin(pi / 2)", 1),
        ("cos(0)", 1),
        ("tan(0)", 0),
        ("log(e)", 1),
        ("log10(100)", 2),
        ("log2(8)", 3),
        ("exp(0)", 1),
        ("pow(2, 3)", 8),
        ("floor(1.9)", 1),
        ("ceil(1.1)", 2),
        ("pi", math.pi),
        ("e", math.e),
        ("pi()", math.pi),
    ],
)
def test_safe_eval_allows_documented_operations_and_functions(expression, expected):
    assert calculator.safe_eval(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("'text'", "Unsupported constant type"),
        ("2 @ 3", "Unsupported operator: MatMult"),
        ("~1", "Unsupported unary operator: Invert"),
        ("math.sqrt(4)", "Only simple function calls are supported"),
        ("open(1)", "Unsupported function: open"),
        ("pi(1)", "pi is a constant, not a function"),
        ("abs", "Undefined variable: abs"),
        ("missing", "Undefined variable: missing"),
        ("[1, 2]", "Unsupported syntax: List"),
        ("2**1001", "Exponent too large"),
        ("(", "Invalid expression syntax"),
    ],
)
def test_safe_eval_rejects_unsafe_or_invalid_expressions(expression, message):
    with pytest.raises(ValueError, match=message):
        calculator.safe_eval(expression)


def test_allowed_function_argument_errors_propagate():
    with pytest.raises(TypeError, match="sum.*at least 1"):
        calculator.safe_eval("sum()")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expression", "expected"),
    [("6 * 7", 42), ("4 / 2", 2), ("1 / 3", 0.3333333333)],
)
async def test_calculate_formats_integer_and_fractional_results(expression, expected):
    assert await calculator.calculate(expression) == {
        "expression": expression,
        "result": expected,
        "success": True,
    }


@pytest.mark.asyncio
async def test_calculate_normalizes_evaluation_errors(monkeypatch):
    monkeypatch.setattr(calculator, "t", lambda key: f"translated:{key}")

    assert await calculator.calculate("1 / 0") == {
        "expression": "1 / 0",
        "error": "translated:tool_execution_failed",
        "success": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (1, "KM", "m", 1000),
        (1, "kg", "g", 1000),
        (1, "ha", "m2", 10000),
        (1, "l", "ml", 1000),
        (1, "h", "min", 60),
        (1, "mb", "kb", 1024),
    ],
)
async def test_unit_convert_handles_each_scaled_unit_category(
    value, from_unit, to_unit, expected
):
    result = await calculator.unit_convert(value, from_unit, to_unit)

    assert result["result"] == expected
    assert result["success"] is True
    assert result["from_unit"] == from_unit.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (0, "c", "f", 32),
        (32, "f", "c", 0),
        (0, "c", "k", 273.15),
        (273.15, "k", "c", 0),
        (32, "f", "k", 273.15),
        (273.15, "k", "f", 32),
        (12, "c", "c", 12),
    ],
)
async def test_unit_convert_handles_temperature_paths(
    value, from_unit, to_unit, expected
):
    result = await calculator.unit_convert(value, from_unit, to_unit)

    assert result["result"] == pytest.approx(expected)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_unit_convert_rejects_unknown_or_cross_category_units(monkeypatch):
    monkeypatch.setattr(
        calculator,
        "t",
        lambda key, **values: f"{key}:{values['from_unit']}:{values['to_unit']}",
    )

    assert await calculator.unit_convert(1, "m", "kg") == {
        "value": 1,
        "from_unit": "m",
        "to_unit": "kg",
        "error": "unit_convert_unsupported_units:m:kg",
        "success": False,
    }
