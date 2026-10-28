"""One authorization, connection and approval boundary for stored tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID, uuid4

from app.models.tool import Tool, ToolType
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecutionStatus,
)
from app.models.tool_connection import ToolConnectionScope
from app.models.user import User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import (
    ExternalApprovalAudienceError,
    assert_caller_only_approval_policy,
)
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
    interactive: bool = False
    execution_id: UUID | None = None
    require_approval: bool = False


@dataclass(frozen=True, slots=True)
class PendingToolApproval:
    execution_id: UUID
    tool_name: str


def require_caller_only_policy(policy: Any, *, status_code: int = 422) -> None:
    """Fail closed on a legacy ``user``/``team_role`` policy body.

    Used by explicit policy write paths (tool create/update/duplicate, policy
    layers, package install) before anything is persisted and by the execution
    boundary. Reading historical configuration and decisions stays untouched;
    the error keeps the existing configuration-required code.
    """
    try:
        assert_caller_only_approval_policy(policy)
    except ExternalApprovalAudienceError as exc:
        raise BusinessError(
            code=ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED,
            msg_key="tool_approval_policy_external_audience_unsupported",
            status_code=status_code,
        ) from exc


def _reject_legacy_external_gates(
    tool: Tool,
    *,
    policy: Any | None,
    execution: Any | None = None,
) -> None:
    """Every entrypoint fails closed on a legacy external audience.

    The caller-only contract never silently ignores a stored audience: a tool
    whose policy (at any nesting depth), an explicit override, or the stored
    execution snapshot names users or team roles cannot run.
    """
    for candidate in (
        getattr(tool, "approval_policy", None),
        policy,
        getattr(execution, "policy_snapshot", None),
    ):
        require_caller_only_policy(candidate, status_code=409)


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
    if mode is None:
        # A missing mode on a selectable tool means "use the invoking user's
        # account"; team-only tools keep their single allowed scope.
        scope = (
            ToolConnectionScope.USER
            if ToolConnectionScope.USER in scopes
            else scopes[0]
        )
    elif mode in {"personal", "team"}:
        scope = (
            ToolConnectionScope.USER if mode == "personal" else ToolConnectionScope.TEAM
        )
    else:
        raise BusinessError(
            code=400, msg_key="tool_connection_required", status_code=400
        )
    fields = {field["name"] for field in tool.connection_fields}
    # Automatic identity selection is limited to an interactive caller or a
    # trusted manual workflow origin (workflow surface with a stable entrypoint
    # reference); API-key, embed, channel, schedule and nested origins still
    # require a fixed connection. Manual workflows stay non-interactive for
    # approval gates.
    manual_workflow = context.entrypoint == ExecutionEntrypoint.WORKFLOW and bool(
        context.entrypoint_id
    )
    im_origin = context.entrypoint in {
        ExecutionEntrypoint.FEISHU_CHANNEL,
        ExecutionEntrypoint.WECHAT_CHANNEL,
    }
    auto_select = context.connection_id is None and (
        (context.interactive and not im_origin) or manual_workflow
    )
    binding_trusted = context.entrypoint in {
        ExecutionEntrypoint.WORKFLOW,
        ExecutionEntrypoint.SUBWORKFLOW,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.CHANNEL,
        ExecutionEntrypoint.FEISHU_CHANNEL,
        ExecutionEntrypoint.WECHAT_CHANNEL,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.AGENT_RUN,
    } or (
        context.entrypoint == ExecutionEntrypoint.CHAT
        and context.entrypoint_id is not None
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
        binding_trusted=binding_trusted,
        use_default=auto_select,
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
    # Snapshot the identity that was actually resolved. Resolving again here
    # could select a different default connection under a concurrent update.
    binding = ToolConnectionService.binding_from_resolved(resolved)
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
    # Every entrypoint (interactive or not) fails closed while any legacy
    # user/team_role audience remains configured; it is never treated as a
    # caller gate, ignored, or silently allowed.
    _reject_legacy_external_gates(tool, policy=policy)
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
            connection_mode="personal"
            if execution.connection_scope == "user"
            else "team"
            if execution.connection_id
            else None,
        )
    # A pending/ready execution created before the cutover also cannot resume
    # with a snapshot that still names external approvers.
    _reject_legacy_external_gates(tool, policy=policy, execution=execution)
    resolved, binding = await resolve_tool_connection(tool, context, operation)
    is_agent_call = (
        context.entrypoint
        in {
            ExecutionEntrypoint.CHAT,
            ExecutionEntrypoint.AGENT_RUN,
            ExecutionEntrypoint.FEISHU_CHANNEL,
            ExecutionEntrypoint.WECHAT_CHANNEL,
        }
        and context.run_kind != ExecutionRunKind.WORKFLOW
        and context.interactive
    )
    from app.schemas.tool_approval import (
        ApprovalDecision,
        ApprovalGate,
        ApprovalGateKind,
        PolicyLayer,
        PolicySource,
        ToolApprovalPolicy,
    )

    effective_policy = ToolApprovalPolicy(default_decision=ApprovalDecision.ALLOW)
    layers: list[PolicyLayer] = []
    if is_agent_call:
        # MCP child policies are explicit configuration, not a discovery gate.
        if tool.type == ToolType.MCP and tool.approval_policy:
            try:
                effective_policy = tool_approvals.normalize_tool_approval_policy(
                    tool.approval_policy
                )
            except tool_approvals.PolicyConfigurationError as exc:
                raise BusinessError(
                    code=ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED,
                    msg_key="tool_approval_policy_configuration_required",
                    status_code=409,
                ) from exc
        if context.require_approval:
            layers.append(
                PolicyLayer(
                    source=PolicySource.ENTRYPOINT,
                    label="agent_confirmation",
                    policy=ToolApprovalPolicy(
                        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                        gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
                    ),
                )
            )
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
            *layers,
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
