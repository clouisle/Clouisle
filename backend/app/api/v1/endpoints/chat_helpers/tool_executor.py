"""
Tool execution utilities for chat.
"""

import json
from app.core.i18n import t
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

    if tool_name.startswith("skill_"):
        from app.services.skill import SkillService
        from app.services.skill_executor import SkillExecutor

        if not agent:
            return json.dumps(
                {"error": t("agent_context_required_for_skill")}, ensure_ascii=False
            )
        skill, skill_config = await SkillService.resolve_agent_skill_tool(
            agent, tool_name
        )
        result = await SkillExecutor.execute(
            skill=skill,
            arguments=arguments,
            config=skill_config,
            tenant_id=str(agent.team_id) if agent.team_id else None,
        )
        return result.to_chat_payload()

    # Get tool from database
    tool = await Tool.get_or_none(name=tool_name)
    if not tool:
        return json.dumps({"error": t("tool_not_found")}, ensure_ascii=False)

    # Execute based on tool type
    if tool.type == "http":
        timeout = tool_timeouts.get("http", 30.0)
        return await execute_http_tool(tool, arguments, timeout)
    elif tool.type == "code":
        timeout = tool_timeouts.get("code", 60.0)
        return await execute_code_tool(tool, arguments, timeout)
    elif tool.type == "mcp":
        timeout = tool_timeouts.get("mcp", 60.0)
        return await execute_mcp_tool_call(tool, arguments, timeout)
    else:
        return json.dumps(
            {
                "error": t(
                    "unsupported_custom_tool_type",
                    tool_type=tool.type,
                )
            },
            ensure_ascii=False,
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
