"""
计算器工具

提供数学计算功能，支持基本运算和数学函数。
"""

import ast
import math
import operator
from typing import Any, Callable

from app.core.i18n import t
from ..registry import tool_registry, ToolParameter


# 安全的二元运算符映射
SAFE_BINARY_OPERATORS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# 安全的一元运算符映射
SAFE_UNARY_OPERATORS: dict[type, Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 安全的数学函数
SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "pow": pow,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
}


class SafeEvaluator(ast.NodeVisitor):
    """安全的表达式求值器"""

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_Num(self, node: ast.Num) -> Any:
        # 兼容旧版本 Python
        return node.n

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        op_type = type(node.op)
        if op_type not in SAFE_BINARY_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")

        left = self.visit(node.left)
        right = self.visit(node.right)

        # 防止大数幂运算
        if op_type == ast.Pow and isinstance(right, (int, float)) and right > 1000:
            raise ValueError("Exponent too large")

        return SAFE_BINARY_OPERATORS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        op_type = type(node.op)
        if op_type not in SAFE_UNARY_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")

        operand = self.visit(node.operand)
        return SAFE_UNARY_OPERATORS[op_type](operand)

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are supported")

        func_name = node.func.id
        if func_name not in SAFE_FUNCTIONS:
            raise ValueError(f"Unsupported function: {func_name}")

        func = SAFE_FUNCTIONS[func_name]

        # 处理常量（如 pi, e）
        if not callable(func):
            if node.args:
                raise ValueError(f"{func_name} is a constant, not a function")
            return func

        args = [self.visit(arg) for arg in node.args]
        return func(*args)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in SAFE_FUNCTIONS:
            value = SAFE_FUNCTIONS[node.id]
            if not callable(value):
                return value
        raise ValueError(f"Undefined variable: {node.id}")

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"Unsupported syntax: {type(node).__name__}")


def safe_eval(expression: str) -> float | int:
    """
    安全地求值数学表达式

    Args:
        expression: 数学表达式字符串

    Returns:
        计算结果

    Raises:
        ValueError: 表达式无效或不安全
    """
    try:
        tree = ast.parse(expression, mode="eval")
        evaluator = SafeEvaluator()
        return evaluator.visit(tree)
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}") from e


async def calculate(expression: str) -> dict:
    """
    计算数学表达式

    Args:
        expression: 数学表达式，支持 +, -, *, /, //, %, ** 运算符
                   以及 sqrt, sin, cos, tan, log, exp, abs, round, min, max, floor, ceil 等函数
                   以及常量 pi, e

    Returns:
        包含结果的字典
    """
    try:
        result = safe_eval(expression)

        # 格式化结果
        if isinstance(result, float):
            # 处理浮点数精度问题
            if result == int(result):
                result = int(result)
            else:
                result = round(result, 10)

        return {
            "expression": expression,
            "result": result,
            "success": True,
        }
    except Exception as e:
        return {
            "expression": expression,
            "error": t("tool_execution_failed"),
            "success": False,
        }


async def unit_convert(
    value: float,
    from_unit: str,
    to_unit: str,
) -> dict:
    """
    单位转换

    Args:
        value: 数值
        from_unit: 源单位
        to_unit: 目标单位

    Returns:
        转换结果
    """
    # 单位转换表（转换为基准单位的系数）
    conversions = {
        # 长度 (基准: 米)
        "length": {
            "m": 1,
            "km": 1000,
            "cm": 0.01,
            "mm": 0.001,
            "mi": 1609.344,
            "yd": 0.9144,
            "ft": 0.3048,
            "in": 0.0254,
        },
        # 重量 (基准: 千克)
        "weight": {
            "kg": 1,
            "g": 0.001,
            "mg": 0.000001,
            "lb": 0.453592,
            "oz": 0.0283495,
            "t": 1000,
        },
        # 温度 (特殊处理)
        "temperature": {"c", "f", "k"},
        # 面积 (基准: 平方米)
        "area": {
            "m2": 1,
            "km2": 1000000,
            "cm2": 0.0001,
            "ha": 10000,
            "acre": 4046.86,
            "ft2": 0.092903,
        },
        # 体积 (基准: 升)
        "volume": {
            "l": 1,
            "ml": 0.001,
            "m3": 1000,
            "gal": 3.78541,
            "qt": 0.946353,
            "pt": 0.473176,
            "cup": 0.236588,
        },
        # 时间 (基准: 秒)
        "time": {
            "s": 1,
            "ms": 0.001,
            "min": 60,
            "h": 3600,
            "d": 86400,
            "wk": 604800,
        },
        # 数据 (基准: 字节)
        "data": {
            "b": 1,
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
        },
    }

    from_unit = from_unit.lower()
    to_unit = to_unit.lower()

    # 温度特殊处理
    if (
        from_unit in conversions["temperature"]
        and to_unit in conversions["temperature"]
    ):
        if from_unit == "c" and to_unit == "f":
            result = value * 9 / 5 + 32
        elif from_unit == "f" and to_unit == "c":
            result = (value - 32) * 5 / 9
        elif from_unit == "c" and to_unit == "k":
            result = value + 273.15
        elif from_unit == "k" and to_unit == "c":
            result = value - 273.15
        elif from_unit == "f" and to_unit == "k":
            result = (value - 32) * 5 / 9 + 273.15
        elif from_unit == "k" and to_unit == "f":
            result = (value - 273.15) * 9 / 5 + 32
        else:
            result = value

        return {
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "result": round(result, 6),
            "success": True,
        }

    # 查找单位类型
    unit_type = None
    for category, units in conversions.items():
        if category == "temperature":
            continue
        if isinstance(units, dict) and from_unit in units and to_unit in units:
            unit_type = category
            break

    if not unit_type:
        return {
            "value": value,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "error": t(
                "unit_convert_unsupported_units",
                from_unit=from_unit,
                to_unit=to_unit,
            ),
            "success": False,
        }

    units = conversions[unit_type]
    # 转换: 源单位 -> 基准单位 -> 目标单位
    assert isinstance(units, dict)
    base_value = value * units[from_unit]
    result = base_value / units[to_unit]

    return {
        "value": value,
        "from_unit": from_unit,
        "to_unit": to_unit,
        "result": round(result, 6),
        "success": True,
    }


def register_calculator_tools() -> None:
    """注册计算器相关工具"""

    tool_registry.register(
        name="calculate",
        description="计算数学表达式。支持基本运算（+, -, *, /, //, %, **）和数学函数（sqrt, sin, cos, tan, log, exp, abs, round, min, max, floor, ceil）以及常量（pi, e）。",
        parameters=[
            ToolParameter(
                name="expression",
                type="string",
                description="数学表达式，如 '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'",
                required=True,
            ),
        ],
    )(calculate)

    tool_registry.register(
        name="unit_convert",
        description="单位转换。支持长度（m, km, cm, mm, mi, yd, ft, in）、重量（kg, g, mg, lb, oz, t）、温度（c, f, k）、面积（m2, km2, ha, acre）、体积（l, ml, m3, gal）、时间（s, ms, min, h, d, wk）、数据（b, kb, mb, gb, tb）。",
        parameters=[
            ToolParameter(
                name="value",
                type="number",
                description="要转换的数值",
                required=True,
            ),
            ToolParameter(
                name="from_unit",
                type="string",
                description="源单位",
                required=True,
            ),
            ToolParameter(
                name="to_unit",
                type="string",
                description="目标单位",
                required=True,
            ),
        ],
    )(unit_convert)
