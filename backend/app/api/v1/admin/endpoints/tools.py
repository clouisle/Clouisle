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
    _category_value,
    _matches_filter,
    _option,
    _runtime_duration_ms,
    _serialize_runtime_artifacts,
)
from app.core.i18n import t
from app.llm.tools import tool_registry
from app.llm.tools.executors import execute_http_tool
from app.llm.tools.mcp_client import execute_mcp_tool, list_mcp_tools
from app.models.tool import CustomToolType as DBCustomToolType
from app.models.tool import Tool, ToolShare, ToolType as DBToolType
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
from app.services.error_messages import resolve_user_visible_error
from app.services.sandbox.compiler import compile_code_config_job
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJobSource

router = APIRouter()
logger = logging.getLogger(__name__)


async def _build_admin_tools(user: User) -> list[ToolOut]:
    tools: list[ToolOut] = get_builtin_tools(user.locale)
    db_tools = (
        await Tool.all()
        .prefetch_related("team", "created_by")
        .order_by("-updated_at")
    )
    for db_tool in db_tools:
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
    tools = await _build_admin_tools(current_user)
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
        if not _matches_filter("enabled" if tool.is_enabled else "disabled", status_filter):
            continue
        if not _matches_filter(str(tool.team_id) if tool.team_id else None, team_filter):
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
    creator_values = sorted({tool.created_by_name for tool in tools if tool.created_by_name})
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
        type=DBToolType(tool_in.type.value),
        custom_type=DBCustomToolType(tool_in.custom_type.value)
        if tool_in.custom_type
        else None,
        parameters=[parameter.model_dump() for parameter in tool_in.parameters],
        http_config=tool_in.http_config.model_dump() if tool_in.http_config else {},
        code_config=tool_in.code_config.model_dump() if tool_in.code_config else {},
        mcp_config=tool_in.mcp_config.model_dump() if tool_in.mcp_config else {},
        credentials=tool_in.credentials,
        is_enabled=tool_in.is_enabled,
        created_by=current_user,
    )
    return success(data=db_tool_to_detail(tool, current_user.username), msg_key="tool_created")


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
        tool.credentials = tool_in.credentials
    if tool_in.is_enabled is not None:
        tool.is_enabled = tool_in.is_enabled
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
        type=tool.type,
        custom_type=tool.custom_type,
        parameters=tool.parameters,
        http_config=tool.http_config,
        code_config=tool.code_config,
        mcp_config=tool.mcp_config,
        credentials=tool.credentials,
        is_enabled=False,
        created_by=current_user,
    )
    return success(data=db_tool_to_detail(new_tool, current_user.username), msg_key="tool_duplicated")


@router.post("/test", response_model=Response[ToolExecuteResponse])
async def test_tool(
    request: ToolExecuteRequest,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:execute")),
) -> Any:
    start_time = time.time()
    builtin_tool = tool_registry.get_tool(request.name)
    if builtin_tool:
        try:
            from app.models.tool_config import ToolConfig

            credentials = {}
            if team_id:
                tool_config = await ToolConfig.filter(tool_name=request.name, team_id=team_id).first()
                if tool_config:
                    credentials = tool_config.credentials or {}
            if not credentials:
                global_config = await ToolConfig.filter(tool_name=request.name, team_id=None).first()
                if global_config:
                    credentials = global_config.credentials or {}
            result = await tool_registry.execute(request.name, request.arguments, credentials=credentials)
            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=True,
                    result=result,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            )
        except Exception as exc:
            logger.error("Builtin tool execution error: %s", exc)
            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=False,
                    error=resolve_user_visible_error(str(exc)),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            )

    custom_query = Tool.filter(name=request.name)
    if team_id:
        custom_query = custom_query.filter(team_id=team_id)
    custom_tool = await custom_query.first()
    if not custom_tool:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_not_found",
            status_code=404,
        )

    if custom_tool.type == DBToolType.MCP:
        mcp_config = custom_tool.mcp_config or {}
        mcp_tool_name = request.arguments.pop("__tool_name__", None) or request.name
        try:
            result = await execute_mcp_tool(
                mcp_config=mcp_config,
                tool_name=mcp_tool_name,
                arguments=request.arguments,
                timeout=60.0,
            )
            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=result.success,
                    result=result.result,
                    error=result.error,
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            )
        except Exception as exc:
            logger.exception("MCP tool execution error: %s", exc)
            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=False,
                    error=resolve_user_visible_error(str(exc), fallback_key="mcp_tool_execution_failed"),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            )

    if custom_tool.custom_type == DBCustomToolType.HTTP:
        result = await execute_http_tool(
            custom_tool.http_config,
            request.arguments,
            custom_tool.credentials,
        )
        return success(
            data=ToolExecuteResponse(
                name=request.name,
                success=result.get("success", False),
                result=result.get("result"),
                error=result.get("error"),
                duration_ms=int((time.time() - start_time) * 1000),
            )
        )

    if custom_tool.custom_type == DBCustomToolType.CODE:
        code_config = custom_tool.code_config or {}
        if not code_config.get("code"):
            return success(
                data=ToolExecuteResponse(
                    name=request.name,
                    success=False,
                    error=t("tool_code_not_defined"),
                    duration_ms=int((time.time() - start_time) * 1000),
                )
            )
        job = compile_code_config_job(
            code_config=code_config,
            params=request.arguments,
            timeout=float(code_config.get("limits", {}).get("timeout_seconds", 30.0)),
            source=SandboxJobSource.TOOL,
        )
        exec_result = await sandbox_gateway.submit_and_wait(
            job,
            timeout_seconds=job.limits.timeout_seconds + 5,
        )
        return success(
            data=ToolExecuteResponse(
                name=request.name,
                success=exec_result.success,
                result=exec_result.result,
                error=exec_result.error,
                logs=exec_result.stdout or None,
                artifacts=_serialize_runtime_artifacts(getattr(exec_result, "artifacts", [])),
                duration_ms=_runtime_duration_ms(exec_result),
            )
        )

    return success(
        data=ToolExecuteResponse(
            name=request.name,
            success=False,
            error=t("unsupported_custom_tool_type", tool_type=custom_tool.custom_type),
            duration_ms=int((time.time() - start_time) * 1000),
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
                error=t("unsupported_code_execution_language", language=request.language),
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
            "artifacts": [artifact.model_dump(exclude_none=True) for artifact in request.artifacts],
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
            artifacts=_serialize_runtime_artifacts(getattr(exec_result, "artifacts", [])),
            duration_ms=_runtime_duration_ms(exec_result),
        )
    )


