"""Resolve model aliases against the Agent's configured stored tools."""

from typing import Any
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
from app.services.tool_execution import PendingToolApproval, ToolCallContext


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
            grant_id=UUID(config["grant_id"]) if config.get("grant_id") else None,
            interactive=runtime.interactive if runtime else False,
        )
        result = await ToolExecutor().execute(
            tool, arguments, context=context, operation=operation
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
