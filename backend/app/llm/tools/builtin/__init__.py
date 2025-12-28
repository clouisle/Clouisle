"""
内置工具模块

提供系统预置的工具，如时间获取、网页搜索、计算器等。
"""

from .time import register_time_tools
from .calculator import register_calculator_tools
from .web_search import register_web_search_tools


def register_all_builtin_tools() -> None:
    """注册所有内置工具"""
    register_time_tools()
    register_calculator_tools()
    register_web_search_tools()


__all__ = [
    "register_all_builtin_tools",
    "register_time_tools",
    "register_calculator_tools",
    "register_web_search_tools",
]
