"""Admin capability tool endpoints."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api import deps
from app.api.v1.endpoints.tools import (
    db_tool_to_detail,
    db_tool_to_out,
    get_builtin_tools,
    get_builtin_tools_for_team,
    _category_value,
    _enforce_tool_write_contract,
    _matches_filter,
    _option,
    _run_saved_tool_test,
    _runtime_duration_ms,
    _serialize_runtime_artifacts,
    _tool_test_context,
    _tool_test_response,
)
from app.core.i18n import t
from app.llm.tools import tool_registry
from app.llm.tools.mcp_client import list_mcp_tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool_approval import ExecutionEntrypoint
from app.models.tool import (
    Tool,
    ToolShare,
    ToolType as DBToolType,
    ToolVisibility as DBToolVisibility,
)
from app.models.user import Team, User
from app.schemas.response import BusinessError, Response, ResponseCode, success
from app.schemas.tool import (
    CodeExecuteRequest,
    CodeExecuteResponse,
    McpToolInfoOut,
    McpToolsListRequest,
    McpToolsListResponse,
    ToolCreateInput,
    ToolDetailOut,
    ToolExecuteRequest,
    ToolExecuteResponse,
    ToolFilterOptionsOut,
    ToolListPageOut,
    ToolOut,
    ToolShareInput,
    ToolShareListOut,
    ToolShareOut,
    ToolSharePermission,
    ToolType,
    ToolUpdateInput,
)
from app.schemas.web_search import (
    WebSearchConfigOut,
    WebSearchConfigUpdate,
    WebSearchTestInput,
)
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource
from app.services.tool import ToolExecutor
from app.services.tool_execution import require_caller_only_policy
from app.services.tool_secret_contract import enforce_tool_secret_contract

router = APIRouter()
logger = logging.getLogger(__name__)


async def _build_admin_tools(user: User, team_id: UUID | None = None) -> list[ToolOut]:
    if team_id is None:
        first_team = await Team.all().order_by("name").first()
        team_id = first_team.id if first_team else None
    tools: list[ToolOut] = (
        await get_builtin_tools_for_team(team_id, user.locale)
        if team_id is not None
        else get_builtin_tools(user.locale)
    )
    # Builtin rows are already represented by the registry list above; skip
    # them (and any duplicate id) instead of listing each builtin twice.
    listed_ids = {tool.id for tool in tools if tool.id is not None}
    db_tools = (
        await Tool.all().prefetch_related("team", "created_by").order_by("-updated_at")
    )
    for db_tool in db_tools:
        if db_tool.id in listed_ids:
            continue
        if getattr(db_tool, "type", None) in (
            DBToolType.BUILTIN,
            DBToolType.BUILTIN.value,
        ):
            continue
        creator_name = db_tool.created_by.username if db_tool.created_by else None
        tool_out = db_tool_to_out(db_tool, creator_name)
        tool_out.is_owned = True
        tool_out.owner_team_id = db_tool.team_id
        tool_out.owner_team_name = db_tool.team.name if db_tool.team else None
        tool_out.shared_with_count = await ToolShare.filter(tool_id=db_tool.id).count()
        tools.append(tool_out)
    return tools


async def _get_db_tool(tool_id: UUID, *, detail: bool = False) -> Tool:
    query = Tool.filter(id=tool_id)
    if detail:
        query = query.prefetch_related("team", "created_by")
    tool = await query.first()
    if not tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )
    return tool


async def _get_team(team_id: UUID) -> Team:
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )
    return team


@router.get("", response_model=Response[ToolListPageOut])
async def list_tools(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None),
    type: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    team_id: list[UUID] | None = Query(None),
    creator: list[str] | None = Query(None),
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    tools = await _build_admin_tools(
        current_user, team_id[0] if team_id and len(team_id) == 1 else None
    )
    type_filter = set(type or [])
    category_filter = set(category or [])
    status_filter = set(status or [])
    creator_filter = set(creator or [])
    team_filter = {str(value) for value in team_id or []}
    search_query = search.lower() if search else None

    filtered_tools = []
    for tool in tools:
        if search_query and (
            search_query not in tool.name.lower()
            and search_query not in tool.display_name.lower()
            and search_query not in tool.description.lower()
        ):
            continue
        if not _matches_filter(tool.type.value, type_filter):
            continue
        if not _matches_filter(_category_value(tool.category), category_filter):
            continue
        if not _matches_filter(
            "enabled" if tool.is_enabled else "disabled", status_filter
        ):
            continue
        if not _matches_filter(
            str(tool.team_id) if tool.team_id else None, team_filter
        ):
            continue
        if not _matches_filter(tool.created_by_name, creator_filter):
            continue
        filtered_tools.append(tool)

    filtered_tools.sort(
        key=lambda tool: (
            tool.display_name.lower(),
            str(tool.id) if tool.id else tool.name,
        )
    )
    total = len(filtered_tools)
    start = (page - 1) * page_size
    return success(
        data=ToolListPageOut(
            items=filtered_tools[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/filters", response_model=Response[ToolFilterOptionsOut])
async def get_tool_filter_options(
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    tools = await _build_admin_tools(current_user)
    teams = await Team.all().order_by("name")
    creator_values = sorted(
        {tool.created_by_name for tool in tools if tool.created_by_name}
    )
    categories = sorted({tool.category for tool in tools if tool.category})
    return success(
        data=ToolFilterOptionsOut(
            types=[
                _option(ToolType.BUILTIN.value),
                _option(ToolType.CUSTOM.value),
                _option(ToolType.MCP.value),
            ],
            categories=[_option(_category_value(value)) for value in categories],
            statuses=[_option("enabled"), _option("disabled")],
            teams=[_option(str(team.id), team.name) for team in teams],
            creators=[_option(value) for value in creator_values],
        )
    )


@router.post("/mcp/list-tools", response_model=Response[McpToolsListResponse])
async def get_mcp_tools(
    request: McpToolsListRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    try:
        tools = await list_mcp_tools(request.mcp_config.model_dump())
        return success(
            data=McpToolsListResponse(
                tools=[
                    McpToolInfoOut(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    for tool in tools
                ],
            )
        )
    except Exception as exc:
        logger.exception("Failed to list MCP tools: %s", exc)
        raise BusinessError(
            code=ResponseCode.INTERNAL_ERROR,
            msg_key="mcp_connection_failed",
            status_code=500,
        ) from exc


@router.post("", response_model=Response[ToolDetailOut])
async def create_tool(
    team_id: UUID,
    tool_in: ToolCreateInput,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:create")),
) -> Any:
    await _get_team(team_id)
    _enforce_tool_write_contract(tool_in)
    if tool_in.type == ToolType.BUILTIN:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="tool_builtin_not_creatable",
            status_code=400,
        )
    existing = await Tool.filter(team_id=team_id, name=tool_in.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_EXISTS,
            msg_key="tool_name_exists",
            status_code=400,
        )
    tool = await Tool.create(
        team_id=team_id,
        name=tool_in.name,
        display_name=tool_in.display_name,
        description=tool_in.description,
        icon=tool_in.icon,
        category=tool_in.category,
        visibility=DBToolVisibility(tool_in.visibility.value),
        type=DBToolType(tool_in.type.value),
        custom_type=DBCustomToolType(tool_in.custom_type.value)
        if tool_in.custom_type
        else None,
        parameters=[parameter.model_dump() for parameter in tool_in.parameters],
        http_config=tool_in.http_config.model_dump() if tool_in.http_config else {},
        code_config=tool_in.code_config.model_dump() if tool_in.code_config else {},
        mcp_config=tool_in.mcp_config.model_dump() if tool_in.mcp_config else {},
        credentials={},
        is_enabled=tool_in.is_enabled,
        identity_policy=tool_in.identity_policy,
        connection_fields=[field.model_dump() for field in tool_in.connection_fields],
        approval_policy=tool_in.approval_policy.model_dump(mode="json"),
        created_by=current_user,
    )
    return success(
        data=db_tool_to_detail(tool, current_user.username), msg_key="tool_created"
    )


@router.get("/id/{tool_id}", response_model=Response[ToolDetailOut])
async def get_tool_by_id(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    tool = await _get_db_tool(tool_id, detail=True)
    creator_name = tool.created_by.username if tool.created_by else None
    detail = db_tool_to_detail(tool, creator_name)
    detail.owner_team_id = tool.team_id
    detail.owner_team_name = tool.team.name if tool.team else None
    detail.shared_with_count = await ToolShare.filter(tool_id=tool.id).count()
    return success(data=detail)


@router.put("/{tool_id}", response_model=Response[ToolDetailOut])
async def update_tool(
    tool_id: UUID,
    tool_in: ToolUpdateInput,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    tool = await _get_db_tool(tool_id, detail=True)
    if any(
        value is not None
        for value in (
            tool_in.credentials,
            tool_in.http_config,
            tool_in.mcp_config,
            tool_in.connection_fields,
            tool_in.approval_policy,
        )
    ):
        _enforce_tool_write_contract(
            tool_in, existing_connection_fields=tool.connection_fields
        )
    if tool_in.name and tool_in.name != tool.name:
        existing = await Tool.filter(team_id=tool.team_id, name=tool_in.name).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.ALREADY_EXISTS,
                msg_key="tool_name_exists",
                status_code=400,
            )
        tool.name = tool_in.name

    if tool_in.display_name is not None:
        tool.display_name = tool_in.display_name
    if tool_in.description is not None:
        tool.description = tool_in.description
    if tool_in.icon is not None:
        tool.icon = tool_in.icon
    if tool_in.category is not None:
        tool.category = tool_in.category
    if tool_in.visibility is not None:
        tool.visibility = DBToolVisibility(tool_in.visibility.value)
    if tool_in.custom_type is not None:
        tool.custom_type = DBCustomToolType(tool_in.custom_type.value)
    if tool_in.parameters is not None:
        tool.parameters = [parameter.model_dump() for parameter in tool_in.parameters]
    if tool_in.http_config is not None:
        tool.http_config = tool_in.http_config.model_dump()
    if tool_in.code_config is not None:
        tool.code_config = tool_in.code_config.model_dump()
    if tool_in.mcp_config is not None:
        tool.mcp_config = tool_in.mcp_config.model_dump()
    if tool_in.credentials is not None:
        # Non-empty maps are rejected above; an explicit empty map clears any
        # legacy inline credentials so the definition references connections.
        tool.credentials = {}
    if tool_in.is_enabled is not None:
        tool.is_enabled = tool_in.is_enabled
    if tool_in.identity_policy is not None:
        tool.identity_policy = tool_in.identity_policy
    if tool_in.connection_fields is not None:
        tool.connection_fields = [
            field.model_dump() for field in tool_in.connection_fields
        ]
    if tool_in.approval_policy is not None:
        tool.approval_policy = tool_in.approval_policy.model_dump(mode="json")
    tool.definition_version += 1
    await tool.save()

    creator_name = tool.created_by.username if tool.created_by else None
    return success(data=db_tool_to_detail(tool, creator_name), msg_key="tool_updated")


@router.delete("/{tool_id}", response_model=Response[None])
async def delete_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:delete")),
) -> Any:
    tool = await _get_db_tool(tool_id)
    await tool.delete()
    return success(data=None, msg_key="tool_deleted")


@router.post("/{tool_id}/toggle", response_model=Response[ToolDetailOut])
async def toggle_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    tool = await _get_db_tool(tool_id, detail=True)
    tool.is_enabled = not tool.is_enabled
    await tool.save()
    creator_name = tool.created_by.username if tool.created_by else None
    return success(data=db_tool_to_detail(tool, creator_name), msg_key="tool_updated")


@router.post("/{tool_id}/duplicate", response_model=Response[ToolDetailOut])
async def duplicate_tool(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:create")),
) -> Any:
    tool = await _get_db_tool(tool_id)
    enforce_tool_secret_contract(
        credentials=tool.credentials,
        http_config=tool.http_config,
        mcp_config=tool.mcp_config,
        connection_fields=tool.connection_fields,
    )
    require_caller_only_policy(tool.approval_policy)
    base_name = f"{tool.name}_copy"
    new_name = base_name
    counter = 1
    while await Tool.filter(team_id=tool.team_id, name=new_name).exists():
        new_name = f"{base_name}_{counter}"
        counter += 1

    new_tool = await Tool.create(
        team_id=tool.team_id,
        name=new_name,
        display_name=f"{tool.display_name} (Copy)",
        description=tool.description,
        icon=tool.icon,
        category=tool.category,
        visibility=DBToolVisibility.PRIVATE,
        type=tool.type,
        custom_type=tool.custom_type,
        parameters=tool.parameters,
        http_config=tool.http_config,
        code_config=tool.code_config,
        mcp_config=tool.mcp_config,
        credentials={},
        identity_policy=tool.identity_policy,
        connection_fields=tool.connection_fields,
        approval_policy=tool.approval_policy,
        is_enabled=False,
        created_by=current_user,
    )
    return success(
        data=db_tool_to_detail(new_tool, current_user.username),
        msg_key="tool_duplicated",
    )


@router.post("/test", response_model=Response[ToolExecuteResponse])
async def test_tool(
    request: ToolExecuteRequest,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:execute")),
) -> Any:
    started_at = time.time()

    # 内置工具同样需要可信的团队上下文，缺失时拒绝而不是绕过策略。
    if tool_registry.get_tool(request.name) is not None:
        if team_id is None:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="team_id_required",
                status_code=400,
            )
        context = _tool_test_context(
            current_user, team_id, ExecutionEntrypoint.ADMIN_TEST, request
        )
        raw = await ToolExecutor().execute_builtin_tool(
            tool_name=request.name,
            arguments=request.arguments,
            team_id=team_id,
            context=context,
        )
        return success(
            data=_tool_test_response(
                request.name,
                builtin=True,
                custom_type=None,
                raw=raw,
                started_at=started_at,
            )
        )

    custom_query = Tool.filter(name=request.name)
    if team_id is not None:
        custom_query = custom_query.filter(team_id=team_id)
    custom_tools = await custom_query.limit(2)
    if not custom_tools:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )
    if len(custom_tools) > 1:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg="Multiple tools share this name; pass team_id to disambiguate",
            status_code=400,
        )

    return success(
        data=await _run_saved_tool_test(
            custom_tools[0],
            request,
            current_user,
            ExecutionEntrypoint.ADMIN_TEST,
            started_at=started_at,
        )
    )


@router.post("/execute-code", response_model=Response[CodeExecuteResponse])
async def execute_code_directly(
    request: CodeExecuteRequest,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:execute")),
) -> Any:
    start_time = time.time()
    if request.language.lower() not in ("javascript", "python"):
        return success(
            data=CodeExecuteResponse(
                success=False,
                error=t(
                    "unsupported_code_execution_language", language=request.language
                ),
                duration_ms=int((time.time() - start_time) * 1000),
            )
        )

    job = compile_code_config_job(
        code_config={
            "language": request.language,
            "code": request.code,
            "command": request.command,
            "python_packages": request.python_packages,
            "js_packages": request.js_packages,
            "python_package_index_url": request.python_package_index_url,
            "node_package_registry_url": request.node_package_registry_url,
            "artifacts": [
                artifact.model_dump(exclude_none=True) for artifact in request.artifacts
            ],
            "limits": request.limits.model_dump(),
        },
        params=request.params,
        timeout=request.timeout,
        source=SandboxJobSource.DEBUG,
    )
    exec_result = await sandbox_gateway.submit_and_wait(
        job,
        timeout_seconds=job.limits.timeout_seconds + 5,
    )
    return success(
        data=CodeExecuteResponse(
            success=exec_result.success,
            result=exec_result.result,
            error=exec_result.error,
            logs=exec_result.stdout or None,
            artifacts=_serialize_runtime_artifacts(
                getattr(exec_result, "artifacts", [])
            ),
            duration_ms=_runtime_duration_ms(exec_result),
        )
    )


@router.get("/web-search/config", response_model=Response[WebSearchConfigOut])
async def get_site_web_search_config(
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    from app.services.web_search_config import get_web_search_config

    return success(data=await get_web_search_config())


@router.put("/web-search/config", response_model=Response[WebSearchConfigOut])
async def update_site_web_search_config(
    data: WebSearchConfigUpdate,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    from app.services.web_search_config import save_web_search_config

    return success(data=await save_web_search_config(data))


@router.post("/web-search/test", response_model=Response[dict])
async def test_site_web_search_config(
    data: WebSearchTestInput,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:execute")),
) -> Any:
    from app.llm.tools.builtin.web_search import web_search

    return success(data=await web_search(data.query, search_engine=data.engine))


@router.post("/{tool_id}/share", response_model=Response[ToolShareOut])
async def share_tool(
    tool_id: UUID,
    share_data: ToolShareInput,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    tool = await _get_db_tool(tool_id, detail=True)
    if tool.team_id == share_data.team_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="cannot_share_to_own_team",
            status_code=400,
        )
    if tool.visibility == DBToolVisibility.PRIVATE:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="private_tool_cannot_be_shared",
            status_code=400,
        )
    target_team = await _get_team(share_data.team_id)
    existing_share = await ToolShare.filter(
        tool_id=tool_id, shared_with_team_id=share_data.team_id
    ).first()
    if existing_share:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="tool_already_shared",
            status_code=400,
        )
    share = await ToolShare.create(
        tool_id=tool_id,
        shared_with_team_id=share_data.team_id,
        permission=share_data.permission,
        shared_by_id=current_user.id,
    )
    await share.fetch_related("tool", "shared_by")
    return success(
        data=ToolShareOut(
            id=share.id,
            tool_id=share.tool_id,
            tool_name=tool.name,
            tool_display_name=tool.display_name,
            shared_with_team_id=share.shared_with_team_id,
            shared_with_team_name=target_team.name,
            permission=ToolSharePermission(share.permission),
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.username if share.shared_by else "",
            shared_at=share.shared_at,
        ).model_dump(),
        msg_key="tool_shared_successfully",
    )


@router.get("/{tool_id}/shares", response_model=Response[ToolShareListOut])
async def list_tool_shares(
    tool_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    await _get_db_tool(tool_id)
    shares = (
        await ToolShare.filter(tool_id=tool_id)
        .prefetch_related("tool", "shared_with_team", "shared_by")
        .order_by("-shared_at")
    )
    share_list = [
        ToolShareOut(
            id=share.id,
            tool_id=share.tool_id,
            tool_name=share.tool.name,
            tool_display_name=share.tool.display_name,
            shared_with_team_id=share.shared_with_team_id,
            shared_with_team_name=share.shared_with_team.name,
            permission=ToolSharePermission(share.permission),
            shared_by_id=share.shared_by_id,
            shared_by_name=share.shared_by.username if share.shared_by else "",
            shared_at=share.shared_at,
        )
        for share in shares
    ]
    return success(
        data=ToolShareListOut(shares=share_list, total=len(share_list)).model_dump()
    )


@router.delete("/{tool_id}/share/{team_id}", response_model=Response[None])
async def unshare_tool(
    tool_id: UUID,
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    await _get_db_tool(tool_id)
    share = await ToolShare.filter(tool_id=tool_id, shared_with_team_id=team_id).first()
    if not share:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_share_not_found",
            status_code=404,
        )
    await share.delete()
    return success(data=None, msg_key="tool_unshared_successfully")
