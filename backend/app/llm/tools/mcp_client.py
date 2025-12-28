"""
MCP (Model Context Protocol) Client

Provides functionality to connect to MCP servers and execute tools.
Supports three transport types:
- stdio: Launch a subprocess and communicate via stdin/stdout
- sse: Connect via Server-Sent Events
- http: Connect via Streamable HTTP
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


@dataclass
class McpToolResult:
    """Result of MCP tool execution"""

    success: bool
    result: Any | None = None
    error: str | None = None


@dataclass
class McpToolInfo:
    """Information about an MCP tool"""

    name: str
    description: str | None
    parameters: dict[str, Any]


class McpClient:
    """
    MCP Client for connecting to MCP servers.

    Supports stdio, SSE, and HTTP transports.
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize MCP client with configuration.

        Args:
            config: MCP configuration dict with:
                - transport: "stdio" | "sse" | "http"
                - command: Command to run (for stdio)
                - args: Command arguments (for stdio)
                - env: Environment variables (for stdio)
                - url: Server URL (for sse/http)
                - headers: HTTP headers (for sse/http)
        """
        self.config = config
        self.transport = config.get("transport", "stdio")
        self._session: ClientSession | None = None
        self._read_stream: Any = None
        self._write_stream: Any = None

    @asynccontextmanager
    async def connect(self):
        """
        Connect to MCP server.

        Yields:
            ClientSession: The MCP client session
        """
        if self.transport == "stdio":
            async with self._connect_stdio() as session:
                yield session
        elif self.transport == "sse":
            async with self._connect_sse() as session:
                yield session
        elif self.transport == "http":
            async with self._connect_http() as session:
                yield session
        else:
            raise ValueError(f"Unsupported transport: {self.transport}")

    @asynccontextmanager
    async def _connect_stdio(self):
        """Connect via stdio transport"""
        command = self.config.get("command")
        args = self.config.get("args", [])
        env = self.config.get("env", {})

        if not command:
            raise ValueError("Command is required for stdio transport")

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env if env else None,
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    @asynccontextmanager
    async def _connect_sse(self):
        """Connect via SSE transport"""
        url = self.config.get("url")
        headers = self.config.get("headers", {})

        if not url:
            raise ValueError("URL is required for SSE transport")

        async with sse_client(url, headers=headers if headers else None) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    @asynccontextmanager
    async def _connect_http(self):
        """Connect via Streamable HTTP transport"""
        url = self.config.get("url")
        headers = self.config.get("headers", {})

        if not url:
            raise ValueError("URL is required for HTTP transport")

        async with streamablehttp_client(url, headers=headers if headers else None) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[McpToolInfo]:
        """
        List available tools from the MCP server.

        Returns:
            List of tool information
        """
        async with self.connect() as session:
            result = await session.list_tools()
            return [
                McpToolInfo(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.inputSchema if hasattr(tool, "inputSchema") else {},
                )
                for tool in result.tools
            ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float = 60.0,
    ) -> McpToolResult:
        """
        Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            timeout: Execution timeout in seconds

        Returns:
            McpToolResult with success status and result/error
        """
        try:
            async with asyncio.timeout(timeout):
                async with self.connect() as session:
                    result = await session.call_tool(tool_name, arguments)

                    # Check if there are any errors in the content
                    if result.isError:
                        error_text = ""
                        for content in result.content:
                            if hasattr(content, "text"):
                                error_text += content.text
                        return McpToolResult(
                            success=False,
                            error=error_text or "Tool execution failed",
                        )

                    # Extract result from content
                    result_data = []
                    for content in result.content:
                        if hasattr(content, "text"):
                            result_data.append(content.text)
                        elif hasattr(content, "data"):
                            result_data.append(content.data)

                    # Return single item or list
                    if len(result_data) == 1:
                        return McpToolResult(success=True, result=result_data[0])
                    elif len(result_data) == 0:
                        return McpToolResult(success=True, result=None)
                    else:
                        return McpToolResult(success=True, result=result_data)

        except TimeoutError:
            return McpToolResult(
                success=False,
                error=f"Tool execution timed out after {timeout} seconds",
            )
        except Exception as e:
            logger.exception(f"MCP tool execution error: {e}")
            return McpToolResult(
                success=False,
                error=str(e),
            )


async def execute_mcp_tool(
    mcp_config: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 60.0,
) -> McpToolResult:
    """
    Execute an MCP tool.

    This is a convenience function that creates a client and executes a tool.

    Args:
        mcp_config: MCP server configuration
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        timeout: Execution timeout in seconds

    Returns:
        McpToolResult with success status and result/error
    """
    client = McpClient(mcp_config)
    return await client.execute_tool(tool_name, arguments, timeout)


async def list_mcp_tools(mcp_config: dict[str, Any]) -> list[McpToolInfo]:
    """
    List tools available from an MCP server.

    Args:
        mcp_config: MCP server configuration

    Returns:
        List of tool information
    """
    client = McpClient(mcp_config)
    return await client.list_tools()
