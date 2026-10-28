"""Authenticated MCP capabilities, resources, prompts and tool calls.

Every route starts from a *stored* MCP tool definition. Request bodies may
select an identity (``connection_mode`` / ``connection_id``) but can never
supply transport configuration or credentials: the saved
:class:`~app.models.tool.Tool.mcp_config` is copied, its ``headers``/``env``
placeholders are rendered with secrets resolved by
:class:`~app.services.tool_connections.ToolConnectionService`, and the
resulting configuration never leaves this module.

Boundaries:

* **Tool access** – ``authorize_tool_context`` against the *consuming*
  ``team_id``: the owning team uses canonical ``check_tool_access``, a
  different team must hold an explicit ``ToolShare`` (private tools never
  share). The row is always looked up by ID; no caller-supplied config is
  trusted.
* **Identity** – every operation, metadata included, runs through
  ``execute_stored_tool``. Metadata uses a dedicated ``list:<kind>`` policy
  layer: default allow, an explicit one-level override is honoured in full
  (allow/deny/require_approval), and a malformed stored policy is rejected.
  ``max_items`` and ``cursor`` are bound into the approval parameters, so an
  approved page cannot be widened or swapped. Metadata may return the same
  pending-approval envelope as an operation; replay the request with
  ``execution_id`` after approval.
* **Operation namespaces** – ``tool:<name>``, ``read:resource``,
  ``prompt:<name>``, ``complete:prompt`` / ``complete:resource_template`` and
  ``list:<kind>`` keep MCP tools, resources and prompts with identical names
  from sharing one approval/override key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api import deps
from app.llm.tools.mcp_client import (
    DEFAULT_MAX_ITEMS,
    DEFAULT_MAX_PAGES,
    McpCompletionReference,
    McpContentLimits,
    McpEnumeration,
    McpEnumerationLimits,
    McpPromptInfo,
    McpResourceInfo,
    McpResourceTemplateInfo,
    McpServerCapabilities,
    McpTimeouts,
    McpToolInfo,
    complete_mcp_argument,
    enumerate_mcp_prompts,
    enumerate_mcp_resource_templates,
    enumerate_mcp_resources,
    enumerate_mcp_tools,
    execute_mcp_tool,
    get_mcp_prompt,
    probe_mcp_capabilities,
    read_mcp_resource,
    translate_mcp_error,
)
from app.models.tool import Tool, ToolType
from app.models.tool_approval import ExecutionEntrypoint
from app.models.user import User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.tool_approval import ToolApprovalPolicy
from app.schemas.tool_mcp import (
    McpCapabilitiesOut,
    McpCompletionIn,
    McpCompletionOut,
    McpConnectionMode,
    McpEnumerationOut,
    McpOperationOut,
    McpPendingApprovalOut,
    McpPromptArgumentOut,
    McpPromptGetIn,
    McpPromptMessageOut,
    McpPromptOut,
    McpPromptResultOut,
    McpResourceContentsOut,
    McpResourceOut,
    McpResourceReadIn,
    McpResourceTemplateOut,
    McpToolCallIn,
    McpToolOut,
    McpToolResultOut,
)
from app.services.mcp_errors import map_mcp_error
from app.services.mcp_interactions import (
    mcp_call_timeout_seconds,
    run_with_mcp_callbacks,
)
from app.services.mcp_subscriptions import (
    SubscriptionClosed,
    open_subscription,
)
from app.services.tool import build_mcp_config
from app.services.tool_approvals import PolicyConfigurationError
from app.services.tool_connections import ResolvedConnection
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    authorize_tool_context,
    execute_stored_tool,
    resolve_tool_layer_policy,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Fixed server-side budgets: callers cannot raise them, and no MCP session is
# ever opened without an explicit deadline.
MCP_CONNECT_TIMEOUT_SECONDS = 10.0
MCP_METADATA_TIMEOUT_SECONDS = 20.0
MCP_CONTENT_TIMEOUT_SECONDS = 30.0
MCP_CALL_TIMEOUT_SECONDS = 60.0
MCP_METADATA_TIMEOUTS = McpTimeouts(
    connect=MCP_CONNECT_TIMEOUT_SECONDS,
    request=MCP_METADATA_TIMEOUT_SECONDS,
    enumeration=MCP_METADATA_TIMEOUT_SECONDS,
)
MCP_CONTENT_TIMEOUTS = McpTimeouts(
    connect=MCP_CONNECT_TIMEOUT_SECONDS,
    request=MCP_CONTENT_TIMEOUT_SECONDS,
    enumeration=MCP_METADATA_TIMEOUT_SECONDS,
)
MCP_CONTENT_LIMITS = McpContentLimits()

# Operation namespaces shared with approval policy / connection grants.
OP_TOOL_PREFIX = "tool:"
OP_PROMPT_PREFIX = "prompt:"
OP_RESOURCE_READ = "read:resource"
OP_RESOURCE_SUBSCRIBE = "subscribe:resource"
OP_COMPLETION_PROMPT = "complete:prompt"
OP_COMPLETION_RESOURCE_TEMPLATE = "complete:resource_template"
OP_LIST_PREFIX = "list:"

# Raw braces never appear in a concrete URI; their presence means the caller
# pasted an unexpanded RFC 6570 resource template.
_URI_TEMPLATE_MARKER = re.compile(r"[{}]")


# ============ Loading & authorization ============


async def _load_mcp_tool(tool_id: UUID, context: ToolCallContext) -> Tool:
    """Load the stored definition and authorize it for the consuming team.

    ``authorize_tool_context`` accepts the tool's owning team (canonical
    ``check_tool_access``) or a consuming team that holds an explicit
    ``ToolShare``; private tools are never shared. The row is always resolved
    by ID so no caller-supplied configuration can replace it.
    """
    tool = await Tool.filter(id=tool_id).first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )
    await authorize_tool_context(tool, context)
    if not tool.is_enabled:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="tool_access_denied",
            status_code=403,
        )
    tool_type = getattr(tool.type, "value", tool.type)
    if tool_type != ToolType.MCP.value:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_tool_invalid_type",
            status_code=400,
        )
    if not getattr(tool, "mcp_config", None):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_tool_missing_configuration",
            status_code=400,
            tool_name=tool.name,
        )
    return tool


def _validate_resource_uri(uri: str) -> str:
    """Reject empty or unexpanded-template URIs before any execution row.

    The adapter repeats this check at the protocol boundary; doing it here
    turns a user input mistake into a localized 400 instead of a 502.
    """
    if not uri.strip() or _URI_TEMPLATE_MARKER.search(uri):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="mcp_invalid_resource_uri",
            status_code=400,
        )
    return uri


def _call_context(
    team_id: UUID,
    user: User,
    *,
    connection_mode: McpConnectionMode | None,
    connection_id: UUID | None,
    execution_id: UUID | None = None,
) -> ToolCallContext:
    return ToolCallContext(
        actor=user,
        team_id=team_id,
        entrypoint=ExecutionEntrypoint.TOOL_TEST,
        entrypoint_id=None,
        connection_mode=connection_mode,
        connection_id=connection_id,
        interactive=True,
        execution_id=execution_id,
    )


# ============ Error mapping ============


def _mcp_business_error(
    exc: BaseException, *, operation: str, tool: Tool
) -> BusinessError:
    if isinstance(exc, BusinessError):
        return exc
    # Task-group teardown wraps typed failures in ExceptionGroup; classify the
    # nested cause, never the wrapper, or an unsupported capability reads as a
    # connection failure.
    typed = translate_mcp_error(exc)
    logger.warning(
        "MCP operation %s failed for tool %s (%s)",
        operation,
        tool.id,
        type(typed if typed is not None else exc).__name__,
    )
    mapped = map_mcp_error(exc, operation=operation)
    if mapped is not None:
        return mapped
    return BusinessError(
        code=ResponseCode.INTERNAL_ERROR,
        msg_key="mcp_connection_failed",
        status_code=502,
    )


# ============ Serialization ============


def _capabilities_out(value: McpServerCapabilities) -> McpCapabilitiesOut:
    return McpCapabilitiesOut(
        protocol_version=value.protocol_version,
        server_name=value.server_name,
        server_version=value.server_version,
        instructions=value.instructions,
        tools=value.tools,
        tools_list_changed=value.tools_list_changed,
        resources=value.resources,
        resources_subscribe=value.resources_subscribe,
        resources_list_changed=value.resources_list_changed,
        resource_templates=value.resource_templates,
        prompts=value.prompts,
        prompts_list_changed=value.prompts_list_changed,
        completions=value.completions,
        logging=value.logging,
        experimental=value.experimental,
    )


def _tool_out(value: McpToolInfo) -> McpToolOut:
    return McpToolOut(
        name=value.name,
        title=value.title,
        description=value.description,
        parameters=value.parameters or {},
        output_schema=value.output_schema,
        annotations=value.annotations,
        meta=value.meta,
    )


def _resource_out(value: McpResourceInfo) -> McpResourceOut:
    return McpResourceOut(
        uri=value.uri,
        name=value.name,
        title=value.title,
        description=value.description,
        mime_type=value.mime_type,
        size=value.size,
        annotations=value.annotations,
        meta=value.meta,
    )


def _resource_template_out(
    value: McpResourceTemplateInfo,
) -> McpResourceTemplateOut:
    return McpResourceTemplateOut(
        uri_template=value.uri_template,
        name=value.name,
        title=value.title,
        description=value.description,
        mime_type=value.mime_type,
        annotations=value.annotations,
        meta=value.meta,
    )


def _prompt_out(value: McpPromptInfo) -> McpPromptOut:
    return McpPromptOut(
        name=value.name,
        title=value.title,
        description=value.description,
        arguments=[
            McpPromptArgumentOut(
                name=argument.name,
                description=argument.description,
                required=argument.required,
            )
            for argument in value.arguments
        ],
        meta=value.meta,
    )


def _enumeration_out(
    value: McpEnumeration[Any], serializer: Any
) -> McpEnumerationOut[Any]:
    items = [serializer(item) for item in value.items]
    return McpEnumerationOut[Any](
        items=items,
        pages_fetched=value.pages_fetched,
        truncated=value.truncated,
        truncation_reason=value.truncation_reason,
        next_cursor=value.next_cursor,
        total_items=len(items),
    )


def _operation_out(operation: str, outcome: Any) -> McpOperationOut[Any]:
    if isinstance(outcome, PendingToolApproval):
        return McpOperationOut[Any](
            status="pending_approval",
            operation=operation,
            execution_id=outcome.execution_id,
            pending_approval=McpPendingApprovalOut(
                execution_id=outcome.execution_id,
                tool_name=outcome.tool_name,
            ),
        )
    return McpOperationOut[Any](
        status="completed",
        operation=operation,
        result=outcome,
    )


def _sse_frame(event: str, data: dict[str, Any]) -> str:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


# ============ Shared request plumbing ============


def _metadata_policy(tool: Tool, operation: str) -> ToolApprovalPolicy:
    """Metadata-effective policy: allow by default, explicit override wins.

    The tool's operation default never governs discovery; only an explicit
    ``operation_overrides[list:<kind>]`` entry does (one level, as stored).
    A malformed stored policy is rejected instead of silently ignored.
    """
    try:
        return resolve_tool_layer_policy(
            tool,
            operation=operation,
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
        )
    except PolicyConfigurationError as exc:
        raise BusinessError(
            code=ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED,
            msg_key="tool_approval_policy_configuration_required",
            status_code=409,
        ) from exc


async def _execute_metadata(
    tool: Tool,
    context: ToolCallContext,
    *,
    operation: str,
    parameters: dict[str, Any],
    invoke: Any,
) -> McpOperationOut[Any]:
    try:
        outcome = await execute_stored_tool(
            tool,
            operation,
            parameters,
            context,
            invoke,
            policy=_metadata_policy(tool, operation),
        )
    except BusinessError:
        raise
    except Exception as exc:
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    return _operation_out(operation, outcome)


def _metadata_parameters(max_items: int, cursor: str | None) -> dict[str, Any]:
    """Approval-bound listing scope; an approved page cannot be widened."""
    return {"max_items": max_items, "cursor": cursor or None}


# ============ Metadata execution ============


async def _list_metadata(
    tool: Tool,
    context: ToolCallContext,
    *,
    operation: str,
    max_items: int,
    cursor: str | None,
    enumerate_call: Any,
    serializer: Any,
) -> McpOperationOut[Any]:
    """Run one listing through the approval boundary with bound page scope."""
    parameters = _metadata_parameters(max_items, cursor)

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> McpEnumerationOut[Any]:
        config = await build_mcp_config(tool, resolved)

        async def call_mcp(callbacks: Any) -> McpEnumeration[Any]:
            return await enumerate_call(
                config,
                timeout=MCP_METADATA_TIMEOUT_SECONDS,
                limits=McpEnumerationLimits(
                    max_pages=DEFAULT_MAX_PAGES,
                    max_items=approved["max_items"],
                ),
                start_cursor=approved.get("cursor"),
                timeouts=MCP_METADATA_TIMEOUTS,
                callbacks=callbacks,
            )

        enumeration = await run_with_mcp_callbacks(
            tool, context, call_mcp, execution_id=context.execution_id
        )
        return _enumeration_out(enumeration, serializer)

    return await _execute_metadata(
        tool,
        context,
        operation=operation,
        parameters=parameters,
        invoke=invoke,
    )


# ============ Capabilities ============


@router.get(
    "/{tool_id}/mcp/capabilities",
    response_model=Response[McpOperationOut[McpCapabilitiesOut]],
    summary="Negotiate and read the saved MCP server's capabilities",
)
async def get_mcp_capabilities(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    execution_id: UUID | None = Query(
        default=None, description="Pending metadata execution to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    operation = f"{OP_LIST_PREFIX}capabilities"

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> McpCapabilitiesOut:
        config = await build_mcp_config(tool, resolved)

        async def call_mcp(callbacks: Any) -> Any:
            return await probe_mcp_capabilities(
                config,
                timeout=MCP_METADATA_TIMEOUT_SECONDS,
                timeouts=MCP_METADATA_TIMEOUTS,
                callbacks=callbacks,
            )

        capabilities = await run_with_mcp_callbacks(
            tool, context, call_mcp, execution_id=context.execution_id
        )
        return _capabilities_out(capabilities)

    outcome = await _execute_metadata(
        tool, context, operation=operation, parameters={}, invoke=invoke
    )
    return success(data=outcome, msg_key="success")


# ============ Metadata listings ============


@router.get(
    "/{tool_id}/mcp/tools",
    response_model=Response[McpOperationOut[McpEnumerationOut[McpToolOut]]],
    summary="List tools advertised by the saved MCP server",
)
async def list_mcp_tools(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    max_items: int = Query(default=200, ge=1, le=DEFAULT_MAX_ITEMS),
    cursor: str | None = Query(
        default=None,
        max_length=4096,
        description="Opaque next_cursor from a truncated listing",
    ),
    execution_id: UUID | None = Query(
        default=None, description="Pending metadata execution to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    outcome = await _list_metadata(
        tool,
        context,
        operation=f"{OP_LIST_PREFIX}tools",
        max_items=max_items,
        cursor=cursor,
        enumerate_call=enumerate_mcp_tools,
        serializer=_tool_out,
    )
    return success(data=outcome, msg_key="success")


@router.get(
    "/{tool_id}/mcp/resources",
    response_model=Response[McpOperationOut[McpEnumerationOut[McpResourceOut]]],
    summary="List concrete resources advertised by the saved MCP server",
)
async def list_mcp_resources(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    max_items: int = Query(default=200, ge=1, le=DEFAULT_MAX_ITEMS),
    cursor: str | None = Query(
        default=None,
        max_length=4096,
        description="Opaque next_cursor from a truncated listing",
    ),
    execution_id: UUID | None = Query(
        default=None, description="Pending metadata execution to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    outcome = await _list_metadata(
        tool,
        context,
        operation=f"{OP_LIST_PREFIX}resources",
        max_items=max_items,
        cursor=cursor,
        enumerate_call=enumerate_mcp_resources,
        serializer=_resource_out,
    )
    return success(data=outcome, msg_key="success")


@router.get(
    "/{tool_id}/mcp/resource-templates",
    response_model=Response[McpOperationOut[McpEnumerationOut[McpResourceTemplateOut]]],
    summary="List resource templates advertised by the saved MCP server",
)
async def list_mcp_resource_templates(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    max_items: int = Query(default=200, ge=1, le=DEFAULT_MAX_ITEMS),
    cursor: str | None = Query(
        default=None,
        max_length=4096,
        description="Opaque next_cursor from a truncated listing",
    ),
    execution_id: UUID | None = Query(
        default=None, description="Pending metadata execution to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    outcome = await _list_metadata(
        tool,
        context,
        operation=f"{OP_LIST_PREFIX}resource-templates",
        max_items=max_items,
        cursor=cursor,
        enumerate_call=enumerate_mcp_resource_templates,
        serializer=_resource_template_out,
    )
    return success(data=outcome, msg_key="success")


@router.get(
    "/{tool_id}/mcp/prompts",
    response_model=Response[McpOperationOut[McpEnumerationOut[McpPromptOut]]],
    summary="List prompts advertised by the saved MCP server",
)
async def list_mcp_prompts(
    tool_id: UUID,
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    max_items: int = Query(default=200, ge=1, le=DEFAULT_MAX_ITEMS),
    cursor: str | None = Query(
        default=None,
        max_length=4096,
        description="Opaque next_cursor from a truncated listing",
    ),
    execution_id: UUID | None = Query(
        default=None, description="Pending metadata execution to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:read")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    outcome = await _list_metadata(
        tool,
        context,
        operation=f"{OP_LIST_PREFIX}prompts",
        max_items=max_items,
        cursor=cursor,
        enumerate_call=enumerate_mcp_prompts,
        serializer=_prompt_out,
    )
    return success(data=outcome, msg_key="success")


# ============ Approval-bound operations ============


@router.post(
    "/{tool_id}/mcp/tools/call",
    response_model=Response[McpOperationOut[McpToolResultOut]],
    summary="Call one MCP tool through the unified execution boundary",
)
async def call_mcp_tool(
    tool_id: UUID,
    payload: McpToolCallIn,
    team_id: UUID = Query(..., description="Consuming team context"),
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=payload.connection_mode,
        connection_id=payload.connection_id,
        execution_id=payload.execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    operation = f"{OP_TOOL_PREFIX}{payload.name}"
    parameters = {"name": payload.name, "arguments": payload.arguments}

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> McpToolResultOut:
        config = await build_mcp_config(tool, resolved)
        call_timeout = mcp_call_timeout_seconds(tool)

        async def call_mcp(callbacks: Any) -> Any:
            return await execute_mcp_tool(
                config,
                approved["name"],
                approved.get("arguments") or {},
                timeout=call_timeout,
                timeouts=MCP_CONTENT_TIMEOUTS,
                callbacks=callbacks,
            )

        result = await run_with_mcp_callbacks(
            tool,
            context,
            call_mcp,
            execution_id=context.execution_id,
            call_timeout_seconds=call_timeout,
        )
        return McpToolResultOut(
            success=result.success,
            result=result.result,
            error=result.error,
            is_error=result.is_error,
            content=[block.to_dict() for block in result.content],
            structured_content=result.structured_content,
            input_required=(
                result.input_required.to_dict()
                if result.input_required is not None
                else None
            ),
        )

    try:
        outcome = await execute_stored_tool(
            tool,
            operation,
            parameters,
            context,
            invoke,
            preview_parameters=payload.arguments,
        )
    except BusinessError:
        raise
    except Exception as exc:
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    return success(data=_operation_out(operation, outcome), msg_key="success")


@router.post(
    "/{tool_id}/mcp/resources/read",
    response_model=Response[McpOperationOut[list[McpResourceContentsOut]]],
    summary="Read one MCP resource through the unified execution boundary",
)
async def read_mcp_resource_contents(
    tool_id: UUID,
    payload: McpResourceReadIn,
    team_id: UUID = Query(..., description="Consuming team context"),
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=payload.connection_mode,
        connection_id=payload.connection_id,
        execution_id=payload.execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    uri = _validate_resource_uri(payload.uri)
    operation = OP_RESOURCE_READ
    parameters = {"uri": uri}

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> list[McpResourceContentsOut]:
        config = await build_mcp_config(tool, resolved)

        async def call_mcp(callbacks: Any) -> Any:
            return await read_mcp_resource(
                config,
                approved["uri"],
                timeout=MCP_CONTENT_TIMEOUT_SECONDS,
                limits=MCP_CONTENT_LIMITS,
                timeouts=MCP_CONTENT_TIMEOUTS,
                callbacks=callbacks,
            )

        contents = await run_with_mcp_callbacks(
            tool, context, call_mcp, execution_id=context.execution_id
        )
        return [
            McpResourceContentsOut(
                uri=item.uri,
                mime_type=item.mime_type,
                text=item.text,
                blob=item.blob,
                meta=item.meta,
            )
            for item in contents
        ]

    try:
        outcome = await execute_stored_tool(
            tool,
            operation,
            parameters,
            context,
            invoke,
        )
    except BusinessError:
        raise
    except Exception as exc:
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    return success(data=_operation_out(operation, outcome), msg_key="success")


@router.get(
    "/{tool_id}/mcp/resources/subscribe",
    summary="Stream live MCP resource updates for one explicitly selected connection",
)
async def subscribe_mcp_resource(
    tool_id: UUID,
    uri: str = Query(..., min_length=1, max_length=8192),
    team_id: UUID = Query(..., description="Consuming team context"),
    connection_mode: McpConnectionMode | None = Query(default=None),
    connection_id: UUID | None = Query(default=None),
    execution_id: UUID | None = Query(
        default=None, description="Pending subscribe approval to resume"
    ),
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
) -> Any:
    """Open one request-scoped subscription and stream redacted update events.

    Authorization, connection resolution and approval happen first through
    ``execute_stored_tool`` (operation ``subscribe:resource``). A pending
    approval returns the normal JSON pending envelope; replaying with
    ``execution_id`` after approval opens the live session and streams. The
    stream owns the session: TTL expiry or client disconnect closes it, and
    unsubscribe is read-side cleanup that never enters the outcome machinery.
    """
    context = _call_context(
        team_id,
        current_user,
        connection_mode=connection_mode,
        connection_id=connection_id,
        execution_id=execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    uri = _validate_resource_uri(uri)
    operation = OP_RESOURCE_SUBSCRIBE
    parameters = {"uri": uri}
    stack = AsyncExitStack()

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> Any:
        config = await build_mcp_config(tool, resolved)
        scope = getattr(resolved.scope, "value", resolved.scope) if resolved else None
        return await stack.enter_async_context(
            open_subscription(
                tool=tool,
                config=config,
                uri=approved["uri"],
                user_id=current_user.id,
                team_id=team_id,
                connection_id=resolved.connection_id if resolved else None,
                connection_scope=str(scope) if scope is not None else None,
                account_label=resolved.account_label if resolved else None,
            )
        )

    try:
        outcome = await execute_stored_tool(
            tool, operation, parameters, context, invoke
        )
    except BusinessError:
        await stack.aclose()
        raise
    except Exception as exc:
        await stack.aclose()
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    except BaseException:
        await stack.aclose()
        raise

    if isinstance(outcome, PendingToolApproval):
        await stack.aclose()
        return success(data=_operation_out(operation, outcome), msg_key="success")

    handle = outcome

    async def event_stream():
        yield _sse_frame("subscription_opened", handle.opened_event())
        try:
            async for event in handle.events():
                if event is None:
                    yield ": keep-alive\n\n"
                else:
                    yield _sse_frame("resource_updated", event)
        except asyncio.CancelledError:
            handle.close_reason = SubscriptionClosed.CLIENT_DISCONNECTED
            raise
        except Exception:
            handle.close_reason = SubscriptionClosed.CONNECTION_LOST
            logger.warning(
                "MCP resource subscription %s failed", handle.id, exc_info=True
            )
        else:
            yield _sse_frame(
                "subscription_closed",
                {
                    "subscription_id": str(handle.id),
                    "reason": handle.close_reason or SubscriptionClosed.TTL_EXPIRED,
                },
            )
        finally:
            await stack.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{tool_id}/mcp/prompts/get",
    response_model=Response[McpOperationOut[McpPromptResultOut]],
    summary="Render one MCP prompt through the unified execution boundary",
)
async def get_mcp_prompt_result(
    tool_id: UUID,
    payload: McpPromptGetIn,
    team_id: UUID = Query(..., description="Consuming team context"),
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=payload.connection_mode,
        connection_id=payload.connection_id,
        execution_id=payload.execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    operation = f"{OP_PROMPT_PREFIX}{payload.name}"
    parameters = {"name": payload.name, "arguments": payload.arguments}

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> McpPromptResultOut:
        config = await build_mcp_config(tool, resolved)

        async def call_mcp(callbacks: Any) -> Any:
            return await get_mcp_prompt(
                config,
                approved["name"],
                approved.get("arguments"),
                timeout=MCP_CONTENT_TIMEOUT_SECONDS,
                limits=MCP_CONTENT_LIMITS,
                timeouts=MCP_CONTENT_TIMEOUTS,
                callbacks=callbacks,
            )

        prompt = await run_with_mcp_callbacks(
            tool, context, call_mcp, execution_id=context.execution_id
        )
        return McpPromptResultOut(
            messages=[
                McpPromptMessageOut(
                    role=message.role, content=message.content.to_dict()
                )
                for message in prompt.messages
            ],
            description=prompt.description,
            meta=prompt.meta,
        )

    try:
        outcome = await execute_stored_tool(
            tool,
            operation,
            parameters,
            context,
            invoke,
            # The prompt name identifies the operation; only its arguments
            # are the reviewer's business input.
            preview_parameters=payload.arguments or {},
        )
    except BusinessError:
        raise
    except Exception as exc:
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    return success(data=_operation_out(operation, outcome), msg_key="success")


@router.post(
    "/{tool_id}/mcp/completion",
    response_model=Response[McpOperationOut[McpCompletionOut]],
    summary="Complete a prompt or resource-template argument",
)
async def complete_mcp_prompt_argument(
    tool_id: UUID,
    payload: McpCompletionIn,
    team_id: UUID = Query(..., description="Consuming team context"),
    current_user: User = Depends(deps.PermissionChecker("tool:execute")),
) -> Any:
    context = _call_context(
        team_id,
        current_user,
        connection_mode=payload.connection_mode,
        connection_id=payload.connection_id,
        execution_id=payload.execution_id,
    )
    tool = await _load_mcp_tool(tool_id, context)
    operation = (
        OP_COMPLETION_PROMPT
        if payload.reference.kind == "prompt"
        else OP_COMPLETION_RESOURCE_TEMPLATE
    )
    parameters = {
        "reference_kind": payload.reference.kind,
        "name": payload.reference.name,
        "uri": payload.reference.uri,
        "argument_name": payload.argument_name,
        "argument_value": payload.argument_value,
        "context_arguments": payload.context_arguments,
    }

    async def invoke(
        approved: dict[str, Any], resolved: ResolvedConnection | None
    ) -> McpCompletionOut:
        config = await build_mcp_config(tool, resolved)
        reference = McpCompletionReference(
            kind=approved["reference_kind"],
            name=approved.get("name"),
            uri=approved.get("uri"),
        )

        async def call_mcp(callbacks: Any) -> Any:
            return await complete_mcp_argument(
                config,
                reference,
                approved["argument_name"],
                approved.get("argument_value") or "",
                context_arguments=approved.get("context_arguments"),
                timeout=MCP_CONTENT_TIMEOUT_SECONDS,
                timeouts=MCP_CONTENT_TIMEOUTS,
                callbacks=callbacks,
            )

        completion = await run_with_mcp_callbacks(
            tool, context, call_mcp, execution_id=context.execution_id
        )
        return McpCompletionOut(
            values=completion.values,
            total=completion.total,
            has_more=completion.has_more,
        )

    try:
        outcome = await execute_stored_tool(
            tool,
            operation,
            parameters,
            context,
            invoke,
        )
    except BusinessError:
        raise
    except Exception as exc:
        raise _mcp_business_error(exc, operation=operation, tool=tool) from exc
    return success(data=_operation_out(operation, outcome), msg_key="success")


__all__ = ["router"]