@router.get("/config", response_model=Response[list[dict]])
async def list_tool_configs(
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigOut

    configs = await ToolConfig.filter(team_id=team_id).all()
    return success(data=[ToolConfigOut.model_validate(config).model_dump() for config in configs])


@router.get("/config/{tool_name}", response_model=Response[dict])
async def get_tool_config(
    tool_name: str,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:read")),
) -> Any:
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigOut

    config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    if not config:
        if team_id and tool_registry.get_tool(tool_name):
            config = await ToolConfig.create(tool_name=tool_name, team_id=team_id, credentials={})
        else:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="tool_config_not_found",
                status_code=404,
            )
    return success(data=ToolConfigOut.model_validate(config).model_dump())


@router.post("/config", response_model=Response[dict])
async def create_tool_config(
    data: dict,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigCreate, ToolConfigOut

    config_data = ToolConfigCreate(**data)
    existing = await ToolConfig.filter(tool_name=config_data.tool_name, team_id=team_id).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.DUPLICATE_NAME,
            msg_key="tool_config_already_exists",
            status_code=400,
        )
    config = await ToolConfig.create(
        tool_name=config_data.tool_name,
        team_id=team_id,
        credentials=config_data.credentials,
    )
    return success(data=ToolConfigOut.model_validate(config).model_dump(), msg_key="tool_config_created")


@router.put("/config/{tool_name}", response_model=Response[dict])
async def update_tool_config(
    tool_name: str,
    data: dict,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    from app.models.tool_config import ToolConfig
    from app.schemas.tool_config import ToolConfigOut, ToolConfigUpdate

    config_data = ToolConfigUpdate(**data)
    config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    if not config:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_config_not_found",
            status_code=404,
        )
    config.credentials = config_data.credentials
    await config.save()
    return success(data=ToolConfigOut.model_validate(config).model_dump(), msg_key="tool_config_updated")


@router.delete("/config/{tool_name}", response_model=Response[None])
async def delete_tool_config(
    tool_name: str,
    team_id: UUID | None = None,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:delete")),
) -> Any:
    from app.models.tool_config import ToolConfig

    config = await ToolConfig.filter(tool_name=tool_name, team_id=team_id).first()
    if not config:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="tool_config_not_found",
            status_code=404,
        )
    await config.delete()
    return success(data=None, msg_key="tool_config_deleted")


@router.post("/{tool_id}/share", response_model=Response[ToolShareOut])
async def share_tool(
    tool_id: UUID,
    share_data: ToolShareInput,
    current_user: User = Depends(deps.PermissionChecker("admin:capability:update")),
) -> Any:
    tool = await _get_db_tool(tool_id, detail=True)
    target_team = await _get_team(share_data.team_id)
    if tool.team_id == share_data.team_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="cannot_share_to_own_team",
            status_code=400,
        )
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
    return success(data=ToolShareListOut(shares=share_list, total=len(share_list)).model_dump())


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
