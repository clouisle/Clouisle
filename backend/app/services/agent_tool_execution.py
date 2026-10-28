"""Resolve model aliases against the Agent's configured stored tools."""

from collections.abc import Awaitable
from typing import Any, TypeVar
from uuid import UUID

from app.llm.tools.interaction import ToolInteractionRequest
from app.models.tool import Tool
from app.models.tool_approval import ExecutionEntrypoint
from app.models.user import User
from app.schemas.response import BusinessError
from app.services.tool import ToolExecutor
from app.services.tool_context import (
    coerce_execution_entrypoint,
    coerce_execution_run_kind,
    current_tool_identity,
)
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    authorize_tool_context,
    resolve_tool_connection,
)

_T = TypeVar("_T")
_GUIDANCE_KEYS = {
    "tool_access_denied": "agent_tool_access_denied",
    "tool_connection_required": "agent_tool_connection_required",
    "tool_connection_inactive": "agent_tool_connection_inactive",
    "tool_oauth_reauth_required": "agent_tool_connection_inactive",
    "tool_connection_default_required": "agent_tool_connection_default_required",
    "tool_connection_access_denied": "agent_tool_connection_access_denied",
}


async def _with_tool_guidance(tool: Tool, operation: Awaitable[_T]) -> _T:
    try:
        return await operation
    except BusinessError as exc:
        key = _GUIDANCE_KEYS.get(exc.msg_key)
        if key is None:
            raise
        raise BusinessError(
            code=exc.code,
            msg_key=key,
            status_code=exc.status_code,
            data=exc.data,
            tool_name=(tool.display_name or tool.name)[:100],
        ) from exc


async def list_agent_mcp_tools(
    agent: Any, tool: Tool, config: dict[str, Any], user_id: UUID | str | None
) -> list[Any]:
    """Discover tools using the same user's connection as their later execution."""
    from app.llm.tools.mcp_client import list_mcp_tools
    from app.services.tool import build_mcp_config

    resolved = None
    if user_id is not None or getattr(tool, "identity_policy", "none") != "none":
        actor = await User.get_or_none(id=user_id) if user_id else None
        if actor is None:
            raise BusinessError(
                code=403, msg_key="user_context_required", status_code=403
            )
        runtime = current_tool_identity()
        context = ToolCallContext(
            actor=actor,
            team_id=agent.team_id,
            entrypoint=coerce_execution_entrypoint(runtime.entrypoint)
            if runtime
            else ExecutionEntrypoint.AGENT_RUN,
            entrypoint_id=runtime.entrypoint_id if runtime else str(agent.id),
            connection_mode=config.get("connection_mode"),
            connection_id=UUID(config["connection_id"])
            if config.get("connection_id")
            else None,
            interactive=runtime.interactive if runtime else False,
        )
        await _with_tool_guidance(tool, authorize_tool_context(tool, context))
        resolved, _binding = await _with_tool_guidance(
            tool, resolve_tool_connection(tool, context, "list:tools")
        )
    mcp_config = await _with_tool_guidance(tool, build_mcp_config(tool, resolved))
    return await list_mcp_tools(mcp_config)


async def execute_agent_stored_tool(
    agent: Any, name: str, arguments: dict, user: Any
) -> Any:
    if agent is None or user is None:
        raise BusinessError(code=403, msg_key="user_context_required", status_code=403)
    actor = await User.get_or_none(id=user.id)
    if actor is None:
        raise BusinessError(code=403, msg_key="user_context_required", status_code=403)
    runtime = current_tool_identity()
    for config in agent.tools_config or []:
        if not isinstance(config, dict) or config.get("type") not in {"mcp", "custom"}:
            continue
        tool_id = config.get("server_id") or config.get("tool_id")
        if not tool_id:
            continue
        tool = await Tool.get_or_none(id=tool_id, is_enabled=True)
        if tool is None:
            continue
        if config["type"] == "mcp":
            prefix = f"mcp_{tool.name}_"
            if not name.startswith(prefix):
                continue
            operation = name[len(prefix) :]
        else:
            if name != f"custom_{tool.name}":
                continue
            operation = tool.name
        context = ToolCallContext(
            actor=actor,
            team_id=agent.team_id,
            entrypoint=coerce_execution_entrypoint(runtime.entrypoint)
            if runtime
            else ExecutionEntrypoint.AGENT_RUN,
            entrypoint_id=runtime.entrypoint_id if runtime else str(agent.id),
            run_kind=(
                coerce_execution_run_kind(getattr(runtime, "run_kind", "agent"))
                if runtime and runtime.run_id
                else None
            ),
            run_id=runtime.run_id if runtime else None,
            tool_call_id=runtime.tool_call_id if runtime else None,
            connection_mode=config.get("connection_mode"),
            connection_id=UUID(config["connection_id"])
            if config.get("connection_id")
            else None,
            interactive=runtime.interactive if runtime else False,
            require_approval=bool(config.get("require_approval", False)),
        )
        result = await _with_tool_guidance(
            tool,
            ToolExecutor().execute(
                tool, arguments, context=context, operation=operation
            ),
        )
        if isinstance(result, PendingToolApproval):
            return ToolInteractionRequest(
                tool_name=name,
                arguments={
                    "interaction_kind": "tool_approval",
                    "execution_id": str(result.execution_id),
                },
            )
        return result
    raise BusinessError(code=404, msg_key="tool_not_found", status_code=404)
