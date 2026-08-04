"""
Configuration utilities for chat.
"""

from app.core.config import settings
from app.models.agent import Agent


def _has_tool_runtime(agent: Agent) -> bool:
    return bool(
        agent.tools_config
        or agent.enable_memory
        or agent.enable_image_generation
        or agent.enable_video_generation
    )


def get_streaming_config(agent: Agent) -> dict:
    """Get streaming configuration from agent or use defaults."""
    config = agent.streaming_config or {}

    global_timeout_default = (
        settings.STREAM_GLOBAL_TIMEOUT_WITH_TOOLS
        if _has_tool_runtime(agent)
        else settings.STREAM_GLOBAL_TIMEOUT
    )

    return {
        "global_timeout": config.get("global_timeout", global_timeout_default),
        "heartbeat_interval": config.get(
            "heartbeat_interval", settings.STREAM_HEARTBEAT_INTERVAL
        ),
        "idle_timeout": config.get("idle_timeout", settings.STREAM_IDLE_TIMEOUT),
        "tool_timeouts": {
            "http": config.get("tool_timeouts", {}).get(
                "http", settings.STREAM_TOOL_TIMEOUT_HTTP
            ),
            "code": config.get("tool_timeouts", {}).get(
                "code", settings.STREAM_TOOL_TIMEOUT_CODE
            ),
            "mcp": config.get("tool_timeouts", {}).get(
                "mcp", settings.STREAM_TOOL_TIMEOUT_MCP
            ),
            "download": config.get("tool_timeouts", {}).get(
                "download", settings.STREAM_TOOL_TIMEOUT_DOWNLOAD
            ),
        },
    }
