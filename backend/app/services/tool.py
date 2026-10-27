"""
Tool execution service.

Provides unified tool execution with credentials support.
"""

import logging
from copy import copy, deepcopy
from typing import Any
from uuid import UUID

from app.core.i18n import t
from app.models.tool import Tool, ToolType, CustomToolType
from app.llm.tools import tool_registry
from app.llm.tools.executors import execute_http_tool
from app.llm.tools.mcp_client import execute_mcp_tool
from app.services.builtin_tools import get_builtin_definition
from app.services.error_messages import resolve_user_visible_error
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.credentials import (
    CREDENTIALS_METADATA_KEY,
    encrypt_sandbox_credentials,
)
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource
from app.services.tool_execution import ToolCallContext, execute_stored_tool
from app.services.tool_connections import ResolvedConnection


async def build_mcp_config(
    tool: Tool, resolved: ResolvedConnection | None
) -> dict[str, Any]:
    """Render one connection's MCP credentials without mutating the definition."""
    from app.llm.tools.executors import _render_text_template
    from app.schemas.response import BusinessError
    from app.services.tool_oauth import ToolOAuthService

    config = deepcopy(tool.mcp_config or {})
    secrets = dict(resolved.secrets) if resolved is not None else {}
    for key in ("headers", "env"):
        raw = config.get(key)
        if isinstance(raw, dict):
            config[key] = {
                str(name): _render_text_template(str(value), secrets)
                for name, value in raw.items()
            }
    if config.get("oauth") or await ToolOAuthService.has_oauth_binding(resolved):
        if resolved is None:
            raise BusinessError(
                code=403, msg_key="tool_connection_required", status_code=403
            )
        authorization = await ToolOAuthService.get_authorization_header(resolved)
        if authorization:
            config["headers"] = {
                key: value
                for key, value in (config.get("headers") or {}).items()
                if str(key).lower() != "authorization"
            }
            config["headers"]["Authorization"] = authorization
    return config


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
        conversation_id: UUID | str | None = None,
        workflow_run_id: UUID | str | None = None,
        context: ToolCallContext | None = None,
        operation: str | None = None,
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
            if context is None:
                from app.models.user import User
                from app.models.tool_approval import ExecutionEntrypoint
                from app.schemas.response import BusinessError

                actor = await User.get_or_none(id=user_id) if user_id else None
                if actor is None or team_id is None:
                    raise BusinessError(
                        code=403,
                        msg_key="user_context_required",
                        status_code=403,
                    )
                context = ToolCallContext(
                    actor=actor,
                    team_id=team_id,
                    entrypoint=(
                        ExecutionEntrypoint.WORKFLOW
                        if workflow_run_id
                        else ExecutionEntrypoint.CHAT
                    ),
                )
            return await self.execute_builtin_tool(
                tool_name=tool.name,
                arguments=arguments,
                team_id=team_id,
                context=context,
                conversation_id=conversation_id,
                workflow_run_id=workflow_run_id,
                operation=operation,
            )
        elif tool_type in {ToolType.CUSTOM.value, ToolType.MCP.value}:
            if context is None:
                from app.models.user import User
                from app.models.tool_approval import ExecutionEntrypoint
                from app.schemas.response import BusinessError

                actor = await User.get_or_none(id=user_id) if user_id else None
                if actor is None or team_id is None:
                    raise BusinessError(
                        code=403, msg_key="user_context_required", status_code=403
                    )
                context = ToolCallContext(
                    actor=actor,
                    team_id=team_id,
                    entrypoint=ExecutionEntrypoint.WORKFLOW
                    if workflow_run_id
                    else ExecutionEntrypoint.CHAT,
                )

            async def invoke(parameters, resolved):
                execution_tool = copy(tool)
                execution_tool.credentials = dict(resolved.secrets) if resolved else {}
                from app.services.tool_oauth import ToolOAuthService

                oauth_config = (tool.http_config or {}).get("oauth2")
                authorization = None
                if tool_type == ToolType.CUSTOM.value and oauth_config:
                    if resolved is None:
                        from app.schemas.response import BusinessError

                        raise BusinessError(
                            code=403,
                            msg_key="tool_connection_required",
                            status_code=403,
                        )

                    authorization = await ToolOAuthService.get_authorization_header(
                        resolved
                    )
                if authorization and tool.custom_type == CustomToolType.HTTP:
                    execution_tool.http_config = dict(tool.http_config)
                    execution_tool.http_config["headers"] = {
                        key: value
                        for key, value in tool.http_config.get("headers", {}).items()
                        if key.lower() != "authorization"
                    }
                    execution_tool.http_config["headers"]["Authorization"] = (
                        authorization
                    )

                if tool_type == ToolType.CUSTOM.value:
                    return await self._execute_custom_tool(execution_tool, parameters)
                config = await build_mcp_config(tool, resolved)
                from app.services.mcp_interactions import (
                    mcp_call_timeout_seconds,
                    run_with_mcp_callbacks,
                )

                call_timeout = mcp_call_timeout_seconds(tool)

                async def call_mcp(callbacks):
                    return await execute_mcp_tool(
                        config,
                        operation or tool.name,
                        parameters,
                        timeout=call_timeout,
                        callbacks=callbacks,
                    )

                result = await run_with_mcp_callbacks(
                    tool,
                    context,
                    call_mcp,
                    call_timeout_seconds=call_timeout,
                )
                return result.to_dict()

            return await execute_stored_tool(
                tool,
                f"tool:{operation or tool.name}"
                if tool_type == ToolType.MCP.value
                else operation or tool.name,
                arguments,
                context,
                invoke,
            )
        else:
            raise ValueError(t("unsupported_custom_tool_type", tool_type=tool.type))

    @staticmethod
    def _get_tool_type_value(tool_type: Any) -> str:
        """Normalize tool type enum/string values across schema and model layers."""
        return getattr(tool_type, "value", tool_type)

    async def execute_builtin_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        team_id: UUID | None = None,
        context: ToolCallContext | None = None,
        conversation_id: UUID | str | None = None,
        workflow_run_id: UUID | str | None = None,
        operation: str | None = None,
        agent_tool_config: dict[str, Any] | None = None,
        agent: Any = None,
        user: Any = None,
        session_id: str | None = None,
        current_images: list[Any] | None = None,
    ) -> Any:
        """Execute a builtin tool through the unified stored-tool boundary.

        The stable per-team definition supplies identity/approval policy; the
        connection resolver supplies credentials. There is no ToolConfig or
        global credential fallback here. ``web_search`` deliberately resolves
        no connection secrets: its site-managed engine configuration remains
        authoritative and a personal override is rejected by policy ``none``.
        """
        definition = await get_builtin_definition(team_id, tool_name)

        if context is None:
            from app.schemas.response import BusinessError

            raise BusinessError(
                code=403,
                msg_key="user_context_required",
                status_code=403,
            )

        async def invoke(parameters, resolved):
            credentials = (
                {}
                if tool_name == "web_search"
                else (dict(resolved.secrets) if resolved else {})
            )
            scope: dict[str, Any] = {}
            if conversation_id is not None:
                scope["conversation_id"] = conversation_id
            if workflow_run_id is not None:
                scope["workflow_run_id"] = workflow_run_id
            if agent_tool_config:
                scope["agent_tool_config"] = agent_tool_config
            if agent is not None:
                scope["agent"] = agent
            if user is not None:
                scope["user"] = user
            if session_id is not None:
                scope["session_id"] = session_id
            if current_images is not None:
                scope["current_images"] = current_images
            try:
                return await tool_registry.execute(
                    name=tool_name,
                    arguments=parameters,
                    credentials=credentials,
                    **scope,
                )
            except Exception as e:
                logger.exception(f"Builtin tool execution error: {e}")
                return {
                    "error": resolve_user_visible_error(str(e)),
                    "success": False,
                }

        return await execute_stored_tool(
            definition,
            operation or tool_name,
            arguments,
            context,
            invoke,
        )

    @staticmethod
    def _attach_code_credentials(job: Any, credentials: dict[str, Any]) -> Any:
        """Attach an encrypted credential envelope to a sandbox job.

        Only the versioned ciphertext enters the durable Celery payload; the
        selected connection values are decrypted by the Sandbox Worker for
        this single execution.
        """
        metadata = dict(job.metadata or {})
        metadata[CREDENTIALS_METADATA_KEY] = encrypt_sandbox_credentials(
            credentials, job_id=job.job_id
        )
        return job.model_copy(update={"metadata": metadata})

    async def _execute_custom_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        """Execute a custom tool (HTTP or Code)."""
        if tool.custom_type == CustomToolType.HTTP:
            if not tool.http_config:
                raise ValueError(t("tool_execution_failed"))

            return await execute_http_tool(
                http_config=tool.http_config,
                arguments=arguments,
                credentials=tool.credentials or None,
            )
        elif tool.custom_type == CustomToolType.CODE:
            if not tool.code_config:
                raise ValueError(t("tool_execution_failed"))

            job = compile_code_config_job(
                code_config=tool.code_config,
                params=arguments,
                timeout=float(
                    tool.code_config.get("limits", {}).get("timeout_seconds", 30.0)
                ),
                source=SandboxJobSource.TOOL,
            )
            credentials = {
                str(name): value for name, value in (tool.credentials or {}).items()
            }
            if credentials:
                job = self._attach_code_credentials(job, credentials)
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
            raise ValueError(
                t("unsupported_custom_tool_type", tool_type=tool.custom_type)
            )
