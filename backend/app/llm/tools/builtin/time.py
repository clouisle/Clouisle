"""
时间相关工具

提供获取当前时间、日期格式化等功能。
"""

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

from ..registry import tool_registry, ToolParameter


async def get_current_time(timezone_name: str = "UTC") -> dict:
    """
    获取当前时间

    Args:
        timezone_name: 时区名称，如 "UTC", "Asia/Shanghai", "America/New_York"

    Returns:
        包含时间信息的字典
    """
    tz: tzinfo
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
        timezone_name = "UTC"

    now = datetime.now(tz)

    return {
        "timezone": timezone_name,
        "datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timestamp": int(now.timestamp()),
    }


async def format_datetime(
    timestamp: int | None = None,
    format_string: str = "%Y-%m-%d %H:%M:%S",
    timezone_name: str = "UTC",
) -> dict:
    """
    格式化日期时间

    Args:
        timestamp: Unix 时间戳，None 表示当前时间
        format_string: 格式化字符串
        timezone_name: 时区名称

    Returns:
        格式化后的时间字符串
    """
    tz: tzinfo
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
        timezone_name = "UTC"

    if timestamp is None:
        dt = datetime.now(tz)
    else:
        dt = datetime.fromtimestamp(timestamp, tz)

    return {
        "formatted": dt.strftime(format_string),
        "timezone": timezone_name,
        "timestamp": int(dt.timestamp()),
    }


def register_time_tools() -> None:
    """注册时间相关工具"""

    tool_registry.register(
        name="get_current_time",
        description="获取当前时间。返回指定时区的当前日期、时间、星期和时间戳。",
        parameters=[
            ToolParameter(
                name="timezone_name",
                type="string",
                description="时区名称，如 'UTC', 'Asia/Shanghai', 'America/New_York', 'Europe/London'。默认为 UTC。",
                required=False,
                default="UTC",
            ),
        ],
    )(get_current_time)

    tool_registry.register(
        name="format_datetime",
        description="格式化日期时间。将时间戳转换为指定格式的字符串。",
        parameters=[
            ToolParameter(
                name="timestamp",
                type="integer",
                description="Unix 时间戳（秒），不提供则使用当前时间",
                required=False,
            ),
            ToolParameter(
                name="format_string",
                type="string",
                description="Python strftime 格式字符串，如 '%Y-%m-%d %H:%M:%S'",
                required=False,
                default="%Y-%m-%d %H:%M:%S",
            ),
            ToolParameter(
                name="timezone_name",
                type="string",
                description="时区名称，默认为 UTC",
                required=False,
                default="UTC",
            ),
        ],
    )(format_datetime)
