"""
Tool execution utilities for chat.
"""

import json
from typing import Any

from app.models.agent import Agent
from app.models.tool import Tool
from app.llm.tools.executors import execute_http_tool as shared_execute_http_tool
from app.llm.tools.mcp_client import execute_mcp_tool
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    agent: Agent | None = None,
    tool_timeouts: dict | None = None,
    user: Any = None,
    session_id: str | None = None,
    current_images: list[Any] | None = None,
    conversation_id: Any = None,
) -> Any:
    """Execute a tool call and return the result."""
    tool_timeouts = tool_timeouts or {}

    # Check if it's a built-in tool
    builtin_tools = {
        "get_current_time": _execute_get_current_time,
        "get_weather": _execute_get_weather,
    }

    if tool_name in builtin_tools:
        return await builtin_tools[tool_name](arguments)

    from app.api.v1.endpoints.chat_tools import (
        execute_tool_call as shared_execute_tool_call,
    )

    return await shared_execute_tool_call(
        tool_name,
        arguments,
        agent=agent,
        tool_timeouts=tool_timeouts,
        user=user,
        session_id=session_id,
        current_images=current_images,
        conversation_id=conversation_id,
    )


async def execute_http_tool(tool: Tool, arguments: dict, timeout: float = 30.0) -> str:
    """Execute an HTTP tool."""
    result = await shared_execute_http_tool(
        http_config=tool.http_config,
        arguments=arguments,
        credentials=tool.credentials or None,
        timeout=timeout,
    )
    return json.dumps(result, ensure_ascii=False)


async def execute_code_tool(tool: Tool, arguments: dict, timeout: float = 60.0) -> str:
    """Execute a code tool in sandbox."""
    job = compile_code_config_job(
        code_config=tool.code_config or {},
        params=arguments,
        timeout=timeout,
        source=SandboxJobSource.CHAT,
    )
    result = await sandbox_gateway.submit_and_wait(
        job,
        timeout_seconds=job.limits.timeout_seconds + 5,
    )
    return json.dumps(
        {
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        ensure_ascii=False,
    )


async def execute_mcp_tool_call(
    tool: Tool, arguments: dict, timeout: float = 60.0
) -> str:
    """Execute an MCP tool."""
    result = await execute_mcp_tool(
        mcp_config=tool.mcp_config,
        tool_name=tool.name,
        arguments=arguments,
        timeout=timeout,
    )
    return json.dumps(
        {
            "success": result.success,
            "result": result.result,
            "error": result.error,
        },
        ensure_ascii=False,
    )


async def _execute_get_current_time(arguments: dict) -> str:
    """Built-in tool: Get current time."""
    from datetime import datetime

    timezone = arguments.get("timezone", "UTC")
    current_time = datetime.now().isoformat()

    return json.dumps(
        {"timezone": timezone, "current_time": current_time, "success": True}
    )


async def _execute_get_weather(arguments: dict) -> str:
    """Built-in tool: Get weather (mock implementation)."""
    location = arguments.get("location", "Unknown")

    return json.dumps(
        {
            "location": location,
            "temperature": "22°C",
            "condition": "Sunny",
            "humidity": "60%",
            "success": True,
        }
    )
