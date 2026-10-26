"""One authorization, connection and approval boundary for stored tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid4

from app.models.tool import Tool
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionStatus,
)
from app.models.tool_connection import ToolConnectionScope
from app.models.user import User
from app.schemas.response import BusinessError
from app.schemas.tool_connection import ConnectionEntrypoint
from app.services import tool_approvals
from app.services.tool_connections import (
    ConnectionBinding,
    ResolvedConnection,
    ToolConnectionService,
)


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    actor: User
    team_id: UUID
    entrypoint: ExecutionEntrypoint
    entrypoint_id: str | None = None
    run_kind: ExecutionRunKind | None = None
    run_id: UUID | None = None
    tool_call_id: str | None = None
    connection_mode: str | None = None
    connection_id: UUID | None = None
    grant_id: UUID | None = None
    interactive: bool = False
    execution_id: UUID | None = None
    require_approval: bool = False


@dataclass(frozen=True, slots=True)
class PendingToolApproval:
    execution_id: UUID
    tool_name: str


async def authorize_tool_context(tool: Tool, context: ToolCallContext) -> None:
    from app.api.team_access import check_team_access
    from app.api.v1.endpoints.tools import check_tool_access
    from app.models.tool import ToolShare, ToolVisibility

    await context.actor.fetch_related("roles__permissions")
    await check_team_access(context.team_id, context.actor)
    if tool.team_id == context.team_id:
        await check_tool_access(tool, context.actor)
        return
    if (
        tool.visibility == ToolVisibility.PRIVATE
        or not await ToolShare.filter(
            tool_id=tool.id, shared_with_team_id=context.team_id
        ).exists()
    ):
        raise BusinessError(code=403, msg_key="tool_access_denied", status_code=403)


async def resolve_tool_connection(
    tool: Tool, context: ToolCallContext, operation: str
) -> tuple[ResolvedConnection | None, ConnectionBinding | None]:
    policy = tool.identity_policy
    if policy == "none":
        if context.connection_id is not None:
            raise BusinessError(
                code=403, msg_key="tool_connection_access_denied", status_code=403
            )
        return None, None
    scopes = {
        "team_only": (ToolConnectionScope.TEAM,),
        "personal_only": (ToolConnectionScope.USER,),
        "selectable": (ToolConnectionScope.USER, ToolConnectionScope.TEAM),
    }.get(policy)
    if scopes is None:
        raise BusinessError(
            code=400, msg_key="tool_connection_invalid", status_code=400
        )
    mode = context.connection_mode
    if mode is None and len(scopes) == 1:
        scope = scopes[0]
    elif mode in {"personal", "team"}:
        scope = (
            ToolConnectionScope.USER if mode == "personal" else ToolConnectionScope.TEAM
        )
    else:
        raise BusinessError(
            code=400, msg_key="tool_connection_required", status_code=400
        )
    fields = {field["name"] for field in tool.connection_fields}
    entrypoint = None
    if not context.interactive:
        if not context.entrypoint_id:
            raise BusinessError(
                code=403, msg_key="tool_connection_grant_required", status_code=403
            )
        entrypoint_type = {
            "agent_run": "agent",
            "nested_agent": "agent",
            "chat": "agent",
            "subworkflow": "workflow",
            "workflow": "workflow",
            "api_key": "api_key",
            "channel": "channel",
            "embed": "embed",
            "schedule": "schedule",
        }.get(context.entrypoint.value)
        if entrypoint_type is None:
            raise BusinessError(
                code=403, msg_key="tool_connection_grant_required", status_code=403
            )
        entrypoint = ConnectionEntrypoint(
            entrypoint_type=entrypoint_type,
            entrypoint_id=context.entrypoint_id,
            team_id=context.team_id,
        )
    kwargs = dict(
        actor=context.actor,
        team_id=context.team_id,
        tool_id=tool.id,
        builtin_tool_key=(
            tool.name if getattr(tool.type, "value", tool.type) == "builtin" else None
        ),
        connection_id=context.connection_id,
        scope=scope,
        operation=operation,
        entrypoint=entrypoint,
        grant_id=context.grant_id,
        use_default=context.connection_id is None and context.interactive,
        allowed_scopes=scopes,
    )
    resolved = await ToolConnectionService.resolve_connection(
        **kwargs, allowed_secret_fields=fields
    )
    missing = [
        field["name"]
        for field in tool.connection_fields
        if field.get("required", True) and not resolved.secrets.get(field["name"])
    ]
    if missing:
        raise BusinessError(
            code=400, msg_key="tool_connection_required", status_code=400
        )
    binding = await ToolConnectionService.get_binding_snapshot(**kwargs)
    return resolved, binding


async def execute_stored_tool(
    tool: Tool,
    operation: str,
    arguments: dict[str, Any],
    context: ToolCallContext,
    invoke: Callable[[dict[str, Any], ResolvedConnection | None], Awaitable[Any]],
    *,
    policy: Any | None = None,
) -> Any:
    await authorize_tool_context(tool, context)
    if not tool.is_enabled:
        raise BusinessError(code=403, msg_key="tool_access_denied", status_code=403)
    execution = None
    if context.execution_id is not None:
        execution = await tool_approvals.get_execution(context.execution_id)
        snapshot = tool_approvals.build_parameter_snapshot(arguments)
        if (
            execution.actor_user_id != context.actor.id
            or execution.team_id != context.team_id
            or execution.tool_id != tool.id
            or execution.operation != operation
            or execution.parameters_digest != snapshot.digest
            or execution.entrypoint != context.entrypoint
        ):
            raise BusinessError(
                code=403, msg_key="tool_execution_access_denied", status_code=403
            )
    if (
        execution is None
        and context.run_id is not None
        and context.run_kind is not None
        and context.tool_call_id
    ):
        execution = await tool_approvals.find_execution_by_tool_call(
            run_kind=context.run_kind,
            run_id=context.run_id,
            tool_call_id=context.tool_call_id,
        )
    if execution is not None:
        if (
            execution.actor_user_id != context.actor.id
            or execution.team_id != context.team_id
            or execution.tool_id != tool.id
            or execution.operation != operation
        ):
            raise BusinessError(
                code=403, msg_key="tool_execution_access_denied", status_code=403
            )
        if (
            context.connection_id is not None
            and context.connection_id != execution.connection_id
        ):
            raise BusinessError(
                code=409, msg_key="tool_approval_binding_changed", status_code=409
            )
        context = replace(
            context,
            connection_id=execution.connection_id,
            grant_id=execution.grant_id,
            connection_mode="personal"
            if execution.connection_scope == "user"
            else "team"
            if execution.connection_id
            else None,
        )
    resolved, binding = await resolve_tool_connection(tool, context, operation)
    is_workflow = (
        context.entrypoint == ExecutionEntrypoint.WORKFLOW
        or context.run_kind == ExecutionRunKind.WORKFLOW
    )
    tool_requires_approval = (getattr(tool, "approval_policy", None) or {}).get(
        "default_decision"
    ) == "require_approval"
    needs_approval = (
        not is_workflow
        and context.interactive
        and (context.require_approval or tool_requires_approval)
    )
    from app.schemas.tool_approval import (
        ApprovalDecision,
        ApprovalGate,
        ApprovalGateKind,
        PolicyLayer,
        PolicySource,
        ToolApprovalPolicy,
    )

    if needs_approval:
        effective_policy = ToolApprovalPolicy(
            default_decision=ApprovalDecision.REQUIRE_APPROVAL,
            gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
        )
    else:
        effective_policy = ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW)
    layers: list[PolicyLayer] = []
    if execution is None:
        execution = await tool_approvals.create_execution(
            tool=tool,
            operation=operation,
            parameters=arguments,
            actor=context.actor,
            team_id=context.team_id,
            entrypoint=context.entrypoint,
            entrypoint_id=context.entrypoint_id,
            run_kind=context.run_kind,
            run_id=context.run_id,
            tool_call_id=context.tool_call_id,
            connection_binding=binding,
            connection_account_label=resolved.account_label if resolved else None,
            policy=effective_policy,
            entrypoint_interactive=context.interactive,
            policy_layers=layers,
            sensitive_fields=[
                field["name"]
                for field in tool.connection_fields
                if field.get("secret", True)
            ],
        )
    if execution.status == ToolExecutionStatus.AWAITING_APPROVAL:
        return PendingToolApproval(execution.id, tool.name)
    if execution.status != ToolExecutionStatus.READY:
        raise BusinessError(
            code=409, msg_key="tool_execution_not_ready", status_code=409
        )

    async def authorize(_execution: Any) -> None:
        fresh_tool = await Tool.get_or_none(id=tool.id)
        actor = await User.get_or_none(id=context.actor.id, is_active=True)
        if fresh_tool is None or actor is None or not fresh_tool.is_enabled:
            raise BusinessError(code=403, msg_key="tool_access_denied", status_code=403)
        await authorize_tool_context(fresh_tool, context)
        if fresh_tool.definition_version != tool.definition_version:
            raise BusinessError(
                code=409, msg_key="tool_approval_binding_changed", status_code=409
            )

    evaluation = tool_approvals.evaluate_policy(
        [
            PolicyLayer(
                source=PolicySource.TOOL,
                label="tool",
                policy=effective_policy,
            ),
        ],
        operation,
        entrypoint_interactive=context.interactive,
    )
    token = uuid4().hex
    await tool_approvals.claim_execution(
        execution.id,
        claim_token=token,
        binding=binding,
        tool_definition_version=tool.definition_version,
        authorizer=authorize,
        policy_hash=evaluation.policy_hash,
    )
    parameters = await tool_approvals.load_execution_parameters(
        execution.id, claim_token=token
    )
    try:
        from app.services.tool_context import execution_identity_scope

        with execution_identity_scope(execution.id):
            result = await invoke(parameters, resolved)
    except BaseException:
        await tool_approvals.mark_execution_outcome_unknown(
            execution.id, claim_token=token
        )
        raise
    if isinstance(result, dict) and result.get("success") is False:
        await tool_approvals.mark_execution_failed(
            execution.id, claim_token=token, error_code="tool_execution_failed"
        )
    else:
        await tool_approvals.mark_execution_succeeded(execution.id, claim_token=token)
    return result
