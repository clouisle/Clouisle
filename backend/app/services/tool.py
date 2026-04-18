"""
Tool execution service.

Provides unified tool execution with credentials support.
"""

import logging
from typing import Any
from uuid import UUID

from app.models.tool import Tool, ToolType, CustomToolType
from app.models.tool_config import ToolConfig
from app.llm.tools import tool_registry
from app.llm.tools.executors import execute_http_tool
from app.llm.tools.mcp_client import execute_mcp_tool
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Tool executor service.

    Handles execution of all tool types (builtin, custom, MCP) with proper
    credentials management.
    """

    async def execute(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        user_id: str | None = None,
        team_id: UUID | None = None,
    ) -> Any:
        """
        Execute a tool with the given arguments.

        Args:
            tool: Tool instance to execute
            arguments: Tool arguments
            user_id: User ID for tracking
            team_id: Team ID for credentials lookup

        Returns:
            Tool execution result
        """
        # Get team_id from tool if not provided
        if not team_id and tool.team_id:
            team_id = tool.team_id

        tool_type = self._get_tool_type_value(tool.type)

        if tool_type == "builtin":
            return await self.execute_builtin_tool(
                tool_name=tool.name,
                arguments=arguments,
                team_id=team_id,
            )
        elif tool_type == ToolType.CUSTOM.value:
            return await self._execute_custom_tool(
                tool=tool,
                arguments=arguments,
            )
        elif tool_type == ToolType.MCP.value:
            return await self._execute_mcp_tool(
                tool=tool,
                arguments=arguments,
            )
        else:
            raise ValueError(f"Unknown tool type: {tool.type}")

    @staticmethod
    def _get_tool_type_value(tool_type: Any) -> str:
        """Normalize tool type enum/string values across schema and model layers."""
        return getattr(tool_type, "value", tool_type)

    async def execute_builtin_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        team_id: UUID | None = None,
    ) -> Any:
        """Execute a builtin tool with credentials support."""
        # Worker processes may not have imported the builtin registration path yet.
        if tool_registry.get_tool(tool_name) is None:
            from app.llm.tools.builtin import register_all_builtin_tools

            register_all_builtin_tools()

        # Get credentials for builtin tools
        credentials = await self._get_tool_credentials(
            tool_name=tool_name,
            team_id=team_id,
        )

        # Execute the tool
        try:
            result = await tool_registry.execute(
                name=tool_name,
                arguments=arguments,
                credentials=credentials,
            )
            return result
        except Exception as e:
            logger.exception(f"Builtin tool execution error: {e}")
            return {"error": str(e), "success": False}

    async def _execute_custom_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute a custom tool (HTTP or Code)."""
        if tool.custom_type == CustomToolType.HTTP:
            if not tool.http_config:
                raise ValueError("HTTP tool missing http_config")

            return await execute_http_tool(
                http_config=tool.http_config,
                arguments=arguments,
                credentials=tool.credentials or None,
            )
        elif tool.custom_type == CustomToolType.CODE:
            if not tool.code_config:
                raise ValueError("Code tool missing code_config")

            job = compile_code_config_job(
                code_config=tool.code_config,
                params=arguments,
                timeout=float(tool.code_config.get("limits", {}).get("timeout_seconds", 30.0)),
                source=SandboxJobSource.TOOL,
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                timeout_seconds=job.limits.timeout_seconds + 5,
            )
            return {
                "success": result.success,
                "result": result.result,
                "error": result.error,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "artifacts": [artifact.model_dump() for artifact in result.artifacts],
            }
        else:
            raise ValueError(f"Unknown custom tool type: {tool.custom_type}")

    async def _execute_mcp_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute an MCP tool."""
        if not tool.mcp_config:
            raise ValueError("MCP tool missing mcp_config")

        return await execute_mcp_tool(
            tool_name=tool.name,
            mcp_config=tool.mcp_config,
            arguments=arguments,
        )

    async def _get_tool_credentials(
        self,
        tool_name: str,
        team_id: UUID | None = None,
    ) -> dict[str, str]:
        """
        Get credentials for a tool.

        Priority:
        1. Team-specific config
        2. Global config
        """
        credentials = {}

        # Try team-specific config first
        if team_id:
            tool_config = await ToolConfig.filter(
                tool_name=tool_name, team_id=team_id
            ).first()
            if tool_config:
                credentials = tool_config.credentials or {}

        # If no team config, try global config
        if not credentials:
            global_config = await ToolConfig.filter(
                tool_name=tool_name, team_id=None
            ).first()
            if global_config:
                credentials = global_config.credentials or {}

        return credentials
